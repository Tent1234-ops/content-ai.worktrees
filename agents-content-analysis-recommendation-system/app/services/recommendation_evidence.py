"""Frozen, source-addressable evidence; missing audio is never a content gap."""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from functools import lru_cache

from app.services.nlp import (COMPARABLE_SYNONYMS_BY_DOMAIN, PYTHAINLP_ENGINE,
                              tokenize_text, word_tokenize)
from app.core.datetime_utils import utc_isoformat

SCHEMA_VERSION = "recommendation-evidence-v1"
METHOD_VERSION = "transcript-gap-source-spans-v1"


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def valid_segments(segments) -> list[dict]:
    result = []
    for index, segment in enumerate(segments or []):
        if not isinstance(segment, dict) or not str(segment.get("text") or "").strip():
            continue
        try:
            if isinstance(segment.get("start"), bool) or isinstance(segment.get("end"), bool):
                continue
            start = float(segment["start"])
            end = float(segment["end"]) if segment.get("end") is not None else start + float(segment["duration"])
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
            continue
        result.append({"segment_index": segment.get("segment_index", index), "start": start, "end": end,
                       "text": str(segment["text"]).strip()})
    return result


# Phase 5 compares every topic across a full category cohort. The previous cache
# size (64) thrashed as soon as a category had 65 reference clips.
@lru_cache(maxsize=512)
def _thai_spans(text: str):
    thai_spans = set()
    if word_tokenize is not None and re.search(r"[\u0e00-\u0e7f]", text):
        offset = 0
        for token in word_tokenize(text, engine=PYTHAINLP_ENGINE, keep_whitespace=True):
            thai_spans.add((offset, offset + len(token)))
            offset += len(token)
    return thai_spans


@lru_cache(maxsize=256)
def _term_pattern(term):
    pattern = r"\s+".join(re.escape(part) for part in term.split())
    if term.isascii():
        pattern = r"(?<![a-z0-9])" + pattern + r"(?![a-z0-9])"
    return re.compile(pattern, re.I), not term.isascii() and len(tokenize_text(term)) <= 1


def locate_terms(text: str, terms: list[str], *, segments=None) -> list[dict]:
    """Offsets and quotes always address the supplied source, never normalized text."""
    thai_spans = _thai_spans(text)
    matches = {}
    for term in dict.fromkeys(terms):
        if not term:
            continue
        pattern, require_token = _term_pattern(term)
        for match in pattern.finditer(text):
            if require_token and (match.start(), match.end()) not in thai_spans:
                continue
            matches[match.span()] = match
    aligned, cursor = [], 0
    for segment in valid_segments(segments):
        start = text.find(segment["text"], cursor)
        if start < 0:
            continue
        cursor = start + len(segment["text"])
        aligned.append((start, cursor, segment))
    result, previous_end = [], -1
    # Prefer the longest alias at a position, so "battery life" is not two mentions.
    for (start, end), match in sorted(matches.items(), key=lambda pair: (pair[0][0], -pair[0][1])):
        if start < previous_end:
            continue
        previous_end = end
        quote_start, quote_end = max(0, start - 65), min(len(text), end + 95)
        timed = next((s for a, b, s in aligned if a <= start and end <= b), None)
        result.append({"start_char": start, "end_char": end, "matched_text": match.group(),
                       "quote": text[quote_start:quote_end], "quote_start_char": quote_start,
                       "quote_end_char": quote_end,
                       "timestamp": {"start_seconds": timed["start"], "end_seconds": timed["end"],
                                     "precision": "segment", "segment_index": timed["segment_index"]} if timed else None})
    return result


def user_context(*, transcript: str, raw_transcript: str | None = None, stt_meta=None,
                 segments=None, classification=None, analysis_settings=None) -> dict:
    meta = stt_meta or {}
    source = meta.get("transcript_source") or "provided_text"
    unavailable = source in {"fallback_filename", "failed", "unavailable"} or not transcript.strip()
    partial = bool(meta.get("weak_audio") or meta.get("partial") or
                   meta.get("transcript_scope") in {"partial", "partial_clip"})
    return {"raw_transcript": raw_transcript if raw_transcript is not None else transcript,
            "cleaned_transcript": transcript, "source": source,
            "scope": meta.get("transcript_scope") or "provided_text",
            "availability": "unavailable" if unavailable else "partial" if partial else "available",
            "reason": (meta.get("fallback_reason") or "no_usable_transcript") if unavailable
                else "incomplete_or_weak_audio" if partial else None,
            "segments": valid_segments(segments) if not unavailable else [],
            "hook_seconds": meta.get("hook_seconds_analyzed"),
            "classification": classification or {}, "analysis_settings": analysis_settings or {}}


def freeze_reference(row) -> dict:
    try:
        metadata = json.loads(row.raw_metadata_json or "{}")
    except (ValueError, TypeError):
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    text = str(row.transcript or "")
    segments = valid_segments(metadata.get("transcript_segments")) if row.transcript_timestamps_available else []
    statistics = {key: getattr(row, key) for key in ("views", "likes", "comments")}
    raw_stats = metadata.get("statistics")
    if isinstance(raw_stats, dict):
        for key, provider_key in (("views", "viewCount"), ("likes", "likeCount"), ("comments", "commentCount")):
            # Older imports defaulted omitted counters to zero; do not present those as measured zeros.
            if statistics[key] == 0 and provider_key not in raw_stats:
                statistics[key] = None
    return {"dataset_id": row.dataset_id, "source_type": "dataset_transcript",
            "source_record_id": row.source_record_id, "video_id": row.source_youtube_id,
            "url": row.video_url or row.source_release_url, "title": row.title,
            "channel_id": row.source_channel_id, "channel_title": row.source_creator,
            "taxonomy_leaf_key": row.taxonomy_leaf_key, "data_split": row.data_split,
            "dataset_source": row.dataset_source, "dataset_version": row.dataset_version,
            "collection_run_id": row.collection_run_id,
            "transcript": text, "transcript_sha256": text_hash(text),
            "transcript_source": row.transcript_source, "segments": segments,
            "timestamps_available": bool(segments),
            "published_at": utc_isoformat(row.published_at),
            "statistics_captured_at": utc_isoformat(row.statistics_captured_at),
            "statistics": statistics,
            "statistics_source": "dataset_contents_at_analysis_time",
            "view_metric_version": row.view_metric_version,
            "duration_seconds": row.duration_seconds,
            "reviewed_at": utc_isoformat(row.reviewed_at),
            "source_archive_sha256": row.source_archive_sha256,
            "source_annotation_sha256": row.source_annotation_sha256}


def _observation(context: dict, aliases: list[str], *, hook=False) -> dict:
    if context["availability"] == "unavailable":
        return {"status": "unassessable", "reason": context["reason"], "occurrences": []}
    raw, cleaned = context["raw_transcript"], context["cleaned_transcript"]
    if hook:
        seconds = context.get("hook_seconds")
        if not context["segments"] or not isinstance(seconds, (int, float)) or seconds <= 0:
            return {"status": "unassessable", "reason": "no_timed_hook_transcript", "occurrences": []}
        timed_matches = locate_terms(raw, aliases, segments=context["segments"])
        occurrences = [m for m in timed_matches
                       if m["timestamp"] and m["timestamp"]["end_seconds"] <= seconds]
        # A segment crossing the boundary cannot locate a word inside the hook.
        uncertain_boundary = any(m["timestamp"] and m["timestamp"]["start_seconds"] < seconds
                                 < m["timestamp"]["end_seconds"] for m in timed_matches)
        cursor, aligned = 0, True
        for segment in context["segments"]:
            start = raw.find(segment["text"], cursor)
            if start < 0:
                aligned = False
                break
            cursor = start + len(segment["text"])
        if not occurrences and (not aligned or uncertain_boundary):
            return {"status": "unassessable", "reason": "unaligned_or_boundary_hook_segments", "occurrences": []}
        field = "raw_transcript"
    else:
        occurrences = locate_terms(raw, aliases, segments=context["segments"])
        field = "raw_transcript"
        if not occurrences and raw != cleaned:
            occurrences = locate_terms(cleaned, aliases)
            field = "cleaned_transcript"
    tokenizer_unavailable = word_tokenize is None and bool(re.search(r"[\u0e00-\u0e7f]", raw))
    status = "detected" if occurrences else "unassessable" if context["availability"] != "available" or tokenizer_unavailable else "not_detected"
    return {"status": status, "source_field": field, "occurrences": occurrences,
            "reason": ("thai_tokenizer_unavailable" if tokenizer_unavailable else context["reason"]) if status == "unassessable" else None}


def attach_evidence(result: dict, context: dict, *, keyword_domain: str) -> dict:
    profile = result["dataset_profile"]
    documents = profile.pop("_reference_documents", [])
    by_id = {doc["dataset_id"]: doc for doc in documents}
    lexicon = COMPARABLE_SYNONYMS_BY_DOMAIN.get(keyword_domain, {})
    keywords = {item["keyword"]: item for item in profile.get("top_keywords", [])}
    topics = []
    for keyword in dict.fromkeys([*lexicon, *keywords]):
        item = keywords.get(keyword, {})
        aliases = list(dict.fromkeys([keyword, *lexicon.get(keyword, ()), *item.get("matched_terms", [])]))
        supports = []
        for support in item.get("supporting_records", []):
            doc = by_id.get(support["dataset_id"])
            if doc is None:
                continue
            supports.append({"dataset_id": doc["dataset_id"], "frequency": support["frequency"],
                             "occurrences": support["occurrences"]})
        channels = sorted({by_id[s["dataset_id"]]["channel_id"] for s in supports
                           if by_id[s["dataset_id"]]["channel_id"]})
        topics.append({"topic_id": fingerprint([result["domain"], keyword])[:24],
                       "canonical_topic": keyword, "synonyms": aliases,
                       "source_type": "transcript", "user": _observation(context, aliases),
                       "user_hook": _observation(context, aliases, hook=True),
                       "support_count": len(supports), "channel_count": len(channels),
                       "channel_ids": channels, "sample_size": profile.get("sample_size", 0),
                       "supporting_dataset_row_ids": [s["dataset_id"] for s in supports],
                       "references": supports})
    by_topic = {topic["canonical_topic"]: topic for topic in topics}
    recommendations = []
    for field, kind in (("missing_keywords", "content_gap"), ("hook_keywords", "opening_suggestion"),
                        ("missing_dimensions", "content_dimension")):
        kept = []
        for item in result.get(field, []):
            topic = by_topic.get(item.get("keyword") or item.get("name"))
            if not topic or topic["user"]["status"] != "not_detected" or not topic["support_count"]:
                continue
            item["evidence_topic_id"] = topic["topic_id"]
            kept.append(item)
            recommendations.append({"kind": kind, "topic_id": topic["topic_id"],
                                    "basis": "whole_transcript_gap", "causal_engagement_claim": False})
        result[field] = kept
    if context["availability"] != "available" and result.get("status") != "withheld_unknown":
        result["status"] = "withheld_input_unassessable"
        result["current_trend_ideas"] = {"status": "insufficient_user_evidence", "ideas": []}
    bundle = {"schema_version": SCHEMA_VERSION, "method_version": METHOD_VERSION,
              "synonym_version": fingerprint(COMPARABLE_SYNONYMS_BY_DOMAIN),
              "generated_at": utc_isoformat(datetime.utcnow()), "taxonomy_leaf_key": result["domain"],
              "input": {**context, "raw_transcript_sha256": text_hash(context["raw_transcript"]),
                        "cleaned_transcript_sha256": text_hash(context["cleaned_transcript"])},
              "selection_rule": profile.get("selection_rule", "none"),
              "canonicalization": "curated_synonyms" if lexicon else "surface_terms_only",
              "reference_documents": documents, "topics": topics, "recommendations": recommendations,
              "duration": {"method": "median_and_percentiles", "result": result["recommended_duration"],
                           "dataset_row_ids": profile.get("duration_dataset_row_ids", [])},
              "current_trend_ideas": result.get("current_trend_ideas", {}),
              "metadata_is_transcript": False, "causal_engagement_claim": False}
    bundle["data_fingerprint"] = fingerprint({"references": documents, "input": context,
                                               "trends": bundle["current_trend_ideas"]})
    result["evidence_bundle"] = bundle
    return result
