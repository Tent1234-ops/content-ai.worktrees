"""Read-only closeout inventory. Never imports, trains, approves, or activates."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database.db import SessionLocal
from app.database.models import ClassificationModel, DatasetContent, ModelEvaluationMetric, SystemConfig
from app.services.analysis_settings import get_analysis_settings
from app.services.classification_collection_plan import preview_collection_channels
from app.services.classification_readiness import classification_model_snapshot
from app.services.model_management import (
    DEFAULT_GROUPED_CV_FOLDS, MODEL_PROMOTION_THRESHOLD, UNKNOWN_CONFIDENCE_THRESHOLD,
    model_summary, training_dataset,
)
from app.services.youtube_cc_dataset import list_youtube_cc_review_queue


def db_identity(db):
    rows = db.query(DatasetContent).order_by(DatasetContent.dataset_id).all()
    identities = [(r.dataset_id, r.taxonomy_leaf_key, r.data_split, r.source_youtube_id,
                   r.source_channel_id, r.transcript_sha256, r.is_active,
                   r.is_training_eligible, r.is_keyword_recommendation_eligible,
                   r.is_duration_recommendation_eligible) for r in rows]
    return {
        "dataset_count": len(rows),
        "identity_sha256": hashlib.sha256(json.dumps(identities).encode()).hexdigest(),
        "active_model_ids": [r.model_id for r in db.query(ClassificationModel).filter_by(is_active=True)],
    }


def audit(db, batch):
    before = db_identity(db)
    models = []
    for model in db.query(ClassificationModel).order_by(ClassificationModel.model_id):
        metrics = db.query(ModelEvaluationMetric).filter_by(
            model_id=model.model_id, language="all", taxonomy_level=3).all()
        snapshot = classification_model_snapshot(model)
        item = model_summary(model, metrics)
        item["artifact_sha256"] = snapshot.get("artifact_sha256")
        item["scope_validation"] = snapshot.get("scope_validation")
        try:
            evaluation = json.loads(Path(model.artifact_path).with_name("evaluation.json").read_text(encoding="utf-8"))
            item["evaluation_checksum_matches"] = bool(item["artifact_sha256"] and
                evaluation.get("artifact_sha256") == item["artifact_sha256"])
        except (OSError, ValueError, TypeError):
            item["evaluation_checksum_matches"] = False
        item["activation_preflight_passed"] = item["can_activate"] and item["evaluation_checksum_matches"]
        models.append(item)
    queue = list_youtube_cc_review_queue(db, limit=10000, review_status="pending")
    pending = queue["items"]
    rows = batch["items"]
    candidates = [r for r in rows if r.get("status") == "ready_for_review_import"]
    channels = sorted({r["channel_id"] for r in candidates if r.get("channel_id")})
    result = {
        "schema_version": "project-closeout-audit-v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "mode": "read_only", "before": before,
        "dataset": training_dataset(db), "models": models,
        "training_policy": {"promotion_threshold": MODEL_PROMOTION_THRESHOLD,
            "unknown_threshold": UNKNOWN_CONFIDENCE_THRESHOLD, "grouped_cv_folds": DEFAULT_GROUPED_CV_FOLDS},
        "analysis_settings": get_analysis_settings(db, admin=True) if db.query(SystemConfig).first() else None,
        "pending_review": {"total": queue["total"], "by_leaf": dict(Counter(
            r.get("proposed_leaf_key", "unknown") for r in pending)),
            "identities": [{k: r.get(k) for k in ("source_youtube_id", "collection_run_id",
                "proposed_leaf_key", "data_split", "channel_id")} for r in pending]},
        "new_batch": {"summary": batch.get("summary"),
            "duplicate_rows": [r for r in rows if r.get("status", "").startswith("duplicate")],
            "channel_preview": preview_collection_channels(db, channels) if channels else [],
            "groups": [{"leaf_key": leaf, "split": split,
                "count": len(group := [r for r in candidates if r.get("leaf_key") == leaf and r.get("data_split") == split]),
                "channels": sorted({r["channel_id"] for r in group}),
                "video_ids": [r["video_id"] for r in group]}
                for leaf in ("camera", "unknown") for split in ("train", "validation", "test")],
            "not_imported_or_reviewed": True},
        "fresh_test_independence": "Not inferred from file counts; review prior use and evaluation manifests before reservation.",
    }
    result["after"] = db_identity(db)
    result["database_unchanged"] = result["before"] == result["after"]
    db.rollback()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    batch = json.loads(args.batch_audit.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as target, SessionLocal() as db:
        result = audit(db, batch)
        json.dump(result, target, ensure_ascii=False, indent=2, default=str)
    print(json.dumps({"models": len(result["models"]), "pending_review": result["pending_review"]["total"],
                      "database_unchanged": result["database_unchanged"], "new_groups": result["new_batch"]["groups"]}))


if __name__ == "__main__":
    main()
