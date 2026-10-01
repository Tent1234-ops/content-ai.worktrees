import json
from datetime import datetime, timezone

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.database.models import ModelEvaluationMetric
from app.schemas.analysis_settings import AnalysisParameters, WHISPER_SIZES
from app.services.admin_settings import get_or_create_admin_config
from app.services.classification import get_active_classification_model
from app.services.classification_readiness import classification_model_snapshot
from app.services.persistence import log_system_event
from models.speech_to_text import ModelManager, check_model_readiness


def _parameters(config) -> AnalysisParameters:
    return AnalysisParameters(
        upload_max_duration_seconds=config.upload_max_duration_seconds,
        asr_model=config.asr_model_default,
        hook_duration_seconds=config.hook_duration,
    )


def _classification_snapshot(db: Session) -> dict:
    return classification_model_snapshot(get_active_classification_model(db))


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
