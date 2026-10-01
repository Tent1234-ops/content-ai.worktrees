"""Durable admin training runs around the existing evaluated classifier pipeline."""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.db import SessionLocal
from app.database.models import ClassificationModel, ModelEvaluationMetric, ModelTrainingRun, SystemConfig
from app.services.admin_settings import get_or_create_admin_config
from app.services.classification import get_active_classification_model
from app.services.classification_acceptance import POLICY_VERSION
from app.services.classification_collection_plan import build_collection_plan
from app.services.classification_readiness import classification_model_snapshot
from app.services.classification_training import (
    DEFAULT_GROUPED_CV_FOLDS, MODEL_PROMOTION_THRESHOLD, UNKNOWN_CONFIDENCE_THRESHOLD,
    activate_classification_model, classification_artifact_sha256,
    prepare_classification_dataset, train_and_evaluate_classification_models,
)
from app.services.persistence import log_system_event

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_ROOT = ROOT / "artifacts" / "classification_training"
TRAINING_LEAVES = ("phone", "camera", "laptop")
HEARTBEAT_SECONDS = 10
STALE_SECONDS = 180
LIVE_STATES = ("queued", "running")


class TrainingConflict(ValueError):
    pass


def _json(value: str | None) -> dict:
    if not value:
        return {}
    parsed = json.loads(value)
    return parsed if isinstance(parsed, dict) else {}


def training_dataset(db: Session) -> dict:
    report = prepare_classification_dataset(db, required_leaf_keys=TRAINING_LEAVES).report
    report["collection_plan"] = build_collection_plan(report)
    return report


def _log(db: Session, run: ModelTrainingRun, action: str, status: str) -> None:
    log_system_event(db, user_id=run.requested_by, action=action, status=status,
                     detail=json.dumps({"run_id": run.run_id, "error": run.error}))


def recover_stale_runs(db: Session) -> None:
    cutoff = datetime.utcnow() - timedelta(seconds=STALE_SECONDS)
    rows = db.query(ModelTrainingRun).filter(
        ModelTrainingRun.active_slot == 1, ModelTrainingRun.updated_at < cutoff,
    ).all()
    for row in rows:
        changed = db.query(ModelTrainingRun).filter(
            ModelTrainingRun.run_id == row.run_id,
            ModelTrainingRun.active_slot == 1, ModelTrainingRun.updated_at < cutoff,
        ).update({"status": "interrupted", "stage": "interrupted", "active_slot": None,
                  "finished_at": datetime.utcnow(), "error": "Training worker heartbeat expired"}, synchronize_session=False)
        if changed:
            db.refresh(row)
            _log(db, row, "classification_training_interrupted", "error")
    db.commit()


def serialize_run(row: ModelTrainingRun) -> dict:
    result = _json(row.result_json)
    return {
        "run_id": row.run_id, "status": row.status, "stage": row.stage,
        "current_model_key": row.current_model_key, "requested_by": row.requested_by,
        "created_at": row.created_at, "started_at": row.started_at,
        "updated_at": row.updated_at, "finished_at": row.finished_at,
        "parameters": _json(row.parameters_json), "error": row.error,
        "result": {
            "dataset": result.get("dataset"), "best_model": result.get("best_model"),
            "model_ids": [m["model_id"] for m in result.get("models", [])],
            "skipped_models": result.get("skipped_models", []),
            "active_model_changed": False,
        } if result else None,
    }


def list_training_runs(db: Session, *, limit: int = 10) -> list[dict]:
    recover_stale_runs(db)
    return [serialize_run(row) for row in db.query(ModelTrainingRun).order_by(
        ModelTrainingRun.created_at.desc(), ModelTrainingRun.run_id.desc()).limit(limit).all()]


def get_training_run(db: Session, run_id: str) -> dict | None:
    recover_stale_runs(db)
    row = db.get(ModelTrainingRun, run_id, populate_existing=True)
    return serialize_run(row) if row else None


def launch_training_worker(run_id: str) -> None:
    log_dir = ARTIFACT_ROOT / "worker_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / f"{run_id}.log").open("ab") as output:
        subprocess.Popen(
            [sys.executable, str(ROOT / "scripts" / "run_admin_training.py"), "--run-id", run_id],
            cwd=ROOT, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
            close_fds=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )


def start_training_run(db: Session, *, user_id: int, dataset_fingerprint: str) -> dict:
    recover_stale_runs(db)
    if db.query(ModelTrainingRun).filter(ModelTrainingRun.active_slot == 1).first():
        raise TrainingConflict("A training run is already queued or running")
    dataset = training_dataset(db)
    if dataset["dataset_fingerprint"] != dataset_fingerprint:
        raise TrainingConflict("Dataset changed; refresh the page before starting training")
    if not dataset["ready"]:
        raise ValueError("Dataset does not meet the minimum per-category and channel-split requirements")
    run_id = str(uuid.uuid4())
    parameters = {
        "required_leaf_keys": list(TRAINING_LEAVES),
        "dataset_fingerprint": dataset_fingerprint,
        "model_version": f"web-{datetime.utcnow():%Y%m%dT%H%M%S}-{run_id[:8]}",
        "unknown_threshold": UNKNOWN_CONFIDENCE_THRESHOLD,
        "promotion_threshold": MODEL_PROMOTION_THRESHOLD,
        "grouped_cv_folds": DEFAULT_GROUPED_CV_FOLDS,
        "enforce_phase22_gate": True, "allow_embedding_download": False,
    }
    run = ModelTrainingRun(run_id=run_id, requested_by=user_id, active_slot=1,
                           parameters_json=json.dumps(parameters))
    db.add(run)
    try:
        db.flush()
        _log(db, run, "classification_training_requested", "success")
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise TrainingConflict("Another training run was started at the same time") from exc
    try:
        launch_training_worker(run_id)
    except Exception:
        run.status = run.stage = "failed"
        run.active_slot = None
        run.finished_at = datetime.utcnow()
        run.error = "Could not start the background training worker"
        _log(db, run, "classification_training_failed", "error")
        db.commit()
    return serialize_run(run)


def _update_run(run_id: str, values: dict, *, session_factory=SessionLocal) -> None:
    with session_factory() as db:
        changed = db.query(ModelTrainingRun).filter(
            ModelTrainingRun.run_id == run_id, ModelTrainingRun.active_slot == 1,
            ModelTrainingRun.status.in_(LIVE_STATES),
        ).update({**values, "updated_at": datetime.utcnow()}, synchronize_session=False)
        db.commit()
        if not changed:
            raise TrainingConflict("Training run is no longer active")


def execute_training_run(run_id: str, *, session_factory=SessionLocal) -> None:
    stop = threading.Event()

    def progress(stage: str, model_key: str | None) -> None:
        _update_run(run_id, {"stage": stage, "current_model_key": model_key}, session_factory=session_factory)

    def heartbeat() -> None:
        while not stop.wait(HEARTBEAT_SECONDS):
            try:
                _update_run(run_id, {}, session_factory=session_factory)
            except TrainingConflict:
                return
            except Exception:
                # A temporary DB outage must not kill fitting; stale runs remain detectable.
                continue

    with session_factory() as db:
        claimed = db.query(ModelTrainingRun).filter(
            ModelTrainingRun.run_id == run_id, ModelTrainingRun.status == "queued",
            ModelTrainingRun.active_slot == 1,
        ).update({"status": "running", "stage": "preparing", "started_at": datetime.utcnow(),
                  "updated_at": datetime.utcnow()}, synchronize_session=False)
        db.commit()
        if not claimed:
            return
        run = db.get(ModelTrainingRun, run_id)
        parameters = _json(run.parameters_json)
        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            if training_dataset(db)["dataset_fingerprint"] != parameters["dataset_fingerprint"]:
                raise TrainingConflict("Dataset changed while the run was queued; start a new run")
            result = train_and_evaluate_classification_models(
                db, artifact_root=ARTIFACT_ROOT,
                embedding_cache_folder=ROOT / "models_cache" / "sentence_transformers",
                progress_callback=progress,
                **{k: v for k, v in parameters.items() if k != "dataset_fingerprint"},
            )
            db.refresh(run)
            if run.active_slot != 1:
                return
            run.status = "completed" if result["status"] == "evaluated" else "not_ready"
            run.stage = run.status
            run.result_json = json.dumps(result, ensure_ascii=False)
            run.error = None
            run.active_slot = None
            run.finished_at = run.updated_at = datetime.utcnow()
            _log(db, run, "classification_training_completed", "success")
            db.commit()
        except Exception as exc:
            db.rollback()
            db.refresh(run)
            if run.active_slot == 1:
                run.status = run.stage = "failed"
                run.error = str(exc)[:2000]
                run.active_slot = None
                run.finished_at = run.updated_at = datetime.utcnow()
                _log(db, run, "classification_training_failed", "error")
                db.commit()
        finally:
            stop.set()
            thread.join(timeout=5)


def model_summary(model: ClassificationModel, metrics: list[ModelEvaluationMetric]) -> dict:
    gate = next((r for r in metrics if r.dataset_split == "promotion_gate" and r.metric_name == "passed"), None)
    reload_check = next((r for r in metrics if r.dataset_split == "artifact_check" and r.metric_name == "reload_classify_passed"), None)
    qualification = _json(gate.details) if gate else {}
    artifact_exists = bool(model.artifact_path and Path(model.artifact_path).is_file())
    evaluated = bool(gate and gate.metric_value == 1 and reload_check and reload_check.metric_value == 1)
    scope_evaluated = (qualification.get("scope_validation_status") == "validated"
                       and qualification.get("scope_policy_version") == POLICY_VERSION)
    snapshot = classification_model_snapshot(model)
    readiness = snapshot["readiness"]
    return {
        "model_id": model.model_id, "model_key": model.model_key, "model_version": model.model_version,
        "model_type": model.model_type, "status": model.status, "is_active": bool(model.is_active),
        "trained_at": model.trained_at, "training_sample_count": model.training_sample_count,
        "unknown_threshold": snapshot.get("unknown_threshold", qualification.get("unknown_threshold")), "qualification": qualification,
        "artifact_available": artifact_exists,
        "readiness": readiness,
        "can_activate": (model.status == "qualified" and evaluated and scope_evaluated
                         and readiness["artifact_usable"] and readiness["scope_policy_valid"]
                         and readiness["scope_test_passed"] and not model.is_active),
        "metrics": [
            {"split": r.dataset_split, "metric": r.metric_name, "value": r.metric_value, "sample_size": r.sample_size}
            for r in metrics if r.taxonomy_leaf_key in ("__overall__", "unknown")
            and r.metric_name in ("accuracy", "f1_macro", "unknown_recall")
        ],
    }


def _model_metrics(db: Session, ids: list[int]) -> list[ModelEvaluationMetric]:
    return db.query(ModelEvaluationMetric).filter(
        ModelEvaluationMetric.model_id.in_(ids), ModelEvaluationMetric.language == "all",
        ModelEvaluationMetric.taxonomy_level == 3,
    ).order_by(ModelEvaluationMetric.dataset_split, ModelEvaluationMetric.metric_name).all()


def list_models(db: Session, *, limit: int = 20, offset: int = 0) -> dict:
    query = db.query(ClassificationModel)
    models = query.order_by(ClassificationModel.model_id.desc()).offset(offset).limit(limit).all()
    metrics = _model_metrics(db, [m.model_id for m in models])
    return {"total": query.count(), "items": [model_summary(m, [r for r in metrics if r.model_id == m.model_id]) for m in models]}


def model_detail(db: Session, model_id: int) -> dict | None:
    model = db.get(ClassificationModel, model_id)
    if not model:
        return None
    metrics = _model_metrics(db, [model_id])
    result = model_summary(model, metrics)
    result["per_category"] = [{"split": r.dataset_split, "category": r.taxonomy_leaf_key,
                               "metric": r.metric_name, "value": r.metric_value, "sample_size": r.sample_size}
                              for r in metrics if r.metric_name in ("precision", "recall", "f1")]
    result["confusion_matrices"] = [{"split": r.dataset_split, **_json(r.details)}
                                    for r in metrics if r.metric_name == "confusion_matrix"]
    return result


def training_overview(db: Session) -> dict:
    active = get_active_classification_model(db)
    return {"dataset": training_dataset(db), "runs": list_training_runs(db),
            "models": list_models(db), "active_model": model_detail(db, active.model_id) if active else None,
            "policy": {"promotion_threshold": MODEL_PROMOTION_THRESHOLD,
                       "unknown_threshold": UNKNOWN_CONFIDENCE_THRESHOLD, "grouped_cv_folds": DEFAULT_GROUPED_CV_FOLDS}}


def activate_evaluated_model(db: Session, model_id: int, *, expected_active_model_id: int | None, user_id: int) -> dict:
    config = get_or_create_admin_config(db)
    db.query(SystemConfig).filter(SystemConfig.config_id == config.config_id).with_for_update().one()
    active = get_active_classification_model(db)
    if (active.model_id if active else None) != expected_active_model_id:
        raise TrainingConflict("Active model changed; refresh before confirming activation")
    detail = model_detail(db, model_id)
    if detail is None:
        raise LookupError("Model not found")
    if not detail["can_activate"]:
        raise ValueError("Model has not passed evaluation, is unavailable, or is already active")
    model = db.get(ClassificationModel, model_id)
    evaluation_path = Path(model.artifact_path).with_name("evaluation.json")
    if not evaluation_path.is_file():
        raise ValueError("Model evaluation artifact is missing")
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    if evaluation.get("artifact_sha256") != classification_artifact_sha256(model.artifact_path):
        raise ValueError("Model artifact differs from the evaluated file; activation blocked")
    return activate_classification_model(db, model_id, user_id=user_id)
