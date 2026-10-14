"""Audit original format evidence and count-only coverage; never write the DB."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

os.environ.setdefault("CONTENT_AI_SKIP_DB_BOOTSTRAP", "1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_outcome_incoming_transcripts import fetch_metadata  # noqa: E402
from scripts.prepare_outcome_data_review import write_csv, write_json  # noqa: E402
from app.services.outcome_dataset import database_source_records  # noqa: E402
from app.services.outcome_prediction_readiness import (  # noqa: E402
    _age_bucket, data_use_gate, database_identity, reject_database_writes, validate_protocol,
)
from app.services.training_transcript import normalize_training_transcript, training_transcript_sha256  # noqa: E402
from app.services.youtube_cc_dataset import (  # noqa: E402
    YouTubeCCDatasetError, extract_youtube_video_id, parse_iso8601_duration,
)

POLICY_URL = "https://support.google.com/youtube/answer/15424877?hl=en"
AGES = ("age_0_7d", "age_7_30d", "age_30_90d", "age_90_365d", "age_365d_plus")
CATEGORIES = ("phone", "camera", "laptop")


def source_index(entries: list[dict]) -> dict:
    result = defaultdict(list)
    for entry in entries:
        if entry.get("status") != "parsed":
            continue
        try:
            video_id = extract_youtube_video_id(entry.get("source_url"))
            declared = entry.get("declared_video_id")
            if declared and declared != video_id:
                continue
            digest = training_transcript_sha256(normalize_training_transcript(entry["transcript"]))
        except (ValueError, KeyError, YouTubeCCDatasetError):
            continue
        url = urlsplit(entry["source_url"])
        short_link = (url.hostname in {"youtube.com", "www.youtube.com", "m.youtube.com"}
                      and url.path.rstrip("/") == f"/shorts/{video_id}")
        result[video_id].append({"path": entry["path"], "source_url": entry["source_url"],
                                 "transcript_sha256": digest, "original_shorts_link": short_link})
    return result


def assess_format(record: dict, sources: list[dict], api_item: dict) -> dict:
    matching = [s for s in sources if s["transcript_sha256"] == record["transcript_sha256"]]
    short_sources = [s for s in matching if s["original_shorts_link"]]
    duration_value = (api_item.get("contentDetails") or {}).get("duration")
    duration = parse_iso8601_duration(duration_value) if duration_value else None
    valid_api = api_item.get("id") == record["source_youtube_id"]
    status, content_format = "unresolved", "unknown"
    reasons = []
    if not valid_api or not duration or duration <= 0:
        reasons.append("live_api_metadata_missing_or_invalid")
    elif short_sources and duration > 180:
        reasons.append("original_shorts_link_conflicts_with_official_max_duration")
    elif short_sources:
        content_format, status = "short_form", "documented_original_shorts_url_and_transcript_match"
    elif duration > 180:
        # One-way exclusion under the dated official rule, never <=180 => Shorts.
        content_format, status = "long_form", "inferred_from_api_duration_exceeding_official_shorts_max"
    else:
        reasons.append("short_duration_is_not_format_evidence")
        if sources and not matching:
            reasons.append("original_transcript_identity_not_matched")
    return {"proposed_format": content_format, "format_evidence_status": status,
            "format_reason_codes": reasons, "current_api_duration_seconds": duration,
            "matching_source_files": matching, "original_shorts_source_files": short_sources,
            "policy_url": POLICY_URL if content_format == "long_form" else None,
            "policy_review_date": "2026-10-12" if content_format == "long_form" else None,
            "direct_platform_is_short_flag_observed": False,
            "database_format_unchanged": record["confirmed_format"]}


def count_coverage(rows: list[dict], incoming: list[dict], protocol: dict, as_of: datetime) -> list[dict]:
    minimum = protocol["context_support"]
    result = []
    for category in CATEGORIES:
        for age in AGES:
            new_rows = [r for r in incoming if r["category"] == category and r.get("published_at")
                        and _age_bucket(datetime.fromisoformat(r["published_at"].replace("Z", "+00:00")), as_of)[0] == age]
            candidates = [r for r in rows if r["category"] == category and r["actual_observation_age"] == age
                          and r["countable_metadata_and_text"]]
            members = [r for r in candidates if r["proposed_format"] == "long_form"]
            unknown_fit = [r for r in candidates if r["proposed_format"] == "unknown" and r["outcome_role"] == "fit"]
            metrics = sorted({r["view_metric_version"] for r in members + unknown_fit}) or ["no_existing_observation_cell"]
            for metric in metrics:
                group = [r for r in members if r["view_metric_version"] == metric]
                fit = [r for r in group if r["outcome_role"] == "fit"]
                tuning = [r for r in group if r["outcome_role"] == "tuning"]
                n = len({r["video_id"] for r in fit})
                c = len({r["channel_id"] for r in fit})
                need_v = max(0, minimum["minimum_fit_videos"] - n)
                need_c = max(0, minimum["minimum_fit_channels"] - c)
                unresolved = [r for r in unknown_fit if r["view_metric_version"] == metric]
                optimistic_v = len({r["video_id"] for r in fit + unresolved})
                optimistic_c = len({r["channel_id"] for r in fit + unresolved})
                result.append({"category": category, "age_context": age,
                               "format": "long_form", "view_metric_version": metric,
                               "fit_videos": n, "fit_channels": c,
                               "tuning_videos": len({r["video_id"] for r in tuning}),
                               "tuning_channels": len({r["channel_id"] for r in tuning}),
                               "new_batch_planning_age_videos_not_observations": len(new_rows),
                               "new_batch_no_old_channel_overlap_not_qualified": sum(
                                   bool(r.get("channel_id")) and not r["existing_channel_overlap"]
                                   and r["dedup_status"] == "needs_metadata" and not r["missing_caption_notice"]
                                   for r in new_rows),
                               "missing_fit_videos": need_v, "missing_fit_channels": need_c,
                               "fit_slots_to_fill_from_reviewed_or_new_data": max(need_v, need_c),
                               "unresolved_format_fit_videos": len({r["video_id"] for r in unresolved}),
                               "remaining_fit_slots_if_all_unknown_prove_regular": max(
                                   0, minimum["minimum_fit_videos"] - optimistic_v,
                                   minimum["minimum_fit_channels"] - optimistic_c),
                               "count_minimums_met": need_v == 0 and need_c == 0,
                               "probability_qualified": False})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-export", type=Path, required=True)
    parser.add_argument("--incoming-report", type=Path, required=True)
    parser.add_argument("--expected-review", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--fetch-metadata", action="store_true")
    sources.add_argument("--metadata-file", type=Path)
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("Output directory must be new")
    export = json.loads(args.source_export.read_text(encoding="utf-8"))
    incoming = json.loads(args.incoming_report.read_text(encoding="utf-8"))
    expected = json.loads(args.expected_review.read_text(encoding="utf-8"))
    expected_ids = {r["dataset_id"] for r in expected["records"] if r["queue"] == "development_review"}
    index = source_index(export["items"])
    protocol = json.loads((ROOT / "docs/implementation/outcome-prediction-protocol-v1.json").read_text(encoding="utf-8"))
    rights = json.loads((ROOT / "docs/implementation/outcome-prediction-data-use-v1.json").read_text(encoding="utf-8"))
    if not validate_protocol(protocol)["valid"] or not data_use_gate(rights, "audit")["allowed"]:
        parser.error("Audit permission or protocol invalid")
    from app.core.config import settings
    from app.database.db import SessionLocal, engine
    as_of = datetime.now(timezone.utc)
    with reject_database_writes(engine), SessionLocal() as db:
        before = database_identity(db)
        records = [r for r in database_source_records(db, cutoff=as_of, protocol=protocol, repo_root=ROOT)
                   if r["dataset_id"] in expected_ids]
        if {r["dataset_id"] for r in records} != expected_ids or any(r["source_split"] != "train" for r in records):
            raise ValueError("Candidate identities/splits changed; do not silently audit a different cohort")
        after = database_identity(db)
        db.rollback()
    if before != after:
        raise ValueError("Database changed during audit")
    if args.fetch_metadata:
        metadata = {"checked_at": datetime.now(timezone.utc).isoformat(),
                    "items": fetch_metadata([r["source_youtube_id"] for r in records], api_key=settings.youtube_api_key)}
    else:
        metadata = json.loads(args.metadata_file.read_text(encoding="utf-8"))
    rows = []
    for r in records:
        api_item = metadata["items"].get(r["source_youtube_id"], {})
        assessment = assess_format(r, index.get(r["source_youtube_id"], []), api_item)
        observation = r.get("observation") or {}
        issues = set(r["exclusion_reasons"])
        count_issues = issues - {"confirmed_format_missing", "sampling_frame_not_confirmed"}
        snippet = api_item.get("snippet") or {}
        if snippet.get("channelId") != r["source_channel_id"]:
            count_issues.add("channel_identity_changed_or_unavailable")
        if snippet.get("publishedAt") and datetime.fromisoformat(snippet["publishedAt"].replace("Z", "+00:00")) != datetime.fromisoformat(r["published_at"].replace("Z", "+00:00")):
            count_issues.add("published_at_changed")
        row = {"dataset_id": r["dataset_id"], "video_id": r["source_youtube_id"],
               "source_url": r["source_url"], "title": snippet.get("title"), "category": r["accepted_category"],
               "channel_id": r["source_channel_id"], "source_split_unchanged": r["source_split"],
               "outcome_role": r["outcome_role"], "transcript_sha256": r["transcript_sha256"],
               "published_at": r["published_at"], "observation_id": observation.get("observation_id"),
               "observed_at": observation.get("observed_at"), "actual_observation_age": r["frozen_age_context"],
               "view_metric_version": observation.get("view_metric_version"),
               "metadata_checked_at": metadata["checked_at"],
               "countable_metadata_and_text": not count_issues and bool(observation),
               "count_exclusion_reasons": sorted(count_issues),
               "all_training_exclusion_reasons_unchanged": sorted(issues), **assessment}
        rows.append(row)
    coverage = count_coverage(rows, incoming["records"], protocol, as_of)
    summary = {category: {
        "videos": len([r for r in rows if r["category"] == category]),
        "proposed_formats": dict(Counter(r["proposed_format"] for r in rows if r["category"] == category)),
        "evidence_statuses": dict(Counter(r["format_evidence_status"] for r in rows if r["category"] == category)),
    } for category in CATEGORIES}
    report = {"schema_version": "outcome-format-coverage-audit-v1", "as_of": as_of.isoformat(),
              "source_export_sha256": hashlib.sha256(args.source_export.read_bytes()).hexdigest(),
              "incoming_report_sha256": hashlib.sha256(args.incoming_report.read_bytes()).hexdigest(),
              "protocol_sha256": protocol["protocol_sha256"],
              "database_unchanged": True, "database_identity_before": before, "database_identity_after": after,
              "summary": summary, "records": rows, "regular_video_count_coverage": coverage,
              "new_batch_is_planning_only_no_outcome_observations": True,
              "labels_computed": False, "trained": False, "format_saved_to_database": False,
              "format_inference_policy": {"version": "format-evidence-audit-20261012-v1", "official_source": POLICY_URL,
                                         "shorts_max_seconds": 180, "short_duration_alone_proves_short": False,
                                         "long_result_is_policy_inference_not_direct_platform_flag": True,
                                         "short_result_requires_original_url_and_transcript_hash_match": True},
              "qualification_blockers": ["sampling_not_confirmed", "data_use_unverified", "label_balance_unassessed",
                                         "joint_topic_support_unassessed", "calibration_and_independent_evaluation_pending"],
              "exact_new_collection_total": None}
    args.output_dir.mkdir(parents=True, exist_ok=False)
    write_json(args.output_dir / "report.json", report)
    write_json(args.output_dir / "metadata-no-outcomes.json", metadata)
    flat = [{k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in r.items()} for r in rows]
    write_csv(args.output_dir / "format-review.csv", flat, list(flat[0]))
    write_csv(args.output_dir / "regular-video-coverage.csv", coverage, list(coverage[0]))
    write_csv(args.output_dir / "unresolved-format.csv", [r for r in flat if r["proposed_format"] == "unknown"], list(flat[0]))
    print(json.dumps({"database_unchanged": True, "summary": summary,
                      "count_supported_cells": sum(r["count_minimums_met"] for r in coverage)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
        raise SystemExit(2) from None
