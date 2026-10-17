"""Audited final retraining operations; never silently override qualification."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys

os.environ.setdefault("CONTENT_AI_SKIP_DB_BOOTSTRAP", "1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database.db import SessionLocal, engine
from app.database.models import (
    AnalysisResult, ClassificationModel, ClipRevisionPlan, DatasetContent, ModelTrainingRun, OutcomeModel,
    ReferenceVideoStatistic, SystemLog,
)
from app.services.dataset_eligibility import production_transcript_conditions
from app.services.model_management import start_training_run, training_dataset, serialize_run
from app.services.outcome_dataset import database_source_records
from app.services.outcome_prediction_readiness import data_use_gate, reject_database_writes
from scripts.audit_outcome_incoming_transcripts import transcript_review
from scripts.replace_notebooklm_transcripts import snapshot


def write_new(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, default=str)
        stream.write("\n")


def audit(output):
    output.mkdir(parents=True, exist_ok=False)
    cutoff = datetime.now(timezone.utc)
    protocol = json.loads((ROOT / "docs/implementation/outcome-prediction-protocol-v1.json").read_text(encoding="utf-8"))
    rights = json.loads((ROOT / "docs/implementation/outcome-prediction-data-use-v1.json").read_text(encoding="utf-8"))
    with reject_database_writes(engine), SessionLocal() as db:
        rows = db.query(DatasetContent).order_by(DatasetContent.dataset_id).all()
        before = {
            "captured_at": cutoff.isoformat(),
            "datasets": {str(r.dataset_id): snapshot(r) for r in rows},
            "models": [snapshot(r) for r in db.query(ClassificationModel).all()],
            "outcome_models": [snapshot(r) for r in db.query(OutcomeModel).all()],
            "analysis_results": [snapshot(r) for r in db.query(AnalysisResult).all()],
        }
        write_new(output / "before.json", before)
        ready = training_dataset(db)
        write_new(output / "classification-readiness.json", ready)
        eligible = db.query(DatasetContent).filter(
            *production_transcript_conditions(train_only=False, require_training=True)
        ).all()
        quality = [{"dataset_id": r.dataset_id, "video_id": r.source_youtube_id,
                    "split": r.data_split, "category": r.taxonomy_leaf_key,
                    **transcript_review(r.transcript)} for r in eligible]
        issues = [r for r in quality if r["missing_caption_notice"] or r["language_review_required"]]
        write_new(output / "transcript-review.json", {"screened": len(quality), "issues": issues,
                  "fullness_not_certified_by_this_screen": True, "rows": quality})
        records = database_source_records(db, cutoff=cutoff, protocol=protocol, repo_root=ROOT)
        write_new(output / "outcome-source-audit.json", {"cutoff": cutoff.isoformat(),
            "rows": records, "training_data_use": data_use_gate(rights, "training"),
            "issue_counts": dict(Counter(reason for r in records for reason in r["exclusion_reasons"])),
            "eligible": sum(not r["exclusion_reasons"] for r in records)})
        db.rollback()
    print(json.dumps({"dataset_rows": len(rows), "classification_samples": ready["sample_count"],
        "quality_issues": issues, "outcome_rows": len(records),
        "outcome_eligible": sum(not r["exclusion_reasons"] for r in records),
        "outcome_issues": dict(Counter(reason for r in records for reason in r["exclusion_reasons"])),
        "outcome_data_use": data_use_gate(rights, "training")}, ensure_ascii=False, default=str))


def train(output, admin_id):
    if (output / "run.json").exists():
        raise ValueError("Run already requested; use status")
    before = json.loads((output / "classification-readiness.json").read_text(encoding="utf-8"))
    quality = json.loads((output / "transcript-review.json").read_text(encoding="utf-8"))
    if quality["issues"]:
        raise ValueError("Review transcript quality issues before fitting")
    with SessionLocal() as db:
        from app.database.models import User
        admin = db.get(User, admin_id)
        if admin is None or admin.role != "admin" or not admin.is_active:
            raise ValueError("Active administrator required")
        run = start_training_run(db, user_id=admin_id, dataset_fingerprint=before["dataset_fingerprint"])
        write_new(output / "run.json", run)
        print(json.dumps(run, default=str, ensure_ascii=False))


def status(output):
    run_id = json.loads((output / "run.json").read_text(encoding="utf-8"))["run_id"]
    with SessionLocal() as db:
        run = db.get(ModelTrainingRun, run_id)
        result = serialize_run(run)
        if run.status not in {"queued", "running"} and not (output / "training-result.json").exists():
            write_new(output / "training-result.json", json.loads(run.result_json or "{}"))
        print(json.dumps(result, default=str, ensure_ascii=False))


def confirm_final_batch(output):
    """Apply the scoped owner statement; do not claim rights or fresh holdouts."""
    report_path = output / "owner-confirmed-metadata.json"
    if report_path.exists():
        raise ValueError("Confirmation already recorded")
    before = json.loads((output / "before.json").read_text(encoding="utf-8"))["datasets"]
    expected = {}
    manifests = {}
    for category, folder in (("phone", "phone-20261013"), ("camera", "camera-20261013"),
                             ("laptop", "laptop-20261014")):
        path = ROOT / "docs/prompts/transcript-export" / folder / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifests[category] = {"path": str(path.relative_to(ROOT)),
                               "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for batch in manifest["batches"]:
            for video in batch["videos"]:
                video_id = video["video_id"]
                if video_id in expected:
                    raise ValueError("Duplicate source in prompt manifests")
                expected[video_id] = category
    now = datetime.now(timezone.utc).isoformat()
    confirmation = {
        "schema_version": "final-batch-owner-provenance-v1", "captured_at": now,
        "owner_statement": "ตามpromptที่ให้มาเลย",
        "question_scope": "Latest Perplexity batch: not selected by views/likes; normal YouTube videos, not Shorts",
        "sampling_description": "Owner-confirmed prompt-based convenience discovery; not a random population sample",
        "format_evidence": "owner_statement_not_automated_player_verification",
        "data_use_status": "unverified", "owner_data_use_statement": "ยังไม่มีหลักฐานยืนยัน",
        "fresh_holdout_certified": False, "prompt_manifests": manifests,
    }
    changed, found = [], set()
    with SessionLocal() as db:
        rows = db.query(DatasetContent).filter(DatasetContent.source_youtube_id.in_(expected)).with_for_update().all()
        for row in rows:
            if row.taxonomy_leaf_key != expected[row.source_youtube_id] or row.deleted_at or not row.is_active:
                raise ValueError(f"Unexpected source state: {row.dataset_id}")
            old = before[str(row.dataset_id)]
            if any(snapshot(row)[key] != old[key] for key in ("transcript_sha256", "data_split", "raw_metadata_json")):
                raise ValueError(f"Source changed since backup: {row.dataset_id}")
            metadata = json.loads(row.raw_metadata_json or "{}")
            if not isinstance(metadata, dict) or any(key in metadata for key in (
                "content_format", "outcome_sampling_frame", "outcome_final_batch_provenance")):
                raise ValueError(f"Existing provenance needs separate review: {row.dataset_id}")
            metadata.update(content_format="long_form", outcome_sampling_frame="general_protocol_v1",
                            outcome_final_batch_provenance=confirmation)
            row.raw_metadata_json = json.dumps(metadata, ensure_ascii=False)
            found.add(row.source_youtube_id)
            changed.append({"dataset_id": row.dataset_id, "video_id": row.source_youtube_id,
                            "category": row.taxonomy_leaf_key, "split_unchanged": row.data_split})
        db.add(SystemLog(user_id=2, action="final_batch_owner_provenance", status="success",
                        detail=json.dumps({"count": len(changed), "backup": str(output / "before.json"),
                            "fields": ["raw_metadata_json"], "confirmation": confirmation}, ensure_ascii=False)))
        db.commit()
    result = {"confirmation": confirmation, "updated": changed,
              "missing_prompt_video_ids": sorted(set(expected) - found),
              "counts": dict(Counter(r["category"] for r in changed))}
    write_new(report_path, result)
    print(json.dumps({"updated_count": len(changed), "counts": result["counts"],
                      "missing_prompt_video_ids": result["missing_prompt_video_ids"]}))


def set_asr(output, admin_id, model):
    from app.database.models import User
    from app.schemas.analysis_settings import AnalysisParameters
    from app.services.analysis_settings import get_analysis_settings, save_analysis_settings
    with SessionLocal() as db:
        admin = db.get(User, admin_id)
        if admin is None or admin.role != "admin" or not admin.is_active:
            raise ValueError("Active administrator required")
        before = get_analysis_settings(db)
        write_new(output / "asr-settings-before.json", before)
        parameters = AnalysisParameters(**{k: before[k] for k in (
            "upload_max_duration_seconds", "asr_model", "hook_duration_seconds")})
        parameters.asr_model = model
        after = save_analysis_settings(db, parameters, user_id=admin_id)
        write_new(output / "asr-settings-after.json", after)
        print(json.dumps({"before": before["asr_model"], "after": after["asr_model"],
                          "ready": after["asr_ready"]}))


def verify(output, expected_model_id, content_id):
    from app.services.analysis_settings import capture_analysis_settings
    from app.services.classification_training import classification_artifact_sha256, load_classification_artifact
    before = json.loads((output / "before.json").read_text(encoding="utf-8"))
    with reject_database_writes(engine), SessionLocal() as db:
        dataset_models = {str(r.dataset_id): r for r in db.query(DatasetContent).all()}
        datasets = {key: snapshot(row) for key, row in dataset_models.items()}
        changes = [{"dataset_id": key, "fields": [field for field in original
                    if original[field] != datasets.get(key, {}).get(field)]}
                   for key, original in before["datasets"].items() if original != datasets.get(key)]
        additions = sorted(set(datasets) - set(before["datasets"]))
        dynamic_fields = {"views", "likes", "comments", "statistics_captured_at", "view_metric_version",
                          "average_views_per_day", "engagement_rate"}
        protected_changes = [c for c in changes if set(c["fields"]) - dynamic_fields]
        if protected_changes or additions:
            raise ValueError(json.dumps({"protected_dataset_changes": protected_changes, "added_ids": additions}))
        # A live collector may refresh counters, but each change must match a
        # successful recorded observation. Transcript, split and labels stay fixed.
        for change in changes:
            row = dataset_models[change["dataset_id"]]
            observation = db.query(ReferenceVideoStatistic).filter_by(
                dataset_id=row.dataset_id, observed_at=row.statistics_captured_at, status="complete",
                video_id=row.source_youtube_id).order_by(ReferenceVideoStatistic.observation_id.desc()).first()
            assert observation and not observation.error_code
            assert all(getattr(row, key) == getattr(observation, key)
                       for key in ("views", "likes", "comments", "view_metric_version"))
            age = max((row.statistics_captured_at - row.published_at).total_seconds() / 86400, 1)
            # MySQL FLOAT round-trips about six significant digits in this schema.
            assert math.isclose(row.average_views_per_day, row.views / age, rel_tol=5e-6, abs_tol=1e-6), (
                row.dataset_id, row.average_views_per_day, row.views / age)
            assert math.isclose(row.engagement_rate, (row.likes + row.comments) / max(row.views, 1),
                                rel_tol=5e-6, abs_tol=1e-6)
            change.update(observation_id=observation.observation_id, run_id=observation.run_id,
                          observed_at=row.statistics_captured_at.isoformat())
        for original in before["analysis_results"]:
            assert snapshot(db.get(AnalysisResult, original["result_id"])) == original
        active = db.query(ClassificationModel).filter_by(is_active=True).all()
        assert len(active) == 1 and active[0].model_id == expected_model_id
        assert db.query(ModelTrainingRun).filter(ModelTrainingRun.status.in_(["running", "queued"])).count() == 0
        outcome_count = db.query(OutcomeModel).count()
        assert outcome_count == len(before["outcome_models"])
        settings = capture_analysis_settings(db)
        assert settings["classification_model"]["readiness"]["can_accept_predictions"]
        bundle = load_classification_artifact(active[0].artifact_path)
        assert training_dataset(db)["dataset_fingerprint"] == bundle["dataset_fingerprint"]
        source = db.get(ClassificationModel, bundle["source_model_id"])
        assert classification_artifact_sha256(source.artifact_path) == bundle["source_artifact_sha256"]
        analysis = db.query(AnalysisResult).filter_by(content_id=content_id).one()
        plan = db.get(ClipRevisionPlan, analysis.result_id)
        assert plan and plan.revision == 1 and len(json.loads(plan.selected_advice_ids)) == 1
        report = {"captured_at": datetime.now(timezone.utc).isoformat(), "passed": True,
                  "dataset_protected_fields_unchanged": len(datasets),
                  "verified_statistics_refresh_count": len(changes), "statistics_refreshes": changes,
                  "old_analyses_unchanged": len(before["analysis_results"]),
                  "active_model_id": active[0].model_id, "status": active[0].status,
                  "source_artifact_unchanged": True, "outcome_registry_count": outcome_count,
                  "unfinished_training_runs": 0, "settings": settings,
                  "audit_content_id": content_id, "saved_plan": snapshot(plan)}
        db.rollback()
    write_new(output / "final-integrity.json", report)
    print(json.dumps({k: v for k, v in report.items() if k not in {"settings", "saved_plan", "statistics_refreshes"}}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("audit", "train", "status", "confirm-final-batch", "set-asr", "verify"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--admin-id", type=int)
    parser.add_argument("--asr-model", choices=("small", "medium", "large-v3"), default="medium")
    parser.add_argument("--expected-model-id", type=int)
    parser.add_argument("--content-id", type=int)
    args = parser.parse_args()
    if args.action == "audit":
        audit(args.output)
    elif args.action == "train":
        train(args.output, args.admin_id)
    elif args.action == "confirm-final-batch":
        confirm_final_batch(args.output)
    elif args.action == "set-asr":
        set_asr(args.output, args.admin_id, args.asr_model)
    elif args.action == "verify":
        verify(args.output, args.expected_model_id, args.content_id)
    else:
        status(args.output)
