"""Read-only incoming transcript review, without outcomes, splits or imports."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

os.environ.setdefault("CONTENT_AI_SKIP_DB_BOOTSTRAP", "1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.import_notebooklm_batch import audit_entries  # noqa: E402
from scripts.prepare_outcome_data_review import write_csv, write_json  # noqa: E402
from app.services.outcome_dataset import database_source_records  # noqa: E402
from app.services.outcome_prediction_readiness import (  # noqa: E402
    _age_bucket, data_use_gate, database_identity, reject_database_writes,
)
from app.services.youtube_cc_dataset import _youtube_get, parse_iso8601_duration  # noqa: E402


def transcript_review(text: str) -> dict:
    text = str(text or "").strip()
    letters = [c for c in text if c.isalpha()]
    thai = sum("\u0e00" <= c <= "\u0e7f" for c in letters)
    ratio = thai / len(letters) if letters else 0.0
    notice = bool(re.match(
        r"^[\[(]?\s*(no usable captions found|no transcript|transcript (unavailable|not available)|"
        r"caption unavailable|ไม่พบคำบรรยาย|ไม่มีคำบรรยาย|ไม่พบ\s*transcript)", text, re.I,
    ))
    return {
        "transcript_characters": len(text),
        "thai_letter_ratio": round(ratio, 4),
        "missing_caption_notice": notice,
        "language_review_required": bool(letters) and ratio < 0.1 and not notice,
        "fullness_review_required": True,
        "fullness_confirmed": False,
    }


def fetch_metadata(video_ids: list[str], *, api_key: str, getter=_youtube_get) -> dict:
    result = {}
    ids = sorted(set(video_ids))
    for offset in range(0, len(ids), 50):
        group = ids[offset:offset + 50]
        payload = getter(
            "videos", api_key=api_key, timeout_seconds=20,
            part="snippet,contentDetails",
            fields="items(id,snippet(title,channelId,channelTitle,publishedAt,defaultAudioLanguage),contentDetails(duration,caption))",
            id=",".join(group), maxResults=50,
        )
        for item in payload.get("items") or []:
            if item.get("id") in group:
                result[item["id"]] = item
    return result


def build_review(entries: list[dict], audits: list[dict], metadata: dict,
                 existing_channels: dict, *, checked_at: datetime,
                 owner_format: str | None = None, owner_format_statement: str = "") -> list[dict]:
    if owner_format and (owner_format not in {"short_form", "long_form"} or not owner_format_statement.strip()):
        raise ValueError("Owner format confirmation requires a supported format and statement")
    entries_by_path = {e["path"]: e for e in entries}
    rows = []
    for audit in audits:
        entry = entries_by_path[audit["path"]]
        item = metadata.get(audit.get("video_id")) or {}
        snippet = item.get("snippet") or {}
        details = item.get("contentDetails") or {}
        published = snippet.get("publishedAt")
        age, days = _age_bucket(datetime.fromisoformat(published.replace("Z", "+00:00")) if published else None, checked_at)
        channel = snippet.get("channelId")
        previous = existing_channels.get(channel, [])
        quality = transcript_review(entry.get("transcript") or "")
        rows.append({
            "path": audit["path"], "category": entry["leaf_key"],
            "video_id": audit.get("video_id"), "source_url": entry.get("source_url"),
            "file_title": entry.get("title"), "youtube_title": snippet.get("title"),
            "dedup_status": audit["status"],
            "existing_dataset_id": audit.get("existing_dataset_id"),
            "channel_id": channel, "channel_title": snippet.get("channelTitle"),
            "existing_channel_dataset_ids": "|".join(str(r["dataset_id"]) for r in previous),
            "existing_channel_splits": "|".join(sorted({r["split"] or "unknown" for r in previous})),
            "existing_channel_overlap": bool(previous),
            "published_at": published,
            "duration_seconds": parse_iso8601_duration(details["duration"]) if details.get("duration") else None,
            "audio_language_from_api": snippet.get("defaultAudioLanguage"),
            "caption_available_from_api": details.get("caption"),
            "metadata_checked_at": checked_at.isoformat(),
            "age_days_at_metadata_check_not_statistics": round(days, 3) if days is not None else None,
            "projected_age_context_not_statistics": age,
            "confirmed_format": owner_format or "unknown",
            "format_evidence_type": "owner_statement" if owner_format else "unconfirmed",
            "format_owner_statement": owner_format_statement if owner_format else "",
            "format_evidence_to_fill": "",
            "sampling_method_to_confirm": "",
            "full_transcript_review_notes": "",
            **quality,
            "ready_for_outcome_holdout": False,
        })
    return rows


def summarize(rows: list[dict]) -> dict:
    result = {}
    for category in ("phone", "camera", "laptop"):
        members = [r for r in rows if r["category"] == category]
        result[category] = {
            "files": len(members),
            "dedup_statuses": dict(Counter(r["dedup_status"] for r in members)),
            "metadata_returned": sum(bool(r["published_at"]) for r in members),
            "unique_channels": len({r["channel_id"] for r in members if r["channel_id"]}),
            "existing_channel_overlap_videos": sum(r["existing_channel_overlap"] for r in members),
            "no_existing_channel_overlap_and_new_video": sum(
                bool(r["channel_id"]) and not r["existing_channel_overlap"]
                and r["dedup_status"] == "needs_metadata" and not r["missing_caption_notice"] for r in members),
            "missing_caption_notices": sum(r["missing_caption_notice"] for r in members),
            "language_review_required": sum(r["language_review_required"] for r in members),
            "owner_confirmed_format_count": sum(r["format_evidence_type"] == "owner_statement" for r in members),
            "projected_age_counts_not_statistics": dict(Counter(r["projected_age_context_not_statistics"] for r in members)),
            "ready_for_outcome_holdout": 0,
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Existing web parser export")
    parser.add_argument("--output-dir", type=Path, required=True)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--fetch-metadata", action="store_true")
    source.add_argument("--metadata-file", type=Path, help="Reuse a previous audit's metadata without API calls")
    parser.add_argument("--metadata-checked-at", help="Original metadata capture time, required with --metadata-file")
    parser.add_argument("--owner-confirmed-format", choices=["short_form", "long_form"])
    parser.add_argument("--owner-format-statement", default="")
    parser.add_argument("--owner-sampling-statement", default="")
    args = parser.parse_args()
    if bool(args.metadata_file) != bool(args.metadata_checked_at):
        parser.error("Cached metadata requires its original capture timestamp")
    if args.owner_confirmed_format and not args.owner_format_statement.strip():
        parser.error("Owner format confirmation requires the actual statement")
    if args.output_dir.exists():
        parser.error("Refusing to overwrite an audit directory")
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "notebooklm-local-batch-v1":
        parser.error("Unsupported export schema")
    entries = payload["items"]
    rights = json.loads((ROOT / "docs/implementation/outcome-prediction-data-use-v1.json").read_text(encoding="utf-8"))
    if not data_use_gate(rights, "audit")["allowed"]:
        parser.error("Audit is not authorized")
    protocol = json.loads((ROOT / "docs/implementation/outcome-prediction-protocol-v1.json").read_text(encoding="utf-8"))
    from app.core.config import settings
    from app.database.db import SessionLocal, engine
    from app.database.models import DatasetContent

    checked_at = (datetime.fromisoformat(args.metadata_checked_at.replace("Z", "+00:00"))
                  if args.metadata_checked_at else datetime.now(timezone.utc))
    if checked_at.tzinfo is None:
        parser.error("Metadata capture time requires a timezone")
    with reject_database_writes(engine):
        with SessionLocal() as db:
            before = database_identity(db)
            audits, catalog = audit_entries(db, entries)
            channels = defaultdict(list)
            for row in db.query(DatasetContent).all():
                if row.source_channel_id:
                    channels[row.source_channel_id].append({"dataset_id": row.dataset_id, "split": row.data_split})
            source_records = database_source_records(db, cutoff=checked_at, protocol=protocol, repo_root=ROOT)
            after = database_identity(db)
            db.rollback()
    if before != after:
        raise SystemExit("Database changed during audit")
    metadata = (json.loads(args.metadata_file.read_text(encoding="utf-8")) if args.metadata_file else
                fetch_metadata([r["video_id"] for r in audits if r.get("video_id")],
                               api_key=settings.youtube_api_key) if args.fetch_metadata else {})
    rows = build_review(entries, audits, metadata, channels, checked_at=checked_at,
                        owner_format=args.owner_confirmed_format, owner_format_statement=args.owner_format_statement)
    old_coverage = []
    members = [r for r in source_records if r["source_split"] == "train" and r["transcript_scope"] == "full_video"]
    for r in members:
        age = _age_bucket(datetime.fromisoformat(r["published_at"].replace("Z", "+00:00")) if r.get("published_at") else None, checked_at)[0]
        old_coverage.append({"dataset_id": r["dataset_id"], "category": r["accepted_category"],
                             "channel_id": r["source_channel_id"], "role": r["outcome_role"],
                             "confirmed_format": r["confirmed_format"],
                             "projected_age_if_refreshed_not_statistics": age,
                             "published_at": r["published_at"], "supported_cell": False})
    report = {
        "checked_at": checked_at.isoformat(), "schema_version": "outcome-incoming-review-v1",
        "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "summary": summarize(rows), "records": rows,
        "database_unchanged": True, "database_identity_before": before, "database_identity_after": after,
        "metadata_requested": args.fetch_metadata,
        "owner_confirmation": {
            "scope": "Only incoming files in this exact input_sha256; not the existing training dataset",
            "format_statement": args.owner_format_statement,
            "sampling_statement": args.owner_sampling_statement,
            "sampling_frame": "unconfirmed",
            "does_not_confirm_full_transcripts_or_rights": True,
        },
        "outcome_statistics_requested": False, "labels_computed": False,
        "imported": False, "split_assigned": False, "trained": False,
        "limitations": ["File parsing is not transcript completeness verification",
                        "Duration and watch URLs do not confirm Shorts or regular video",
                        "Age at metadata check is not age at an outcome observation",
                        "No channel overlap is necessary but not sufficient for independence; creator and near-duplicate review still required",
                        "Sampling method, data use and all acceptance gates still apply"],
    }
    args.output_dir.mkdir(parents=True, exist_ok=False)
    write_json(args.output_dir / "report.json", report)
    write_json(args.output_dir / "metadata-no-outcomes.json", metadata)
    write_json(args.output_dir / "dedup-report.json", {"rows": audits, "catalog": catalog})
    write_csv(args.output_dir / "review.csv", rows, list(rows[0]) if rows else ["path"])
    write_csv(args.output_dir / "existing-development-age-coverage.csv", old_coverage,
              list(old_coverage[0]) if old_coverage else ["dataset_id"])
    print(json.dumps({"database_unchanged": True, "summary": report["summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
        raise SystemExit(2) from None
