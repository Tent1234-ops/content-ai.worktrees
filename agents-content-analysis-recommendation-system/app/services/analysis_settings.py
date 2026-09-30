import json
from datetime import datetime, timezone

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.config import settings as runtime_settings
from app.services.classification_acceptance import POLICY_VERSION, acceptance_summary
from app.database.models import ModelEvaluationMetric
from app.schemas.analysis_settings import AnalysisParameters, WHISPER_SIZES
from app.services.admin_settings import get_or_create_admin_config
from app.services.classification import get_active_classification_model
from app.services.classification_training import (
    classification_artifact_sha256,
    load_classification_artifact,
)
from app.services.persistence import log_system_event
from models.speech_to_text import ModelManager, check_model_readiness


def _parameters(config) -> AnalysisParameters:
    return AnalysisParameters(
        upload_max_duration_seconds=config.upload_max_duration_seconds,
        asr_model=config.asr_model_default,
        hook_duration_seconds=config.hook_duration,
    )


def _classification_snapshot(db: Session) -> dict:
    model = get_active_classification_model(db)
    if model is None:
        return {"model_id": None, "status": "unavailable"}
    result = {
        "model_id": model.model_id,
        "model_key": model.model_key,
        "model_version": model.model_version,
        "model_type": model.model_type,
        "training_sample_count": model.training_sample_count,
        "taxonomy_version": model.taxonomy_version,
        "status": model.status,
    }
    try:
        artifact = load_classification_artifact(model.artifact_path)
        if artifact["model_key"] != model.model_key or artifact["model_version"] != model.model_version:
            raise ValueError("Classification artifact does not match the model registry")
        if artifact.get("smoke_test_only"):
            raise ValueError("Smoke-test model cannot be used for analysis")
        result.update(
            unknown_threshold=float(artifact["unknown_threshold"]),
            artifact_sha256=classification_artifact_sha256(model.artifact_path),
            scope_validation_required=runtime_settings.classification_require_scope_validation,
            acceptance_policy_version=POLICY_VERSION,
            scope_validation=acceptance_summary(artifact.get("scope_policy")),
        )
    except Exception:
        result["status"] = "artifact_unavailable"
    return result


def get_analysis_settings(db: Session, *, admin: bool = False) -> dict:
    config = get_or_create_admin_config(db)
    parameters = _parameters(config)
    response = {
        **parameters.model_dump(),
        "config_id": config.config_id,
        "updated_at": config.updated_at.isoformat(),
        "asr_ready": bool(check_model_readiness(parameters.asr_model)["ready"]),
    }
    if not admin:
        return response
    response["whisper_models"] = [
        {"name": name, "ready": bool(check_model_readiness(name)["ready"])}
        for name in WHISPER_SIZES
    ]
    classification = _classification_snapshot(db)
    metrics = db.query(ModelEvaluationMetric).filter(
        ModelEvaluationMetric.model_id == classification.get("model_id"),
        ModelEvaluationMetric.language == "all",
        ModelEvaluationMetric.taxonomy_level == 3,
        or_(
            and_(ModelEvaluationMetric.taxonomy_leaf_key == "__overall__",
                 ModelEvaluationMetric.metric_name.in_(("accuracy", "f1_macro"))),
            and_(ModelEvaluationMetric.taxonomy_leaf_key == "unknown",
                 ModelEvaluationMetric.dataset_split == "out_of_scope",
                 ModelEvaluationMetric.metric_name == "unknown_recall"),
        ),
    ).order_by(ModelEvaluationMetric.dataset_split, ModelEvaluationMetric.metric_name).all() if classification.get("model_id") is not None else []
    classification["evaluation_metrics"] = [
        {"split": row.dataset_split, "metric": row.metric_name,
         "value": row.metric_value, "sample_size": row.sample_size}
        for row in metrics
    ]
    response["classification_model"] = classification
    return response


def save_analysis_settings(db: Session, parameters: AnalysisParameters, *, user_id: int) -> dict:
    if not check_model_readiness(parameters.asr_model)["ready"]:
        raise ValueError("Whisper model is not installed and ready on this server")
    try:
        # Verify that the local files can actually be loaded before committing.
        ModelManager.get_model(parameters.asr_model)
    except Exception as exc:
        raise ValueError("Whisper model could not be loaded; settings were not saved") from exc
    config = get_or_create_admin_config(db)
    before = _parameters(config).model_dump()
    config.upload_max_duration_seconds = parameters.upload_max_duration_seconds
    config.asr_model_default = parameters.asr_model
    config.hook_duration = parameters.hook_duration_seconds
    log_system_event(db, user_id=user_id, action="admin_analysis_settings_update", status="success",
                     detail=json.dumps({"before": before, "after": parameters.model_dump()}, sort_keys=True))
    db.commit()
    db.refresh(config)
    return get_analysis_settings(db, admin=True)


def capture_analysis_settings(db: Session) -> dict:
    settings = get_analysis_settings(db)
    if not settings["asr_ready"]:
        raise ValueError("The configured Whisper model is not ready; contact an administrator")
    classification = _classification_snapshot(db)
    if classification["status"] == "artifact_unavailable":
        raise ValueError("The active classification model artifact is unavailable")
    return {
        **settings,
        "schema_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "classification_model": classification,
    }
