"""Descriptive, channel-aware topic comparisons from frozen reference evidence."""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Iterable

import numpy as np
from scipy import __version__ as scipy_version
from scipy.stats import bootstrap
from sqlalchemy.orm import Session

from app.core.datetime_utils import utc_isoformat
from app.database.models import DatasetContent, ReferenceVideoStatistic
from app.services.actionable_recommendations import _aliases, template_catalog
from app.services.recommendation_evidence import fingerprint, freeze_reference, locate_terms, text_hash
from app.services.view_metrics import (YOUTUBE_PLAY_START_VIEW_V2, YOUTUBE_QUALIFIED_VIEW_V1,
                                      view_metrics_are_comparable)


SCHEMA_VERSION = "topic-comparison-evidence-v1"
METHOD_VERSION = "channel-stratified-descriptive-v2"
POLICY = {
    "version": "topic-comparison-policy-v2",
    "latest_observation_hours": 24,
    "growth_target_hours": 24,
    "growth_min_hours": 12,
    "growth_max_hours": 36,
    "age_buckets_days": [[0, 7], [7, 30], [30, 90], [90, 365], [365, None]],
    "duration_buckets_seconds": [[1, 180], [181, None]],
    "descriptive_min_videos_per_arm": 10,
    "descriptive_min_paired_channels": 5,
    "uncertainty_min_paired_channels": 10,
    "bootstrap_resamples": 2000,
    "bootstrap_confidence": 0.95,
    "bootstrap_method": "BCa",
    "bootstrap_seed": 260929,
    "primary_metric": "views",
}
LIMITATION_TH = (
    "เป็นความแตกต่างที่พบในคลิปอ้างอิงที่ระบบมี ไม่ได้พิสูจน์ว่าหัวข้อนี้เป็นสาเหตุ"
    "ของยอดวิว ไลก์ หรือความคิดเห็น และอาจยังมีความต่างของช่องหรือเนื้อหาที่ควบคุมไม่ได้"
)


def comparison_policy() -> dict:
    value = json.loads(json.dumps(POLICY))
    value["sha256"] = fingerprint(POLICY)
    return value


def _as_naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    return round(float(np.percentile(np.asarray(values, dtype=float), percentile)), 6)


def _summary(values: list[float]) -> dict:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    return {
        "count": len(finite),
        "median": round(float(median(finite)), 6) if finite else None,
        "p25": _percentile(finite, 25),
        "p75": _percentile(finite, 75),
    }


def _age_bucket(days: float) -> str | None:
    if not math.isfinite(days) or days < 0:
        return None
    if days < 7:
        return "age_0_7d"
    if days < 30:
        return "age_7_30d"
    if days < 90:
        return "age_30_90d"
    if days < 365:
        return "age_90_365d"
    return "age_365d_plus"


def _duration_bucket(seconds: int | None) -> str | None:
    if not isinstance(seconds, int) or isinstance(seconds, bool) or seconds <= 0:
        return None
    return "duration_1_180s" if seconds <= 180 else "duration_over_180s"


def _confirmed_format(row: DatasetContent) -> tuple[str, str | None]:
    """Only explicit reviewed/provider metadata may identify Shorts or long-form."""
    try:
        metadata = json.loads(row.raw_metadata_json or "{}")
    except (TypeError, ValueError):
        return "unknown", None
    if not isinstance(metadata, dict):
        return "unknown", None
    containers = [metadata]
    for key in ("raw_metadata", "video", "contentDetails"):
        if isinstance(metadata.get(key), dict):
            containers.append(metadata[key])
    for container in containers:
        for key in ("content_format", "video_format", "format"):
            raw = str(container.get(key) or "").strip().casefold().replace("-", "_")
            if raw in {"short", "shorts", "short_form", "shortform"}:
                return "short_form", f"raw_metadata.{key}"
            if raw in {"long", "long_form", "longform", "standard", "video"}:
                return "long_form", f"raw_metadata.{key}"
        raw_short = container.get("is_short")
        if isinstance(raw_short, bool):
            return ("short_form" if raw_short else "long_form"), "raw_metadata.is_short"
    return "unknown", None


def _load_observations(db: Session, dataset_ids: list[int], as_of: datetime) -> dict[int, list[ReferenceVideoStatistic]]:
    if not dataset_ids:
        return {}
    earliest = as_of - timedelta(
        hours=POLICY["latest_observation_hours"] + POLICY["growth_max_hours"]
    )
    rows = db.query(ReferenceVideoStatistic).filter(
        ReferenceVideoStatistic.dataset_id.in_(dataset_ids),
        ReferenceVideoStatistic.observed_at >= earliest,
        ReferenceVideoStatistic.observed_at <= as_of,
    ).order_by(
        ReferenceVideoStatistic.dataset_id,
        ReferenceVideoStatistic.observed_at,
        ReferenceVideoStatistic.observation_id,
    ).all()
    grouped: dict[int, list[ReferenceVideoStatistic]] = defaultdict(list)
    for row in rows:
        grouped[int(row.dataset_id)].append(row)
    return grouped


def _observation_dict(row: ReferenceVideoStatistic) -> dict:
    return {
        "observation_id": int(row.observation_id),
        "run_id": int(row.run_id),
        "video_id": row.video_id,
        "observed_at": utc_isoformat(row.observed_at),
        "status": row.status,
        "error_code": row.error_code,
        "view_metric_version": row.view_metric_version,
        "views": row.views,
        "likes": row.likes,
        "comments": row.comments,
    }


def _latest_observation(observations: list[ReferenceVideoStatistic], as_of: datetime):
    cutoff = as_of - timedelta(hours=POLICY["latest_observation_hours"])
    valid = [row for row in observations
             if row.status in {"complete", "partial"}
             and row.views is not None
             and cutoff <= row.observed_at <= as_of]
    return valid[-1] if valid else None


def _growth(observations: list[ReferenceVideoStatistic], latest: ReferenceVideoStatistic | None) -> dict:
    empty = {"status": "unavailable", "reason": "two_compatible_observations_required",
             "start": None, "end": _observation_dict(latest) if latest else None,
             "elapsed_hours": None, "views_delta": None, "views_per_hour": None}
    if latest is None:
        return empty
    candidates = []
    for earlier in observations:
        if earlier.observation_id == latest.observation_id or earlier.observed_at >= latest.observed_at:
            continue
        elapsed = (latest.observed_at - earlier.observed_at).total_seconds() / 3600
        if not POLICY["growth_min_hours"] <= elapsed <= POLICY["growth_max_hours"]:
            continue
        if earlier.status not in {"complete", "partial"} or earlier.views is None:
            continue
        if not view_metrics_are_comparable("youtube", latest.view_metric_version, earlier.view_metric_version):
            continue
        between = [row for row in observations
                   if earlier.observed_at < row.observed_at < latest.observed_at]
        if any(row.status not in {"complete", "partial"} or row.views is None or
               not view_metrics_are_comparable("youtube", latest.view_metric_version, row.view_metric_version)
               for row in between):
            continue
        sequence = sorted([earlier, *between, latest], key=lambda row: (row.observed_at, row.observation_id))
        if any(right.views < left.views for left, right in zip(sequence, sequence[1:])):
            if latest.views >= earlier.views:
                empty["reason"] = "intermediate_counter_correction"
                continue
        candidates.append((abs(elapsed - POLICY["growth_target_hours"]),
                           -int(earlier.observation_id), earlier, elapsed))
    if not candidates:
        return empty
    _, _, earlier, elapsed = min(candidates, key=lambda item: (item[0], item[1]))
    delta = int(latest.views) - int(earlier.views)
    status = "counter_correction" if delta < 0 else "observed_interval"
    return {
        "status": status,
        "reason": "counter_decreased" if delta < 0 else None,
        "start": _observation_dict(earlier),
        "end": _observation_dict(latest),
        "elapsed_hours": round(elapsed, 6),
        "views_delta": delta,
        "views_per_hour": round(delta / elapsed, 6) if delta >= 0 else None,
    }


def _record(row: DatasetContent, observations: list[ReferenceVideoStatistic], as_of: datetime,
            aliases: list[str]) -> tuple[dict, list[str]]:
    reasons = []
    if not row.source_youtube_id or not row.source_channel_id:
        reasons.append("missing_video_or_channel_identity")
    observations = [observation for observation in observations
                    if observation.video_id == row.source_youtube_id]
    doc = freeze_reference(row)
    text = str(row.transcript or "")
    current_text_hash = text_hash(text)
    occurrences = locate_terms(text, aliases, segments=doc.get("segments"))
    full_transcript = row.transcript_scope == "full_video"
    topic_status = ("unassessable" if not text.strip() or not full_transcript else
                    "detected" if occurrences else "not_detected")
    if not full_transcript:
        reasons.append("transcript_not_full_video")
    if str(row.transcript_sha256 or "") != current_text_hash:
        reasons.append("transcript_hash_mismatch")
    latest = _latest_observation(observations, as_of)
    if latest is None:
        reasons.append("no_recent_successful_observation")
    elif latest.view_metric_version not in {YOUTUBE_PLAY_START_VIEW_V2, YOUTUBE_QUALIFIED_VIEW_V1}:
        reasons.append("unknown_view_metric_version")
    published = _as_naive_utc(row.published_at)
    observed = _as_naive_utc(latest.observed_at) if latest else None
    age_days = ((observed - published).total_seconds() / 86400
                if observed is not None and published is not None else None)
    age_group = _age_bucket(age_days) if age_days is not None else None
    duration_group = _duration_bucket(row.duration_seconds)
    if age_group is None:
        reasons.append("invalid_publication_age")
    if duration_group is None:
        reasons.append("invalid_duration")
    if latest is not None and latest.views is not None and latest.views < 0:
        reasons.append("invalid_negative_views")
    format_group, format_source = _confirmed_format(row)
    metric_version = latest.view_metric_version if latest else None
    comparable = not reasons and topic_status != "unassessable"
    growth = _growth(observations, latest)
    views = int(latest.views) if latest and latest.views is not None else None
    likes = int(latest.likes) if latest and latest.likes is not None else None
    comments = int(latest.comments) if latest and latest.comments is not None else None
    metrics = {
        "views": float(views) if views is not None else None,
        "likes_per_1000_views": round(likes / views * 1000, 6) if likes is not None and views else None,
        "comments_per_1000_views": round(comments / views * 1000, 6) if comments is not None and views else None,
        "views_per_hour": growth["views_per_hour"],
    }
    if views == 0:
        reasons.append("zero_views_for_rate_metrics")
    return {
        "dataset_id": int(row.dataset_id), "video_id": row.source_youtube_id,
        "channel_id": row.source_channel_id, "channel_title": row.source_creator,
        "url": row.video_url or row.source_release_url,
        "taxonomy_leaf_key": row.taxonomy_leaf_key, "data_split": row.data_split,
        "dataset_source": row.dataset_source, "dataset_version": row.dataset_version,
        "collection_run_id": row.collection_run_id,
        "published_at": utc_isoformat(row.published_at), "duration_seconds": row.duration_seconds,
        "transcript_scope": row.transcript_scope,
        "transcript_sha256": current_text_hash, "topic_status": topic_status,
        "occurrences": occurrences[:3], "latest_observation": _observation_dict(latest) if latest else None,
        "growth": growth, "format_group": format_group, "format_source": format_source,
        "duration_group": duration_group, "age_group": age_group,
        "age_days_at_observation": round(age_days, 6) if age_days is not None else None,
        "view_metric_version": metric_version, "stratum": [row.taxonomy_leaf_key, format_group,
            duration_group, age_group, metric_version] if comparable else None,
        "metrics": metrics, "comparison_eligible": comparable,
        "exclusion_reasons": sorted(set(reasons)),
    }, reasons


def _bootstrap_interval(channel_differences: list[float]) -> dict:
    if len(channel_differences) < POLICY["uncertainty_min_paired_channels"]:
        return {"status": "uncertainty_unavailable", "reason": "insufficient_paired_channels",
                "low": None, "high": None}
    values = np.asarray(channel_differences, dtype=float)
    if not np.isfinite(values).all() or np.all(values == values[0]):
        return {"status": "uncertainty_unavailable", "reason": "degenerate_or_nonfinite_data",
                "low": None, "high": None}
    try:
        result = bootstrap((values,), np.median,
                           confidence_level=POLICY["bootstrap_confidence"],
                           n_resamples=POLICY["bootstrap_resamples"],
                           method=POLICY["bootstrap_method"],
                           rng=np.random.default_rng(POLICY["bootstrap_seed"]))
        low, high = float(result.confidence_interval.low), float(result.confidence_interval.high)
        if not math.isfinite(low) or not math.isfinite(high):
            raise ValueError("non-finite interval")
        return {"status": "available", "reason": None, "low": round(low, 6),
                "high": round(high, 6), "confidence": POLICY["bootstrap_confidence"],
                "method": POLICY["bootstrap_method"], "resamples": POLICY["bootstrap_resamples"],
                "seed": POLICY["bootstrap_seed"], "scipy_version": scipy_version}
    except (ValueError, RuntimeError, FloatingPointError):
        return {"status": "uncertainty_unavailable", "reason": "bootstrap_failed_or_degenerate",
                "low": None, "high": None}


def _metric_comparison(records: list[dict], metric: str) -> dict:
    grouped: dict[tuple, dict[str, list[dict]]] = defaultdict(lambda: {"detected": [], "not_detected": []})
    unavailable = Counter()
    for record in records:
        value = record["metrics"].get(metric)
        if not record["comparison_eligible"]:
            unavailable.update(record["exclusion_reasons"] or ["not_comparison_eligible"])
            continue
        if value is None:
            unavailable[f"missing_{metric}"] += 1
            continue
        key = (record["channel_id"], *record["stratum"])
        grouped[key][record["topic_status"]].append(record)

    matched_groups, detected_records, absent_records = [], {}, {}
    differences_by_channel: dict[str, list[float]] = defaultdict(list)
    for key, arms in grouped.items():
        if not arms["detected"] or not arms["not_detected"]:
            unavailable["stratum_has_one_arm_only"] += len(arms["detected"]) + len(arms["not_detected"])
            continue
        detected_values = [float(row["metrics"][metric]) for row in arms["detected"]]
        absent_values = [float(row["metrics"][metric]) for row in arms["not_detected"]]
        difference = float(median(detected_values) - median(absent_values))
        channel_id = str(key[0])
        differences_by_channel[channel_id].append(difference)
        for row in arms["detected"]:
            detected_records[row["video_id"]] = row
        for row in arms["not_detected"]:
            absent_records[row["video_id"]] = row
        matched_groups.append({
            "channel_id": channel_id, "stratum": list(key[1:]),
            "detected_video_ids": sorted({row["video_id"] for row in arms["detected"]}),
            "not_detected_video_ids": sorted({row["video_id"] for row in arms["not_detected"]}),
            "detected_median": round(float(median(detected_values)), 6),
            "not_detected_median": round(float(median(absent_values)), 6),
            "difference": round(difference, 6),
        })
    channel_rows = [{"channel_id": channel, "difference": round(float(median(values)), 6),
                     "matched_strata_count": len(values)}
                    for channel, values in sorted(differences_by_channel.items())]
    channel_differences = [row["difference"] for row in channel_rows]
    detected_values = [float(row["metrics"][metric]) for row in detected_records.values()]
    absent_values = [float(row["metrics"][metric]) for row in absent_records.values()]
    paired_channels = len(channel_rows)
    enough_descriptive = (len(detected_values) >= POLICY["descriptive_min_videos_per_arm"]
                          and len(absent_values) >= POLICY["descriptive_min_videos_per_arm"]
                          and paired_channels >= POLICY["descriptive_min_paired_channels"])
    interval = _bootstrap_interval(channel_differences) if enough_descriptive else {
        "status": "uncertainty_unavailable", "reason": "descriptive_minimum_not_met",
        "low": None, "high": None}
    main_difference = round(float(median(channel_differences)), 6) if channel_differences else None
    direction = ("higher" if main_difference is not None and main_difference > 0 else
                 "lower" if main_difference is not None and main_difference < 0 else
                 "equal" if main_difference == 0 else "unknown")
    if not matched_groups:
        status = "not_comparable"
    elif not enough_descriptive:
        status = "reference_only"
    elif interval["status"] != "available":
        status = "comparison_descriptive"
    elif interval["low"] <= 0 <= interval["high"]:
        status = "comparison_uncertain"
    else:
        status = "comparison_supported"
    return {
        "metric": metric, "status": status, "direction": direction,
        "unit": {"views": "views", "likes_per_1000_views": "likes_per_1000_views",
                 "comments_per_1000_views": "comments_per_1000_views",
                 "views_per_hour": "average_views_per_actual_hour"}[metric],
        "detected": {**_summary(detected_values), "video_ids": sorted(detected_records)},
        "not_detected": {**_summary(absent_values), "video_ids": sorted(absent_records)},
        "paired_channel_count": paired_channels, "matched_strata_count": len(matched_groups),
        "within_channel_median_difference": main_difference,
        "channel_differences": channel_rows, "matched_groups": matched_groups,
        "uncertainty": interval, "excluded": dict(sorted(unavailable.items())),
        "causal_claim": False, "limitation": LIMITATION_TH,
    }


def _deduplicate(rows: Iterable[DatasetContent]) -> tuple[list[DatasetContent], int]:
    selected = {}
    duplicates = 0
    for row in sorted(rows, key=lambda value: int(value.dataset_id)):
        key = str(row.source_youtube_id or f"row:{row.dataset_id}")
        if key in selected:
            duplicates += 1
            continue
        selected[key] = row
    return list(selected.values()), duplicates


def build_topic_comparisons(db: Session, result: dict, rows: Iterable[DatasetContent], *,
                            as_of: datetime | None = None) -> dict:
    as_of = _as_naive_utc(as_of) or datetime.utcnow()
    rows, duplicate_count = _deduplicate(rows)
    policy = comparison_policy()
    output = {"schema_version": SCHEMA_VERSION, "method_version": METHOD_VERSION,
              "policy": policy, "as_of": utc_isoformat(as_of), "status": "ready",
              "items": [], "reference_documents": [], "limitation": LIMITATION_TH}
    bundle = result.get("evidence_bundle") or {}
    action_topics = bundle.get("action_topics") or []
    if result.get("domain") == "unknown" or str(result.get("status") or "").startswith("withheld_"):
        output["status"] = str(result.get("status") or "withheld_unknown")
        return output
    if not rows or not action_topics:
        output["status"] = "no_reference_topics"
        return output
    observations = _load_observations(db, [int(row.dataset_id) for row in rows], as_of)
    output["reference_documents"] = [freeze_reference(row) for row in rows]
    templates = {template["key"]: template for template in
                 template_catalog()["categories"].get(result["domain"], [])}
    support_ids = set(result.get("dataset_profile", {}).get("dataset_row_ids", []))
    for topic in action_topics:
        canonical = str(topic.get("canonical_topic") or "")
        template = templates.get(canonical)
        aliases = list(topic.get("synonyms") or (_aliases(template, result["domain"]) if template else [canonical]))
        records, exclusions = [], Counter()
        for row in rows:
            record, reasons = _record(row, observations.get(int(row.dataset_id), []), as_of, aliases)
            records.append(record)
            exclusions.update(reasons)
        detected = [row for row in records if row["topic_status"] == "detected"]
        absent = [row for row in records if row["topic_status"] == "not_detected"]
        unassessable = [row for row in records if row["topic_status"] == "unassessable"]
        metrics = {metric: _metric_comparison(records, metric) for metric in
                   ("views", "likes_per_1000_views", "comments_per_1000_views", "views_per_hour")}
        output["items"].append({
            "evidence_topic_id": topic.get("topic_id"), "canonical_topic": canonical,
            "title_th": topic.get("title_th") or (template or {}).get("title") or canonical,
            "aliases": aliases, "alias_version": bundle.get("synonym_version"),
            "alias_sha256": fingerprint(aliases),
            "cohort": {"source": "all_same_category_reference_eligible_before_performance_filter",
                       "eligible_video_count": len(records), "support_cohort_video_count":
                       sum(record["dataset_id"] in support_ids for record in records),
                       "comparison_pool_video_count": sum(record["dataset_id"] not in support_ids for record in records),
                       "duplicate_video_rows_excluded": duplicate_count,
                       "detected_count": len(detected), "not_detected_count": len(absent),
                       "unassessable_count": len(unassessable), "exclusions": dict(sorted(exclusions.items()))},
            "records": records, "metrics": metrics, "causal_claim": False,
            "limitation": LIMITATION_TH,
        })
    if not any(item["records"] for item in output["items"]):
        output["status"] = "no_eligible_records"
    output["data_fingerprint"] = fingerprint({"policy": policy, "as_of": output["as_of"],
                                               "reference_documents": output["reference_documents"],
                                               "items": output["items"]})
    return output


def topic_comparison_readiness(db: Session, rows: Iterable[DatasetContent], *, domain: str,
                               as_of: datetime | None = None) -> dict:
    """Admin audit uses the production policy without creating an analysis result."""
    as_of = _as_naive_utc(as_of) or datetime.utcnow()
    rows, duplicate_count = _deduplicate(rows)
    observations = _load_observations(db, [int(row.dataset_id) for row in rows], as_of)
    topics = []
    for template in template_catalog()["categories"].get(domain, []):
        aliases = _aliases(template, domain)
        records = [_record(row, observations.get(int(row.dataset_id), []), as_of, aliases)[0]
                   for row in rows]
        view_metric = _metric_comparison(records, "views")
        topics.append({"key": template["key"], "title": template["title"],
                       "detected_count": sum(row["topic_status"] == "detected" for row in records),
                       "not_detected_count": sum(row["topic_status"] == "not_detected" for row in records),
                       "recent_statistics_count": sum(row["latest_observation"] is not None for row in records),
                       "paired_channel_count": view_metric["paired_channel_count"],
                       "views_status": view_metric["status"]})
    metadata = Counter()
    for row in rows:
        record = _record(row, observations.get(int(row.dataset_id), []), as_of, ["__never_match__"])[0]
        metadata.update(record["exclusion_reasons"])
    return {"policy_version": POLICY["version"], "policy_sha256": fingerprint(POLICY),
            "as_of": utc_isoformat(as_of), "eligible_video_count": len(rows),
            "duplicate_video_rows_excluded": duplicate_count,
            "channels": len({row.source_channel_id for row in rows if row.source_channel_id}),
            "metadata_or_statistics_gaps": dict(sorted(metadata.items())), "topics": topics,
            "representativeness_limitation": "คลิปอ้างอิงเป็นข้อมูลที่คัดเก็บ ไม่ใช่ตัวแทน YouTube ทั้งหมด"}
