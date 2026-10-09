"""Admin lifecycle for Outcome candidates, separate from category classifiers."""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.db import SessionLocal
from app.database.models import OutcomeModel, OutcomeModelMetric, OutcomeTrainingRun
from app.services.outcome_prediction_readiness import validate_protocol
from app.services.outcome_training import (
    activation_validation,
    load_training_inputs,
    train_and_validate_outcome_model,
)
from app.services.persistence import log_system_event


ROOT = Path(__file__).resolve().parents[2]
PHASE2_ROOT = ROOT / "artifacts" / "outcome-prediction" / "phase-2"
ARTIFACT_ROOT = ROOT / "artifacts" / "outcome-prediction" / "phase-3" / "registry"
PROTOCOL_PATH = ROOT / "docs" / "implementation" / "outcome-prediction-protocol-v1.json"
DATA_USE_PATH = ROOT / "docs" / "implementation" / "outcome-prediction-data-use-v1.json"
HEARTBEAT_SECONDS = 10
STALE_SECONDS = 180
LIVE_STATES = ("queued", "running")


class OutcomeTrainingConflict(ValueError):
    pass


def _json(value: str | None, fallback: Any = None) -> Any:
    if not value:
        return {} if fallback is None else fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return {} if fallback is None else fallback


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path.name}")
    return value


def _manifest_candidates() -> list[Path]:
    if not PHASE2_ROOT.is_dir():
        return []
    return sorted(
        PHASE2_ROOT.rglob("manifest.json"), key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def _find_manifest(manifest_sha256: str | None) -> tuple[Path, Path] | None:
    for manifest_path in _manifest_candidates():
        try:
            manifest = _load_json(manifest_path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if manifest_sha256 and manifest.get("manifest_sha256") != manifest_sha256:
            continue
        features_path = manifest_path.with_name("features.json")
        if features_path.is_file():
            return manifest_path, features_path
    return None


def _latest_blocked_report() -> dict[str, Any] | None:
    if not PHASE2_ROOT.is_dir():
        return None
    reports = sorted(
        PHASE2_ROOT.rglob("build-report.json"), key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in reports:
        try:
            value = _load_json(path)
            return {
                "status": value.get("status"),
                "active_source_rows": value.get("active_source_rows"),
                "structurally_eligible_rows": value.get("structurally_eligible_rows"),
                "training_allowed_rows": value.get("training_allowed_rows"),
                "data_use_gate": value.get("data_use_gate"),
            }
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return None


def outcome_preflight(manifest_sha256: str | None = None) -> dict[str, Any]:
    found = _find_manifest(manifest_sha256)
    if found is None:
        reason = "manifest_hash_not_found" if manifest_sha256 else "phase2_frozen_manifest_missing"
        return {
            "ready": False,
            "reason_codes": [reason],
            "requested_manifest_sha256": manifest_sha256,
            "latest_phase2_report": _latest_blocked_report(),
            "independent_test_opened": False,
            "production_eligible": False,
        }
    manifest_path, features_path = found
    protocol = _load_json(PROTOCOL_PATH)
    data_use = _load_json(DATA_USE_PATH)
    result = load_training_inputs(
        manifest_path=manifest_path,
        features_path=features_path,
        protocol=protocol,
        data_use_record=data_use,
        trusted_root=PHASE2_ROOT,
    )
    return {
        "ready": result["ready"],
        "reason_codes": result["reason_codes"],
        "manifest_sha256": result.get("manifest", {}).get("manifest_sha256"),
        "protocol_sha256": result.get("protocol_validation", {}).get("protocol_sha256"),
        "counts": result.get("counts"),
        "rights": result.get("rights"),
        "split_hashes": result.get("split_hashes"),
        "independent_test_opened": False,
        "production_eligible": False,
    }


def _log(db: Session, run: OutcomeTrainingRun, action: str, status: str) -> None:
    log_system_event(
        db, user_id=run.requested_by, action=action, status=status,
        detail=json.dumps({"run_id": run.run_id, "error": run.error}),
    )


def recover_stale_runs(db: Session) -> None:
    cutoff = datetime.utcnow() - timedelta(seconds=STALE_SECONDS)
    rows = db.query(OutcomeTrainingRun).filter(
        OutcomeTrainingRun.active_slot == 1,
        OutcomeTrainingRun.updated_at < cutoff,
    ).all()
    for row in rows:
        changed = db.query(OutcomeTrainingRun).filter(
            OutcomeTrainingRun.run_id == row.run_id,
            OutcomeTrainingRun.active_slot == 1,
            OutcomeTrainingRun.updated_at < cutoff,
        ).update({
            "status": "interrupted", "stage": "interrupted", "active_slot": None,
            "finished_at": datetime.utcnow(), "updated_at": datetime.utcnow(),
            "error": "Outcome training worker heartbeat expired",
        }, synchronize_session=False)
        if changed:
            db.refresh(row)
            _log(db, row, "outcome_training_interrupted", "error")
    db.commit()


def serialize_run(row: OutcomeTrainingRun) -> dict[str, Any]:
    result = _json(row.result_json)
    return {
        "run_id": row.run_id, "requested_by": row.requested_by,
        "status": row.status, "stage": row.stage, "progress": row.progress,
        "manifest_sha256": row.manifest_sha256,
        "protocol_sha256": row.protocol_sha256,
        "parameters": _json(row.parameters_json), "result": result or None,
        "artifact_path": row.artifact_path, "error": row.error,
        "created_at": row.created_at, "started_at": row.started_at,
        "updated_at": row.updated_at, "finished_at": row.finished_at,
    }


def list_training_runs(db: Session, *, limit: int = 20) -> list[dict[str, Any]]:
    recover_stale_runs(db)
    rows = db.query(OutcomeTrainingRun).order_by(
        OutcomeTrainingRun.created_at.desc(), OutcomeTrainingRun.run_id.desc()
    ).limit(limit).all()
    return [serialize_run(row) for row in rows]


def get_training_run(db: Session, run_id: str) -> dict[str, Any] | None:
    recover_stale_runs(db)
    row = db.get(OutcomeTrainingRun, run_id, populate_existing=True)
    return serialize_run(row) if row else None


def launch_training_worker(run_id: str) -> None:
    log_dir = ARTIFACT_ROOT / "worker_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / f"{run_id}.log").open("ab") as output:
        subprocess.Popen(
            [sys.executable, str(ROOT / "scripts" / "run_outcome_training.py"), "--run-id", run_id],
            cwd=ROOT, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
            close_fds=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )


def start_training_run(
    db: Session, *, user_id: int, manifest_sha256: str,
) -> dict[str, Any]:
    recover_stale_runs(db)
    if db.query(OutcomeTrainingRun).filter(OutcomeTrainingRun.active_slot == 1).first():
        raise OutcomeTrainingConflict("An Outcome training run is already queued or running")
    preflight = outcome_preflight(manifest_sha256)
    if not preflight["ready"]:
        raise ValueError("Outcome preflight blocked: " + ", ".join(preflight["reason_codes"]))
    run_id = str(uuid.uuid4())
    model_version = f"outcome-{datetime.utcnow():%Y%m%dT%H%M%S}-{run_id[:8]}"
    parameters = {
        "manifest_sha256": manifest_sha256,
        "model_version": model_version,
        "source_kind": "real",
        "independent_test_opened": False,
        "allow_network_download": False,
    }
    run = OutcomeTrainingRun(
        run_id=run_id, requested_by=user_id, active_slot=1,
        manifest_sha256=manifest_sha256,
        protocol_sha256=preflight["protocol_sha256"],
        parameters_json=json.dumps(parameters),
    )
    db.add(run)
    try:
        db.flush()
        _log(db, run, "outcome_training_requested", "success")
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise OutcomeTrainingConflict("Another Outcome run started at the same time") from exc
    try:
        launch_training_worker(run_id)
    except Exception:
        run.status = run.stage = "failed"
        run.active_slot = None
        run.error = "Could not start the hidden Outcome training worker"
        run.finished_at = run.updated_at = datetime.utcnow()
        _log(db, run, "outcome_training_failed", "error")
        db.commit()
    return serialize_run(run)


def _update_run(
    run_id: str, values: dict[str, Any], *, session_factory=SessionLocal,
) -> None:
    with session_factory() as db:
        changed = db.query(OutcomeTrainingRun).filter(
            OutcomeTrainingRun.run_id == run_id,
            OutcomeTrainingRun.active_slot == 1,
            OutcomeTrainingRun.status.in_(LIVE_STATES),
        ).update({**values, "updated_at": datetime.utcnow()}, synchronize_session=False)
        db.commit()
        if not changed:
            raise OutcomeTrainingConflict("Outcome training run is no longer active")


def _add_metric_rows(db: Session, model_id: int, report: dict[str, Any]) -> None:
    def add(split: str, phase: str, scope_type: str, scope_value: str,
            weighting: str, metrics: dict[str, Any]) -> None:
        for name in ("brier_score", "log_loss", "roc_auc", "pr_auc"):
            if name not in metrics:
                continue
            db.add(OutcomeModelMetric(
                model_id=model_id, dataset_split=split, phase=phase,
                scope_type=scope_type, scope_value=scope_value,
                weighting=weighting, metric_name=name, metric_value=metrics.get(name),
                metric_status=str(metrics.get("status") or "not_evaluable"),
                sample_size=int(metrics.get("sample_count") or 0),
                details=json.dumps({
                    "positive_count": metrics.get("positive_count"),
                    "negative_count": metrics.get("negative_count"),
                    "reason": metrics.get("reason"),
                }),
            ))

    selected = "metadata_topics_logistic_regression"
    for phase in ("before", "after"):
        evaluation = report["tuning_metrics"][selected][phase]
        for weighting, metrics in evaluation["overall"].items():
            add("tuning", phase, "overall", "__overall__", weighting, metrics)
        for scope_type, scopes in evaluation["by_scope"].items():
            for scope_value, weightings in scopes.items():
                for weighting, metrics in weightings.items():
                    add("tuning", phase, scope_type, scope_value, weighting, metrics)
    for phase in ("before", "after"):
        evaluation = report["calibration_metrics"][selected][phase]
        for weighting, metrics in evaluation["overall"].items():
            add("calibration", phase, "overall", "__overall__", weighting, metrics)


def execute_training_run(run_id: str, *, session_factory=SessionLocal) -> None:
    stop = threading.Event()

    def heartbeat() -> None:
        while not stop.wait(HEARTBEAT_SECONDS):
            try:
                _update_run(run_id, {}, session_factory=session_factory)
            except OutcomeTrainingConflict:
                return
            except Exception:
                continue

    with session_factory() as db:
        claimed = db.query(OutcomeTrainingRun).filter(
            OutcomeTrainingRun.run_id == run_id,
            OutcomeTrainingRun.status == "queued",
            OutcomeTrainingRun.active_slot == 1,
        ).update({
            "status": "running", "stage": "preflight", "progress": 0.05,
            "started_at": datetime.utcnow(), "updated_at": datetime.utcnow(),
        }, synchronize_session=False)
        db.commit()
        if not claimed:
            return
        run = db.get(OutcomeTrainingRun, run_id)
        parameters = _json(run.parameters_json)
        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            found = _find_manifest(run.manifest_sha256)
            if found is None:
                raise ValueError("Frozen manifest disappeared or its hash changed")
            preflight = outcome_preflight(run.manifest_sha256)
            if not preflight["ready"]:
                raise ValueError("Outcome preflight no longer passes: " + ", ".join(preflight["reason_codes"]))
            manifest_path, features_path = found
            output_dir = ARTIFACT_ROOT / parameters["model_version"]
            _update_run(run_id, {"stage": "training", "progress": 0.2}, session_factory=session_factory)
            report = train_and_validate_outcome_model(
                manifest_path=manifest_path, features_path=features_path,
                protocol_path=PROTOCOL_PATH, data_use_path=DATA_USE_PATH,
                output_dir=output_dir, trusted_phase2_root=PHASE2_ROOT,
                source_kind="real",
            )
            if not report.get("artifact_created"):
                raise ValueError("Outcome training was blocked during execution")
            db.expire_all()
            run = db.get(OutcomeTrainingRun, run_id)
            if run.active_slot != 1:
                return
            model = OutcomeModel(
                run_id=run_id, model_version=parameters["model_version"],
                target_version=report["target_version"],
                protocol_sha256=report["protocol_sha256"],
                feature_schema_sha256=report["feature_schema_sha256"],
                manifest_sha256=report["manifest_sha256"],
                split_hashes_json=json.dumps(report["split_hashes"]),
                calibration_version="weighted-sigmoid-v1",
                source_kind="real", status=report["qualification"]["status"],
                is_active=False, artifact_path=report["artifact_path"],
                artifact_sha256=report["artifact_sha256"],
                metrics_json=json.dumps({
                    "tuning": report["tuning_metrics"],
                    "calibration": report["calibration_metrics"],
                    "bootstrap": report["paired_channel_bootstrap"],
                    "qualification": report["qualification"],
                }),
                evaluated_scopes_json=json.dumps([
                    "overall", "category", "confirmed_format", "age_context"
                ]),
                library_versions_json=json.dumps(report["library_versions"]),
                training_sample_count=sum(
                    int(report["partition_counts"][role]["videos"])
                    for role in ("fit", "tuning", "calibration")
                ),
                independent_test_passed=False, production_eligible=False,
                trained_at=datetime.utcnow(),
            )
            db.add(model)
            db.flush()
            _add_metric_rows(db, model.model_id, report)
            run.status = "completed"
            run.stage = report["qualification"]["status"]
            run.progress = 1.0
            run.result_json = json.dumps({
                "model_id": model.model_id,
                "status": model.status,
                "active_model_changed": False,
                "independent_test_opened": False,
                "production_eligible": False,
            })
            run.artifact_path = str(output_dir)
            run.error = None
            run.active_slot = None
            run.finished_at = run.updated_at = datetime.utcnow()
            _log(db, run, "outcome_training_completed", "success")
            db.commit()
        except Exception as exc:
            db.rollback()
            run = db.get(OutcomeTrainingRun, run_id)
            if run and run.active_slot == 1:
                run.status = run.stage = "failed"
                run.error = str(exc)[:2000]
                run.active_slot = None
                run.finished_at = run.updated_at = datetime.utcnow()
                _log(db, run, "outcome_training_failed", "error")
                db.commit()
        finally:
            stop.set()
            thread.join(timeout=5)


def _serialize_model(row: OutcomeModel) -> dict[str, Any]:
    data_use = _load_json(DATA_USE_PATH)
    gate = activation_validation({
        "status": row.status,
        "independent_test_passed": row.independent_test_passed,
        "production_eligible": row.production_eligible,
    }, data_use)
    return {
        "model_id": row.model_id, "run_id": row.run_id,
        "model_version": row.model_version, "target_version": row.target_version,
        "status": row.status, "is_active": bool(row.is_active),
        "source_kind": row.source_kind, "manifest_sha256": row.manifest_sha256,
        "protocol_sha256": row.protocol_sha256,
        "feature_schema_sha256": row.feature_schema_sha256,
        "artifact_sha256": row.artifact_sha256,
        "training_sample_count": row.training_sample_count,
        "independent_test_passed": bool(row.independent_test_passed),
        "production_eligible": bool(row.production_eligible),
        "can_activate": gate["can_activate"],
        "activation_reason_codes": gate["reason_codes"],
        "force_override_supported": False,
        "trained_at": row.trained_at,
    }


def list_models(db: Session, *, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    query = db.query(OutcomeModel)
    rows = query.order_by(OutcomeModel.model_id.desc()).offset(offset).limit(limit).all()
    return {"total": query.count(), "items": [_serialize_model(row) for row in rows]}


def model_detail(db: Session, model_id: int) -> dict[str, Any] | None:
    row = db.get(OutcomeModel, model_id)
    if row is None:
        return None
    result = _serialize_model(row)
    result.update({
        "split_hashes": _json(row.split_hashes_json),
        "metrics": _json(row.metrics_json),
        "evaluated_scopes": _json(row.evaluated_scopes_json, []),
        "library_versions": _json(row.library_versions_json),
        "artifact_available": Path(row.artifact_path).is_file(),
    })
    return result
