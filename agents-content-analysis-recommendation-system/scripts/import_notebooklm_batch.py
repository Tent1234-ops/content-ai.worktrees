"""Audit a web-parser export; optionally enqueue candidates, never approve or train."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.database.db import SessionLocal
from app.database.models import ClassificationModel, DatasetContent, SystemLog, User
from app.services.dataset_contract import channel_dataset_split
from app.services.model_management import training_dataset
from app.services.training_transcript import normalize_training_transcript, training_transcript_sha256
from app.services.youtube_cc_dataset import (
    YouTubeCCDatasetError, _dedup_catalog, _youtube_get,
    create_notebooklm_transcript_candidate, extract_youtube_video_id,
)


def audit_entries(db, entries: list[dict]) -> tuple[list[dict], dict]:
    video_ids, hashes, _, catalog = _dedup_catalog(db, exclude_run_id=-1)
    existing = {row.source_youtube_id: row for row in db.query(DatasetContent).all()
                if row.source_youtube_id}
    seen_ids, seen_hashes = {}, {}
    rows = []
    for entry in entries:
        row = {key: entry.get(key) for key in ("path", "leaf_key", "title", "source_url")}
        rows.append(row)
        row["status"] = "invalid"
        if entry.get("status") != "parsed":
            row["reason"] = entry.get("error") or "Markdown could not be parsed"
            continue
        try:
            if entry.get("leaf_key") not in {"phone", "camera", "laptop", "unknown"}:
                raise ValueError("Unsupported proposed category")
            video_id = extract_youtube_video_id(entry.get("source_url"))
            row["video_id"] = video_id
            declared = entry.get("declared_video_id")
            if declared and declared != video_id:
                raise ValueError("Declared Video ID differs from the source URL")
            transcript = normalize_training_transcript(entry.get("transcript"))
        except (YouTubeCCDatasetError, ValueError) as exc:
            row["reason"] = str(exc)
            continue
        digest = training_transcript_sha256(transcript)
        row.update(transcript_sha256=digest, transcript_characters=len(transcript))
        if video_id in seen_ids or digest in seen_hashes:
            row.update(status="duplicate_in_batch", duplicate_of=seen_ids.get(video_id) or seen_hashes[digest])
        elif video_id in video_ids:
            row.update(status="duplicate_video", reason="Video already in dataset or collection artifacts")
            if video_id in existing:
                old = existing[video_id]
                row.update(existing_dataset_id=old.dataset_id, existing_leaf=old.taxonomy_leaf_key,
                           existing_split=old.data_split)
        elif digest in hashes:
            row.update(status="duplicate_transcript", reason="Transcript already in dataset or collection artifacts")
        else:
            row["status"] = "needs_metadata"
        seen_ids.setdefault(video_id, entry["path"])
        seen_hashes.setdefault(digest, entry["path"])
    return rows, catalog


def attach_metadata(db, rows: list[dict], *, api_key: str, getter=_youtube_get) -> dict:
    from app.services.dataset_split_plan import load_split_registry
    overrides = load_split_registry(db)["overrides"]
    pending = [row for row in rows if row["status"] == "needs_metadata"]
    metadata = {}
    # Fetch real metadata once in batches, then reuse it with the existing importer.
    for start in range(0, len(pending), 50):
        group = pending[start:start + 50]
        requested = {row["video_id"] for row in group}
        payload = getter("videos", api_key=api_key, timeout_seconds=20.0,
                         part="snippet,contentDetails,statistics,status",
                         id=",".join(row["video_id"] for row in group), maxResults=50)
        for item in payload.get("items") or []:
            if item.get("id") in requested:
                metadata[item["id"]] = item
    existing_splits = defaultdict(set)
    for channel_id, split in db.query(DatasetContent.source_channel_id, DatasetContent.data_split).all():
        if channel_id and split:
            existing_splits[channel_id].add(split)
    for row in pending:
        item = metadata.get(row["video_id"])
        if item is None:
            row.update(status="metadata_unavailable", reason="YouTube did not return this Video ID")
            continue
        snippet = item.get("snippet") or {}
        channel_id = snippet.get("channelId")
        if not channel_id:
            row.update(status="metadata_unavailable", reason="YouTube channel ID is missing")
            continue
        split, _ = channel_dataset_split(channel_id, overrides=overrides)
        row.update(channel_id=channel_id, channel_title=snippet.get("channelTitle"),
                   youtube_title=snippet.get("title"), data_split=split,
                   existing_channel_splits=sorted(existing_splits[channel_id]))
        if any(old != split for old in existing_splits[channel_id]):
            row.update(status="split_conflict", reason="Existing channel split differs; manual investigation required")
        else:
            row["status"] = "ready_for_review_import"
    return metadata


def enqueue_entries(db, entries, rows, metadata, *, api_key, admin_user_id,
                    artifact_root=None, importer=create_notebooklm_transcript_candidate):
    admin = db.get(User, admin_user_id)
    if admin is None or admin.role != "admin" or not admin.is_active:
        raise ValueError("--admin-user-id must identify an active admin")
    by_path = {entry["path"]: entry for entry in entries}
    if len(by_path) != len(entries):
        raise ValueError("Export contains duplicate source paths")
    runs = {}

    def cached_getter(resource, **kwargs):
        video_id = kwargs.get("id")
        if resource != "videos" or video_id not in metadata:
            raise YouTubeCCDatasetError("Import metadata cache miss")
        return {"items": [metadata[video_id]]}

    for row in rows:
        if row["status"] != "ready_for_review_import":
            continue
        entry = by_path[row["path"]]
        leaf = row["leaf_key"]
        try:
            result = importer(db, api_key=api_key, video_url=entry["source_url"],
                              transcript=entry["transcript"], proposed_leaf_key=leaf,
                              collection_run_id=runs.get(leaf), youtube_getter=cached_getter,
                              artifact_root=artifact_root)
        except YouTubeCCDatasetError as exc:
            db.rollback()
            row.update(status="import_rejected", reason=str(exc))
            continue
        runs[leaf] = result["collection_run_id"]
        row.update(status="pending_review", collection_run_id=result["collection_run_id"])
        db.add(SystemLog(user_id=admin_user_id, action="notebooklm_candidate_created", status="success",
                         detail=f"Local batch: video={row['video_id']}; run={runs[leaf]}; leaf={leaf}; source={row['path']}"))
        db.commit()
    return runs


def summarize(rows):
    return {leaf: {"files": len(group), "statuses": dict(Counter(row["status"] for row in group)),
                   "new_splits": dict(Counter(row["data_split"] for row in group
                                              if row["status"] in {"ready_for_review_import", "pending_review"}))}
            for leaf in sorted({row["leaf_key"] for row in rows})
            for group in [[row for row in rows if row["leaf_key"] == leaf]]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON from tool/export_notebooklm_batch.dart")
    parser.add_argument("--output", required=True, type=Path, help="New report JSON path; never overwrites")
    parser.add_argument("--fetch-metadata", action="store_true", help="Read YouTube metadata; no database writes")
    parser.add_argument("--apply", action="store_true", help="Create pending review candidates ONLY")
    parser.add_argument("--admin-user-id", type=int)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; choose a new report path")
    if args.apply and not args.admin_user_id:
        parser.error("--apply requires --admin-user-id")
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "notebooklm-local-batch-v1":
        parser.error("Unsupported export format")
    entries = payload["items"]
    report = {"created_at": datetime.now(timezone.utc).isoformat(),
              "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
              "mode": "pending_review_import" if args.apply else "audit_only",
              "auto_approved": False, "trained": False, "activated": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the report before any side effect. Keep partial results on failure.
    with args.output.open("x", encoding="utf-8") as handle, SessionLocal() as db:
        try:
            before = training_dataset(db)
            report["eligible_before"] = before["collection_plan"]
            report["fingerprint_before"] = before["dataset_fingerprint"]
            report["active_models_before"] = [m.model_id for m in db.query(ClassificationModel).filter_by(is_active=True)]
            rows, catalog = audit_entries(db, entries)
            report.update(items=rows, catalog=catalog)
            if args.fetch_metadata or args.apply:
                metadata = attach_metadata(db, rows, api_key=settings.youtube_api_key)
                report["metadata_fetched_at"] = datetime.now(timezone.utc).isoformat()
                if args.apply:
                    report["import_runs"] = enqueue_entries(db, entries, rows, metadata,
                                                          api_key=settings.youtube_api_key,
                                                          admin_user_id=args.admin_user_id)
            after = training_dataset(db)
            report.update(eligible_after=after["collection_plan"], fingerprint_after=after["dataset_fingerprint"],
                          active_models_after=[m.model_id for m in db.query(ClassificationModel).filter_by(is_active=True)])
            report["summary"] = summarize(rows)
        except Exception as exc:
            db.rollback()
            # Never persist API URLs or secrets from third-party exceptions.
            report["failure_type"] = type(exc).__name__
            raise
        finally:
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    print(json.dumps({"report": str(args.output), "summary": report["summary"],
                      "active_models": report["active_models_after"],
                      "training_dataset_unchanged": report["fingerprint_before"] == report["fingerprint_after"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
