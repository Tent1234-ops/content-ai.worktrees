"""Plan or atomically replace existing NotebookLM text, preserving dataset identity."""
from __future__ import annotations

import argparse
from collections import Counter
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

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.models import DatasetContent, SystemLog
from app.schemas.admin_report import AdminDatasetUpdate
from app.services.admin_report import update_admin_dataset
from app.services.outcome_prediction_readiness import reject_database_writes
from app.services.training_transcript import normalize_training_transcript, training_transcript_sha256
from app.services.youtube_cc_dataset import extract_youtube_video_id
from scripts.audit_outcome_incoming_transcripts import transcript_review


ALLOWED_CHANGES = {
    "transcript", "transcript_sha256", "reviewed_by", "reviewed_at",
    "review_notes", "raw_metadata_json",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def snapshot(row) -> dict:
    return json.loads(encode({c.name: getattr(row, c.name) for c in row.__table__.columns}))


def fingerprint(value) -> str:
    return digest(encode(value).encode("utf-8"))


def write_new(path: Path, value) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def load_entries(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "notebooklm-local-batch-v1":
        raise ValueError("Unsupported parser export")
    return payload["items"]


def prepare_record(entry: dict, rows: list, *, title_reviews: dict) -> dict:
    record = {k: entry.get(k) for k in ("path", "leaf_key", "title", "source_url")}
    record.update(status="blocked", reasons=[], warnings=[])
    try:
        if entry.get("status") != "parsed":
            raise ValueError("Markdown parser rejected the file")
        source = Path(entry["path"])
        record["source_file_sha256"] = digest(source.read_bytes())
        video_id = extract_youtube_video_id(entry["source_url"])
        record["video_id"] = video_id
        if video_id != entry.get("declared_video_id"):
            raise ValueError("Declared Video ID differs from source URL")
        if not re.fullmatch(r"transcript_" + re.escape(video_id) + r"(?:-v\d+)?\.md", source.name):
            raise ValueError("Filename does not identify the declared video")
        candidates = [r for r in rows if r.source_youtube_id == video_id]
        if len(candidates) != 1:
            raise ValueError("Expected exactly one existing dataset; no automatic inserts")
        row = candidates[0]
        record.update(dataset_id=row.dataset_id, before_fingerprint=fingerprint(snapshot(row)),
                      old_transcript_sha256=row.transcript_sha256, data_split=row.data_split,
                      old_characters=len(row.transcript or ""))
        if row.deleted_at is not None or not row.is_active:
            raise ValueError("Dataset is archived or inactive; no automatic restoration")
        if row.taxonomy_leaf_key != entry["leaf_key"]:
            raise ValueError("Folder category differs from existing dataset")
        if extract_youtube_video_id(row.video_url) != video_id:
            raise ValueError("Existing dataset source URL is inconsistent")
        if row.transcript_acquisition_method != "notebooklm_manual_source" or row.transcript_timestamps_available:
            raise ValueError("Timed or non-NotebookLM source needs a separate migration")
        body = normalize_training_transcript(entry["transcript"])
        record["new_transcript_sha256"] = training_transcript_sha256(body)
        record["quality"] = transcript_review(body)
        record["new_characters"] = len(body)
        if record["quality"]["missing_caption_notice"]:
            raise ValueError("Missing-caption notice is not a transcript")
        if row.language == "th" and record["quality"]["language_review_required"]:
            raise ValueError("Incoming transcript is not predominantly Thai; retain existing text")
        if Path(entry["path"]).stem.endswith("_partial") or re.search(r"(?m)^##\s+(?:Report|Summary)\b", entry["transcript"]):
            raise ValueError("Partial output or report text needs review")
        if any(r.dataset_id != row.dataset_id and r.transcript_sha256 == record["new_transcript_sha256"] for r in rows):
            raise ValueError("Incoming transcript duplicates a different dataset")

        old_title = str(row.title).strip()
        new_title = str(entry.get("title") or "").strip()
        if new_title == old_title:
            record["pairing_evidence"] = "video_id_and_exact_existing_title"
        elif new_title == old_title + " | " + str(row.source_creator):
            record["pairing_evidence"] = "video_id_and_title_with_channel_suffix"
            record["warnings"].append("File title adds channel; database title is preserved")
        else:
            review = title_reviews.get(video_id, {})
            prefix = re.sub(r"\s+", "", row.transcript or "")[:200]
            new_prefix = re.sub(r"\s+", "", body)[:200]
            if (review.get("source_file_sha256") != record["source_file_sha256"]
                    or review.get("dataset_id") != row.dataset_id or not review.get("reason")
                    or len(prefix) < 200 or prefix != new_prefix):
                raise ValueError("Title differs; requires hash-bound source-pairing review")
            record["pairing_evidence"] = review
            record["warnings"].append("Reviewed title difference; database title is preserved")
        if len(body) < len(row.transcript or ""):
            record["warnings"].append("New text is shorter; length is not a quality or completeness score")
        record["status"] = "unchanged" if body == row.transcript and record["new_transcript_sha256"] == row.transcript_sha256 else "ready"
    except (ValueError, OSError) as error:
        record["reasons"].append(str(error))
    return record


def build_plan(db: Session, entries: list[dict], *, title_reviews: dict | None = None) -> tuple[dict, dict]:
    rows = db.query(DatasetContent).order_by(DatasetContent.dataset_id).all()
    records = [prepare_record(e, rows, title_reviews=title_reviews or {}) for e in entries]
    for field in ("video_id", "new_transcript_sha256"):
        counts = Counter(r.get(field) for r in records if r.get(field))
        for record in records:
            if record.get(field) and counts[record[field]] > 1:
                record["status"] = "blocked"
                record["reasons"].append(f"Duplicate {field} inside replacement batch")
    plan = {
        "schema_version": "notebooklm-transcript-replacement-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_count_before": len(rows), "records": records,
        "summary": {leaf: dict(Counter(r["status"] for r in records if r["leaf_key"] == leaf))
                    for leaf in sorted({r["leaf_key"] for r in records})},
        "no_inserts_or_deletes": True, "full_video_accuracy_verified": False,
        "preserve_splits_and_existing_eligibility": True,
    }
    targets = {r["dataset_id"] for r in records if r.get("dataset_id")}
    return plan, {str(r.dataset_id): snapshot(r) for r in rows if r.dataset_id in targets}


def check_preserved(before: dict, after: dict) -> None:
    changed = {k for k in before if before[k] != after[k]}
    unexpected = changed - ALLOWED_CHANGES
    if unexpected:
        raise ValueError("Unexpected changed fields: " + ", ".join(sorted(unexpected)))


def apply_plan(engine, plan: dict, entries: list[dict], *, plan_id: str, backup: dict) -> dict:
    by_path = {e["path"]: e for e in entries}
    selected = sorted((r for r in plan["records"] if r["status"] == "ready"), key=lambda r: r["dataset_id"])
    for record in selected:
        if digest(Path(record["path"]).read_bytes()) != record["source_file_sha256"]:
            raise ValueError("Source file changed after planning")
        if digest(Path(record["source_snapshot_path"]).read_bytes()) != record["source_file_sha256"]:
            raise ValueError("Source snapshot changed after planning")
        body = normalize_training_transcript(by_path[record["path"]]["transcript"])
        if training_transcript_sha256(body) != record["new_transcript_sha256"]:
            raise ValueError("Parser export changed after planning")
        if fingerprint(backup[str(record["dataset_id"])]) != record["before_fingerprint"]:
            raise ValueError("Backup differs from plan")
    after_rows = {}
    with engine.begin() as connection:
        if connection.dialect.name == "sqlite":
            # Explicit BEGIN prevents sqlite's first SAVEPOINT from becoming the outer transaction.
            connection.exec_driver_sql("BEGIN")
        elif connection.dialect.name == "mysql":
            table_engines = connection.execute(text(
                "SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN ('dataset_contents', 'system_logs')"
            )).all()
            if len(table_engines) != 2 or any(str(e).lower() != "innodb" for _, e in table_engines):
                raise ValueError("Atomic replacement requires InnoDB tables")
        # The existing admin service commits its session. Savepoints keep those commits
        # inside this single outer transaction, so any failure rolls back the entire batch.
        with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
            ids = [r["dataset_id"] for r in selected]
            locked = {r.dataset_id: r for r in db.query(DatasetContent).filter(
                DatasetContent.dataset_id.in_(ids)).order_by(DatasetContent.dataset_id).with_for_update().all()}
            for record in selected:
                row = locked.get(record["dataset_id"])
                if row is None or fingerprint(snapshot(row)) != record["before_fingerprint"]:
                    raise ValueError("Database row changed after planning; regenerate the plan")
            for record in selected:
                dataset_id = record["dataset_id"]
                row = update_admin_dataset(
                    db, dataset_id=dataset_id,
                    payload=AdminDatasetUpdate(transcript=by_path[record["path"]]["transcript"]),
                    reviewer="owner-requested-transcript-file-replacement",
                )
                if row is None or row.transcript_sha256 != record["new_transcript_sha256"]:
                    raise ValueError("Replacement did not produce the expected transcript")
                metadata = json.loads(row.raw_metadata_json or "{}")
                revision = {
                    "plan_sha256": plan_id, "replaced_at": datetime.now(timezone.utc).isoformat(),
                    "source_path": record["path"], "source_snapshot_path": record["source_snapshot_path"],
                    "source_file_sha256": record["source_file_sha256"],
                    "old_transcript_sha256": record["old_transcript_sha256"],
                    "new_transcript_sha256": record["new_transcript_sha256"],
                    "file_title": record["title"], "pairing_evidence": record["pairing_evidence"],
                    "fullness_and_word_accuracy_verified": False,
                    "existing_scope_and_eligibility_preserved_not_newly_certified": True,
                }
                metadata.setdefault("transcript_replacements", []).append(revision)
                row.raw_metadata_json = json.dumps(metadata, ensure_ascii=False)
                row.review_notes = ((row.review_notes or "") + "\n" +
                    f"Transcript replaced at owner request; plan={plan_id}; source={record['source_file_sha256']}. "
                    "Source pairing checked; word accuracy/full-video coverage not independently verified.").strip()
                db.flush()
                after_rows[str(dataset_id)] = snapshot(row)
                check_preserved(backup[str(dataset_id)], after_rows[str(dataset_id)])
            if selected:
                db.add(SystemLog(action="dataset_transcript_batch_replaced", status="success",
                                 detail=json.dumps({"plan_sha256": plan_id, "dataset_ids": ids,
                                                    "inserted": 0, "deleted": 0, "trained": False})))
            db.commit()
    return {"updated_dataset_ids": [r["dataset_id"] for r in selected], "after_rows": after_rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--title-reviews", type=Path)
    parser.add_argument("--apply-plan", type=Path)
    args = parser.parse_args()
    from app.database.db import engine, SessionLocal

    entries = load_entries(args.export)
    if args.apply_plan:
        plan_path = args.apply_plan.resolve()
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if digest(args.export.read_bytes()) != plan["export_sha256"]:
            raise ValueError("Export differs from the planned file")
        result_path = plan_path.parent / "applied.json"
        if result_path.exists():
            raise ValueError("Apply result already exists; inspect it instead of repeating the operation")
        backup_path = plan_path.parent / "before.json"
        if digest(backup_path.read_bytes()) != plan["backup_sha256"]:
            raise ValueError("Backup file changed")
        backup = json.loads(backup_path.read_text(encoding="utf-8"))
        result = apply_plan(engine, plan, entries, plan_id=digest(plan_path.read_bytes()), backup=backup)
        result.update(committed=True, inserted=0, deleted=0, trained=False, activated=False,
                      completed_at=datetime.now(timezone.utc).isoformat(), summary=plan["summary"])
        write_new(result_path, result)
        with reject_database_writes(engine), SessionLocal() as db:
            for dataset_id in result["updated_dataset_ids"]:
                row = db.get(DatasetContent, dataset_id)
                expected = result["after_rows"][str(dataset_id)]
                if row.transcript != expected["transcript"] or row.transcript_sha256 != expected["transcript_sha256"]:
                    raise ValueError("Post-commit transcript verification failed")
                check_preserved(backup[str(dataset_id)], snapshot(row))
            count = db.query(DatasetContent).count()
        write_new(plan_path.parent / "verified.json", {
            "verified_after_reopen": True, "updated": len(result["updated_dataset_ids"]),
            "dataset_count_after": count, "dataset_count_before": plan["dataset_count_before"],
            "all_non_transcript_fields_preserved": True, "summary": plan["summary"],
        })
        print(json.dumps({"updated": len(result["updated_dataset_ids"]), "dataset_count_after": count,
                          "summary": plan["summary"], "report": str(result_path)}, ensure_ascii=False))
        return

    if args.output_dir is None or args.output_dir.exists():
        parser.error("Planning requires a new --output-dir")
    reviews = json.loads(args.title_reviews.read_text(encoding="utf-8")) if args.title_reviews else {}
    with reject_database_writes(engine), SessionLocal() as db:
        plan, backup = build_plan(db, entries, title_reviews=reviews)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    write_new(args.output_dir / "before.json", backup)
    plan.update(export_path=str(args.export.resolve()), export_sha256=digest(args.export.read_bytes()),
                backup_sha256=digest((args.output_dir / "before.json").read_bytes()))
    snapshots = args.output_dir / "source-snapshots"
    snapshots.mkdir()
    for record in plan["records"]:
        if not record.get("source_file_sha256"):
            continue
        raw = Path(record["path"]).read_bytes()
        if digest(raw) != record["source_file_sha256"]:
            raise ValueError("Source file changed during planning")
        target = snapshots / (record["source_file_sha256"] + ".md")
        if not target.exists():
            with target.open("xb") as handle:
                handle.write(raw)
        record["source_snapshot_path"] = str(target.resolve())
    write_new(args.output_dir / "plan.json", plan)
    print(json.dumps({"plan": str(args.output_dir / "plan.json"), "summary": plan["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
