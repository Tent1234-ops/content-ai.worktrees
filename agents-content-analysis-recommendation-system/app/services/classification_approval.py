"""Audited admin deployment decisions, independent of historical score gates."""
from __future__ import annotations

import copy
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import joblib

from app.services.classification_acceptance import (
    is_reviewed_acceptance_policy,
)

APPROVED_STATUS = "admin_approved"
APPROVAL_VERSION = "classification-admin-approval-v1"
ARTIFACT_ROOT = Path(__file__).resolve().parents[2] / "artifacts/classification_approved"


def reviewed_policy(payload: dict) -> dict:
    policy = copy.deepcopy(payload.get("scope_policy"))
    if not isinstance(policy, dict) or payload.get("smoke_test_only"):
        raise ValueError("Evaluated scope policy required")
    # Preserve an already deployed operating point. Otherwise select from the
    # frozen Validation grid only, with no minimum percentage and no Test input.
    selected = policy.get("selected_validation")
    if not isinstance(selected, dict):
        candidates = policy.get("selection_candidates") or []
        candidates = [c for c in candidates if isinstance(c, dict) and all(
            isinstance(c.get(k), (int, float)) and math.isfinite(c[k]) and 0 <= c[k] <= 1
            for k in ("in_scope_macro_f1", "unknown_recall", "minimum_class_recall", "threshold"))]
        if not candidates:
            raise ValueError("No measured Validation operating point")
        selected = max(candidates, key=lambda c: (
            (c["in_scope_macro_f1"] + c["unknown_recall"]) / 2,
            c["minimum_class_recall"], c["unknown_recall"], -c["threshold"],
            -c.get("contrast_margin_threshold", 0)))
    if (selected not in policy.get("selection_candidates", [])
            or not isinstance(selected.get("per_class_recall"), dict)
            or set(selected["per_class_recall"]) != set(policy.get("labels", []))):
        raise ValueError("Validation evidence missing or inconsistent")
    policy.update(original_status=policy.get("original_status", policy["status"]),
                  status="admin_reviewed", selected_validation=selected,
                  similarity_threshold=selected["threshold"],
                  selection_rule="preserve_selected_or_validation_balanced_v1")
    if "contrast_margin_threshold" in selected:
        policy["contrast_margin_threshold"] = selected["contrast_margin_threshold"]
    if not is_reviewed_acceptance_policy(policy):
        raise ValueError("Invalid reviewed scope policy")
    return policy


def admin_authorization(payload: dict) -> dict:
    grant = payload.get("admin_authorization")
    result = {"authorized": False, "reason": "admin_approval_invalid"}
    if not isinstance(grant, dict):
        return result
    try:
        issued = datetime.fromisoformat(grant["issued_at"])
        valid = (grant.get("version") == APPROVAL_VERSION
                 and grant.get("risk_acknowledged") is True
                 and type(grant.get("authorized_by")) is int and grant["authorized_by"] > 0
                 and type(grant.get("source_model_id")) is int and grant["source_model_id"] > 0
                 and issued.tzinfo is not None and issued <= datetime.now(timezone.utc)
                 and grant.get("model_key") == payload.get("model_key")
                 and grant.get("model_version") == payload.get("model_version")
                 and not payload.get("smoke_test_only")
                 and is_reviewed_acceptance_policy(payload.get("scope_policy")))
        if valid:
            result.update(authorized=True, reason="admin_approved", **grant)
    except (KeyError, TypeError, ValueError):
        pass
    return result


def approval_preview(model, payload: dict) -> dict | None:
    if model.status not in ("evaluated_below_threshold", "presentation_only", APPROVED_STATUS):
        return None
    try:
        policy = reviewed_policy(payload)
        return {"selected_validation": policy["selected_validation"],
                "validation_counts": policy["validation_counts"],
                "score_threshold_required": False}
    except (ValueError, TypeError, KeyError):
        return None


def create_approved_model(db, source, *, user_id: int):
    from app.database.models import ClassificationModel, ModelEvaluationMetric, User
    from app.services.classification_training import (
        classification_artifact_sha256, load_classification_artifact, classify_with_artifact,
    )

    admin = db.get(User, user_id)
    if admin is None or admin.role != "admin" or not admin.is_active:
        raise ValueError("Active admin approval required")
    original = load_classification_artifact(source.artifact_path)
    policy = reviewed_policy(original)
    version = f"admin-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid4().hex[:8]}"
    key = source.model_key.removesuffix("-presentation").removesuffix("-approved") + "-approved"
    grant = {"version": APPROVAL_VERSION, "authorized_by": user_id,
             "risk_acknowledged": True, "issued_at": datetime.now(timezone.utc).isoformat(),
             "source_model_id": source.model_id, "model_key": key, "model_version": version}
    bundle = dict(original, model_key=key, model_version=version, scope_policy=policy,
                  admin_authorization=grant, source_model_id=source.model_id,
                  source_artifact_sha256=classification_artifact_sha256(source.artifact_path))
    bundle.pop("presentation_authorization", None)
    if not admin_authorization(bundle)["authorized"]:
        raise ValueError("Invalid admin authorization")
    folder = ARTIFACT_ROOT / version
    folder.mkdir(parents=True, exist_ok=False)
    path = folder / "model.joblib"
    joblib.dump(bundle, path)
    loaded = load_classification_artifact(path)
    if not admin_authorization(loaded)["authorized"]:
        raise ValueError("Approved artifact round-trip failed")
    probe = classify_with_artifact(path, text="", allow_admin_review=True)
    if not probe["is_unknown"] or probe["acceptance"]["reason"] != "no_transcript":
        raise ValueError("Approved artifact inference check failed")
    selected = policy["selected_validation"]
    evaluation = {"artifact_sha256": classification_artifact_sha256(path),
                  "admin_authorization": grant, "source_artifact_sha256": bundle["source_artifact_sha256"],
                  "validation_operating_point": selected, "selection_used_test": False,
                  "score_threshold_required": False}
    (folder / "evaluation.json").write_text(json.dumps(evaluation, ensure_ascii=False, indent=2), encoding="utf-8")
    model = ClassificationModel(model_key=key, model_version=version, model_type=source.model_type,
        taxonomy_version=source.taxonomy_version, artifact_path=str(path.resolve()),
        training_dataset_source=source.training_dataset_source, training_dataset_version=source.training_dataset_version,
        training_sample_count=source.training_sample_count, trained_at=source.trained_at,
        status=APPROVED_STATUS, is_active=False)
    db.add(model)
    db.flush()
    def metric(split, name, value, count, leaf="__overall__", details=None):
        db.add(ModelEvaluationMetric(model_id=model.model_id, dataset_split=split, language="all",
            taxonomy_level=3, taxonomy_leaf_key=leaf, metric_name=name, metric_value=value,
            sample_size=count, details=json.dumps(details, ensure_ascii=False) if details else None))
    count = selected["in_scope_sample_count"]
    metric("validation", "accuracy", selected["in_scope_accuracy"], count)
    metric("validation", "f1_macro", selected["in_scope_macro_f1"], count)
    metric("validation", "unknown_recall", selected["unknown_recall"], selected["unknown_sample_count"], "unknown")
    for leaf, recall in selected["per_class_recall"].items():
        metric("validation", "recall", recall, policy["validation_counts"][leaf], leaf)
    metric("artifact_check", "reload_classify_passed", 1, 1)
    metric("deployment_review", "approved", 1, count, details=evaluation)
    # Old Test metrics belong to the source operating point; don't copy them
    # onto a new policy. Keep the original model and its reports untouched.
    return model
