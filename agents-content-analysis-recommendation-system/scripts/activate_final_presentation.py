"""Explicit final-demo activation from a frozen run, not production qualification."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("CONTENT_AI_SKIP_DB_BOOTSTRAP", "1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import joblib
from app.database.db import SessionLocal
from app.database.models import ClassificationModel, ModelEvaluationMetric, ModelTrainingRun, SystemLog
from app.services.classification_acceptance import acceptance_summary
from app.services.classification_presentation import PRESENTATION_STATUS, presentation_authorization
from app.services.classification_training import classification_artifact_sha256, load_classification_artifact
from app.services.model_management import training_dataset
from scripts.presentation_classification_model import lock_activation


def activate(db, *, run_id, admin_id, expected_active_id, expires_at, reason, confirmed,
             output_root, now=None):
    now = now or datetime.now(timezone.utc)
    if not confirmed or not reason.strip() or expires_at.tzinfo is None:
        raise ValueError("Explicit risk acknowledgment, reason and timezone-aware deadline required")
    if not 0 < (expires_at - now).total_seconds() <= 168 * 3600:
        raise ValueError("Presentation deadline must be within seven days")
    previous = lock_activation(db, admin_id, expected_active_id)
    run = db.get(ModelTrainingRun, run_id)
    if run is None or run.status != "completed":
        raise ValueError("Completed training run required")
    report = json.loads(run.result_json)
    source_id = report["best_model"]["model_id"]
    source = db.get(ClassificationModel, source_id)
    item = next(m for m in report["models"] if m["model_id"] == source_id)
    if source is None or source.status != "evaluated_below_threshold" or item["qualification"]["passed"]:
        raise ValueError("Use normal activation for qualified models")
    if (Path(source.artifact_path).resolve() != Path(item["artifact_path"]).resolve()
            or classification_artifact_sha256(source.artifact_path) != item["artifact_sha256"]):
        raise ValueError("Source artifact integrity mismatch")
    original = load_classification_artifact(source.artifact_path)
    fingerprint = training_dataset(db)["dataset_fingerprint"]
    if fingerprint != report["dataset"]["dataset_fingerprint"] or fingerprint != original.get("dataset_fingerprint"):
        raise ValueError("Dataset changed since fitting")
    policy = copy.deepcopy(original["scope_policy"])
    if policy.get("status") != "failed_validation" or acceptance_summary(policy) != item["scope_policy"]:
        raise ValueError("Source validation policy does not match the frozen report")
    # Retain the Unknown rejection requirement; select only from the existing
    # Validation grid, never using saved test outcomes or demo clip predictions.
    candidates = [c for c in policy["selection_candidates"]
                  if c["unknown_recall"] >= policy["required_recall"]]
    if not candidates:
        raise ValueError("No validation operating point retains the Unknown rejection goal")
    selected = max(candidates, key=lambda c: (c["minimum_class_recall"], c["in_scope_macro_f1"],
                   c["unknown_recall"], -c["threshold"], -c.get("contrast_margin_threshold", 0)))
    policy.update(original_status=policy["status"], status=PRESENTATION_STATUS,
                  similarity_threshold=selected["threshold"], selected_validation=selected)
    if "contrast_margin_threshold" in selected:
        policy["contrast_margin_threshold"] = selected["contrast_margin_threshold"]
    version = now.strftime("final-presentation-%Y%m%dT%H%M%S%fZ")
    key = source.model_key + "-presentation"
    grant = {"version": "presentation-authorization-v2", "risk_acknowledged": True,
             "authorized_by": admin_id, "reason": reason.strip(), "issued_at": now.isoformat(),
             "expires_at": expires_at.isoformat(), "deadline_at": expires_at.isoformat(),
             "model_key": key, "model_version": version, "source_model_id": source_id,
             "previous_active_model_id": previous.model_id}
    bundle = dict(original, model_key=key, model_version=version, scope_policy=policy,
                  scope_test_passed=False, presentation_authorization=grant,
                  source_artifact_sha256=item["artifact_sha256"], source_model_id=source_id)
    if not presentation_authorization(bundle, now=now)["authorized"]:
        raise ValueError("Invalid presentation authorization")
    folder = output_root / version
    folder.mkdir(parents=True, exist_ok=False)
    artifact = folder / "model.joblib"
    joblib.dump(bundle, artifact)
    if not presentation_authorization(load_classification_artifact(artifact), now=now)["authorized"]:
        raise ValueError("Artifact round-trip failed")
    evaluation = {"status": PRESENTATION_STATUS, "promotion_passed": False,
                  "artifact_sha256": classification_artifact_sha256(artifact),
                  "authorization": grant, "source_run_id": run_id,
                  "source_model_id": source_id, "source_artifact_sha256": item["artifact_sha256"],
                  "validation_operating_point": selected, "selection_used_test": False,
                  "test_evaluated_at_presentation_operating_point": False}
    (folder / "evaluation.json").write_text(json.dumps(evaluation, ensure_ascii=False, indent=2), encoding="utf-8")
    model = ClassificationModel(model_key=key, model_version=version, model_type=source.model_type,
        taxonomy_version=source.taxonomy_version, artifact_path=str(artifact.resolve()),
        training_dataset_source=source.training_dataset_source, training_dataset_version=source.training_dataset_version,
        training_sample_count=source.training_sample_count, trained_at=source.trained_at,
        status=PRESENTATION_STATUS, is_active=True)
    previous.is_active = False
    db.add(model)
    db.flush()
    qualification = {"passed": False, "promotion_threshold": policy["required_recall"],
        "scope_validation_status": "failed_validation", "scope_policy_version": policy["version"],
        "blocked_reasons": ["scope_validation_not_passed"], "presentation_authorization": grant,
        "test_evaluated": False, "source_model_id": source_id}
    def metric(split, name, value, count, leaf="__overall__", details=None):
        db.add(ModelEvaluationMetric(model_id=model.model_id, dataset_split=split, language="all", taxonomy_level=3,
            taxonomy_leaf_key=leaf, metric_name=name, metric_value=value, sample_size=count,
            details=json.dumps(details, ensure_ascii=False) if details else None))
    count = selected["in_scope_sample_count"]
    metric("promotion_gate", "passed", 0, count + selected["unknown_sample_count"], details=qualification)
    metric("validation", "accuracy", selected["in_scope_accuracy"], count)
    metric("validation", "f1_macro", selected["in_scope_macro_f1"], count)
    metric("validation", "unknown_recall", selected["unknown_recall"], selected["unknown_sample_count"], "unknown")
    for label, recall in selected["per_class_recall"].items():
        metric("validation", "recall", recall, policy["validation_counts"][label], label)
    result = {**evaluation, "model_id": model.model_id, "previous_active_model_id": previous.model_id,
              "artifact_path": str(artifact.resolve()), "expires_at": expires_at.isoformat()}
    db.add(SystemLog(user_id=admin_id, action="classification_presentation_activate", status="success",
                     detail=json.dumps(result, ensure_ascii=False)))
    db.commit()
    (folder / "activation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--admin-id", type=int, required=True)
    parser.add_argument("--expected-active-model-id", type=int, required=True)
    parser.add_argument("--expires-at", type=datetime.fromisoformat, required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--confirm-unqualified", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        result = activate(db, run_id=args.run_id, admin_id=args.admin_id,
            expected_active_id=args.expected_active_model_id, expires_at=args.expires_at,
            reason=args.reason, confirmed=args.confirm_unqualified,
            output_root=ROOT / "artifacts/classification_presentation")
        print(json.dumps(result, ensure_ascii=False, indent=2))
