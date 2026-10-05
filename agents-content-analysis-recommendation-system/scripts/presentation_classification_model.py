"""Explicit temporary model activation for a presentation; never mark it qualified."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import joblib

from app.database.db import SessionLocal
from app.database.models import ClassificationModel, ModelEvaluationMetric, ModelTrainingRun, SystemConfig, SystemLog, User
from app.services.admin_settings import get_or_create_admin_config
from app.services.classification_acceptance import CONTRAST_POLICY_VERSION, acceptance_summary
from app.services.classification_presentation import PRESENTATION_STATUS, presentation_authorization
from app.services.classification_training import (
    _dataset_fingerprint, classification_artifact_sha256, load_classification_artifact,
)
from app.services.taxonomy import TAXONOMY_VERSION
from scripts.develop_classification_scope import load_development_rows


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lock_activation(db, admin_id, expected_active_id):
    admin = db.get(User, admin_id)
    if admin is None or admin.role != "admin" or not admin.is_active:
        raise ValueError("An active administrator must authorize presentation mode")
    config = get_or_create_admin_config(db)
    db.query(SystemConfig).filter_by(config_id=config.config_id).with_for_update().one()
    if db.query(ModelTrainingRun).filter_by(active_slot=1).count():
        raise ValueError("A training job is still active")
    active = db.query(ClassificationModel).filter_by(is_active=True).all()
    if len(active) != 1 or active[0].model_id != expected_active_id:
        raise ValueError("Active model changed; inspect before authorizing")
    return active[0]


def enable(db, *, source, admin_id, expected_active_id, hours, reason, confirmed, output_root):
    if not confirmed or not str(reason).strip() or not 1 <= hours <= 72:
        raise ValueError("Explicit risk confirmation, reason and 1..72 hours are required")
    previous = lock_activation(db, admin_id, expected_active_id)
    if previous.status == PRESENTATION_STATUS:
        raise ValueError("Disable the current presentation first")
    report_path = source / "report.json"
    artifact_source = source / f"{CONTRAST_POLICY_VERSION}.joblib"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    original = joblib.load(artifact_source)
    if report.get("protocol") != "laptop-scope-20261004-hybrid" or report.get("test_accessed") is not False:
        raise ValueError("Expected the frozen Train/Validation-only hybrid experiment")
    train, validation, unknown = load_development_rows(db)
    if report["development_fingerprint"] != _dataset_fingerprint([*train, *validation, *unknown]):
        raise ValueError("Development data changed since this fit")
    policy = copy.deepcopy(original["scope_policy"])
    recorded = next((p["policy"] for p in report["policies"] if p["policy"]["version"] == policy["version"]), None)
    if (original.get("development_only") is not True or acceptance_summary(policy) != recorded
            or policy["status"] != "failed_validation" or policy["confidence_threshold"] != 0.6
            or policy["required_recall"] != 0.8 or set(policy["fit_dataset_ids"]) != {r.dataset_id for r in train}
            or set(policy["validation_dataset_ids"]) != {r.dataset_id for r in [*validation, *unknown]}
            or original["estimator"].named_steps["classifier"].C != report["selected"]["C"]):
        raise ValueError("Artifact and development report do not match")
    # Keep the existing Unknown rejection goal; choose the best retained known
    # recall from the already measured Validation grid, not from Test scores.
    candidates = [r for r in policy["selection_candidates"] if r["unknown_recall"] >= 0.8]
    selected = max(candidates, key=lambda r: (r["minimum_class_recall"], r["in_scope_macro_f1"],
        r["unknown_recall"], -r["threshold"], -r["contrast_margin_threshold"]))
    now = datetime.now(timezone.utc)
    version = now.strftime("presentation-%Y%m%dT%H%M%S%fZ")
    key = "taxonomy-hybrid-thai-embedding-presentation"
    policy.update(original_status=policy["status"], status=PRESENTATION_STATUS,
                  similarity_threshold=selected["threshold"],
                  contrast_margin_threshold=selected["contrast_margin_threshold"],
                  selected_validation=selected)
    grant = {"version": "presentation-authorization-v1", "risk_acknowledged": True,
             "authorized_by": admin_id, "reason": reason.strip(), "issued_at": now.isoformat(),
             "expires_at": (now + timedelta(hours=hours)).isoformat(),
             "model_key": key, "model_version": version, "previous_active_model_id": previous.model_id}
    bundle = {"artifact_schema_version": 3, "model_family": "taxonomy-text-classifier",
              "model_key": key, "model_version": version,
              "model_type": "multilingual_sentence_embeddings_thai_tfidf_hybrid_logistic_regression",
              "taxonomy_version": TAXONOMY_VERSION, "labels": list(policy["labels"]),
              "unknown_leaf_key": "unknown", "unknown_threshold": 0.6,
              "fit_split": "train", "development_sample_count": len(train),
              "selected_hyperparameters": {"C": report["selected"]["C"]},
              "development_fingerprint": report["development_fingerprint"],
              "source_report_sha256": digest(report_path), "source_artifact_sha256": digest(artifact_source),
              "scope_policy": policy, "scope_test_passed": False, "smoke_test_only": False,
              "presentation_authorization": grant, "estimator": original["estimator"]}
    if not presentation_authorization(bundle)["authorized"]:
        raise ValueError("Invalid presentation authorization")
    folder = output_root / version
    folder.mkdir(parents=True, exist_ok=False)
    artifact_path = folder / "model.joblib"
    joblib.dump(bundle, artifact_path)
    loaded = load_classification_artifact(artifact_path)
    if not presentation_authorization(loaded)["authorized"]:
        raise ValueError("Serialized authorization failed validation")
    evaluation = {"artifact_sha256": classification_artifact_sha256(artifact_path),
                  "status": PRESENTATION_STATUS, "promotion_passed": False, "test_evaluated": False,
                  "authorization": grant, "validation_operating_point": selected,
                  "grouped_cv": report["selected"]["grouped_cv"],
                  "development_fingerprint": report["development_fingerprint"],
                  "source_report_sha256": bundle["source_report_sha256"],
                  "source_artifact_sha256": bundle["source_artifact_sha256"]}
    (folder / "evaluation.json").write_text(json.dumps(evaluation, ensure_ascii=False, indent=2), encoding="utf-8")
    model = ClassificationModel(model_key=key, model_version=version, taxonomy_version=TAXONOMY_VERSION,
        model_type=bundle["model_type"], artifact_path=str(artifact_path.resolve()),
        training_dataset_source="youtube_public_research", training_dataset_version="presentation-frozen-development",
        training_sample_count=len(train), status=PRESENTATION_STATUS, is_active=True,
        trained_at=datetime.fromtimestamp(artifact_source.stat().st_mtime, timezone.utc).replace(tzinfo=None))
    previous.is_active = False
    db.add(model)
    db.flush()
    qualification = {"passed": False, "promotion_threshold": 0.8, "scope_validation_status": "failed_validation",
                     "scope_policy_version": policy["version"], "blocked_reasons": ["scope_validation_not_passed"],
                     "test_evaluated": False, "presentation_authorization": grant}
    def metric(split, name, value, count, leaf="__overall__", details=None):
        db.add(ModelEvaluationMetric(model_id=model.model_id, dataset_split=split, language="all", taxonomy_level=3,
            taxonomy_leaf_key=leaf, metric_name=name, metric_value=value, sample_size=count,
            details=json.dumps(details, ensure_ascii=False) if details else None))
    metric("promotion_gate", "passed", 0, len(validation) + len(unknown), details=qualification)
    for name in ("accuracy", "f1_macro"):
        metric("grouped_cv", name, report["selected"]["grouped_cv"][name], len(train))
    metric("validation", "accuracy", selected["in_scope_accuracy"], len(validation))
    metric("validation", "f1_macro", selected["in_scope_macro_f1"], len(validation))
    metric("validation", "unknown_recall", selected["unknown_recall"], len(unknown), leaf="unknown")
    for label, recall in selected["per_class_recall"].items():
        metric("validation", "recall", recall, sum(r.leaf_key == label for r in validation), leaf=label)
    result = {"model_id": model.model_id, "previous_active_model_id": previous.model_id, "status": PRESENTATION_STATUS,
              "artifact_path": str(artifact_path.resolve()), "expires_at": grant["expires_at"],
              "validation_operating_point": selected, "test_evaluated": False, "promotion_passed": False}
    db.add(SystemLog(user_id=admin_id, action="classification_presentation_activate", status="success",
                     detail=json.dumps({**result, "reason": reason}, ensure_ascii=False)))
    db.commit()
    (folder / "activation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def disable(db, *, admin_id, expected_active_id):
    active = lock_activation(db, admin_id, expected_active_id)
    if active.status != PRESENTATION_STATUS:
        raise ValueError("Active model is not a presentation model")
    artifact = load_classification_artifact(active.artifact_path)
    previous = db.get(ClassificationModel, artifact["presentation_authorization"]["previous_active_model_id"])
    if previous is None or previous.status != "qualified":
        raise ValueError("Previous registry model is unavailable")
    active.is_active = False
    previous.is_active = True
    result = {"disabled_model_id": active.model_id, "restored_model_id": previous.model_id}
    db.add(SystemLog(user_id=admin_id, action="classification_presentation_disable", status="success", detail=json.dumps(result)))
    db.commit()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("enable", "disable"))
    parser.add_argument("--admin-id", type=int, required=True)
    parser.add_argument("--expected-active-model-id", type=int, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--hours", type=int, default=48)
    parser.add_argument("--reason", default="")
    parser.add_argument("--confirm-unqualified", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        if args.action == "enable":
            if args.source is None:
                parser.error("--source is required for enable")
            result = enable(db, source=args.source, admin_id=args.admin_id, expected_active_id=args.expected_active_model_id,
                hours=args.hours, reason=args.reason, confirmed=args.confirm_unqualified,
                output_root=ROOT / "artifacts/classification_presentation")
        else:
            result = disable(db, admin_id=args.admin_id, expected_active_id=args.expected_active_model_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
