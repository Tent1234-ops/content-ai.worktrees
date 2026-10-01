"""Read-only model preflight shared by admin pages and job setting snapshots.

This is not a second classifier: per-clip acceptance remains in
classification_acceptance, and reference coverage is checked at runtime.
"""
from app.core.config import settings
from app.services.classification_acceptance import (
    POLICY_VERSION, acceptance_summary, is_validated_acceptance_policy,
)
from app.services.classification_training import (
    classification_artifact_sha256, load_classification_artifact,
)


def classification_model_snapshot(model) -> dict:
    required = bool(settings.classification_require_scope_validation)
    readiness = {
        "version": "classification-readiness-v1",
        "status": "blocked",
        "artifact_loadable": False,
        "artifact_usable": False,
        "scope_policy_valid": False,
        "scope_test_passed": False,
        "scope_validation_required": required,
        "can_accept_predictions": False,
        "reason_codes": [],
    }
    result = {"model_id": None, "status": "unavailable", "readiness": readiness}
    if model is None:
        readiness["reason_codes"] = ["no_active_model"]
        return result
    result.update(
        model_id=model.model_id, model_key=model.model_key,
        model_version=model.model_version, model_type=model.model_type,
        training_sample_count=model.training_sample_count,
        taxonomy_version=model.taxonomy_version, status=model.status,
    )
    try:
        artifact = load_classification_artifact(model.artifact_path)
        readiness["artifact_loadable"] = True
        if artifact["model_key"] != model.model_key or artifact["model_version"] != model.model_version:
            readiness["reason_codes"] = ["artifact_registry_mismatch"]
            raise ValueError("Artifact does not match registry")
        if artifact.get("smoke_test_only"):
            readiness["reason_codes"] = ["smoke_test_only"]
            raise ValueError("Smoke-test artifact")
        result.update(
            unknown_threshold=float(artifact["unknown_threshold"]),
            artifact_sha256=classification_artifact_sha256(model.artifact_path),
            scope_validation_required=required,
            acceptance_policy_version=POLICY_VERSION,
            scope_validation=acceptance_summary(artifact.get("scope_policy")),
        )
    except Exception:
        # Do not expose paths, artifact internals, or loader exception text via API.
        result["status"] = "artifact_unavailable"
        if not readiness["reason_codes"]:
            readiness["reason_codes"] = ["artifact_unavailable"]
        return result

    policy = artifact.get("scope_policy")
    valid = is_validated_acceptance_policy(policy)
    readiness.update(artifact_usable=True, scope_policy_valid=valid,
                     scope_test_passed=bool(artifact.get("scope_test_passed")))
    if model.status != "qualified":
        readiness["reason_codes"].append("model_not_qualified")
    if not valid:
        readiness["reason_codes"].append(
            "scope_policy_missing" if not isinstance(policy, dict) else "scope_policy_not_validated"
        )
    if not required:
        readiness["reason_codes"].append("scope_validation_disabled")
    readiness["can_accept_predictions"] = model.status == "qualified" and (valid or not required)
    if readiness["can_accept_predictions"]:
        readiness["status"] = "ready" if valid and required else "unvalidated"
    return result
