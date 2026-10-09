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
from app.database.models import (
    OutcomeModel,
    OutcomeModelMetric,
    OutcomeTrainingRun,
    SystemConfig,
)
from app.services.admin_settings import get_or_create_admin_config
from app.services.outcome_prediction_readiness import validate_protocol
from app.services.outcome_training import (
    activation_validation,
    load_outcome_artifact,
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
        latest = _latest_blocked_report()
        rights = (latest or {}).get("data_use_gate") or {}
        return {
            "ready": False,
            "reason_codes": sorted(set([
                reason, *(rights.get("reason_codes") or []),
            ])),
            "requested_manifest_sha256": manifest_sha256,
            "latest_phase2_report": latest,
            "rights": rights,
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
                    "partition_counts": report["partition_counts"],
                    "independent_test": {
                        "status": "sealed_until_phase_6_evaluation",
                        "opened": False,
                        "metrics": None,
                    },
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
    gate = dict(activation_validation({
        "status": row.status,
        "independent_test_passed": row.independent_test_passed,
        "production_eligible": row.production_eligible,
    }, data_use))
    gate["reason_codes"] = list(gate.get("reason_codes") or [])
    artifact_available = Path(row.artifact_path).is_file()
    if not artifact_available:
        gate["reason_codes"].append("outcome_artifact_missing")
    required_hashes = (
        row.protocol_sha256,
        row.feature_schema_sha256,
        row.manifest_sha256,
        row.artifact_sha256,
    )
    if any(len(str(value or "")) != 64 for value in required_hashes):
        gate["reason_codes"].append("outcome_version_hash_invalid")
    split_hashes = _json(row.split_hashes_json)
    if not all(split_hashes.get(role) for role in (
        "fit", "tuning", "calibration", "independent_test"
    )):
        gate["reason_codes"].append("outcome_split_hashes_incomplete")
    required_scopes = {
        "overall", "category", "confirmed_format", "age_context",
    }
    evaluated_scopes = set(_json(row.evaluated_scopes_json, []))
    if not required_scopes.issubset(evaluated_scopes):
        gate["reason_codes"].append("outcome_evaluated_scopes_incomplete")
    if row.source_kind != "real":
        gate["reason_codes"] = sorted(set([
            *gate["reason_codes"], "synthetic_fixture_not_activatable",
        ]))
        gate["can_activate"] = False
    if row.is_active:
        gate["reason_codes"] = sorted(set([
            *gate["reason_codes"], "model_already_active",
        ]))
        gate["can_activate"] = False
    gate["reason_codes"] = sorted(set(gate["reason_codes"]))
    gate["can_activate"] = bool(gate.get("can_activate")) and not gate["reason_codes"]
    return {
        "model_id": row.model_id, "run_id": row.run_id,
        "model_version": row.model_version, "target_version": row.target_version,
        "status": row.status, "is_active": bool(row.is_active),
        "source_kind": row.source_kind, "manifest_sha256": row.manifest_sha256,
        "protocol_sha256": row.protocol_sha256,
        "feature_schema_sha256": row.feature_schema_sha256,
        "artifact_sha256": row.artifact_sha256,
        "training_sample_count": row.training_sample_count,
        "artifact_available": artifact_available,
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


def active_model(db: Session) -> dict[str, Any] | None:
    rows = db.query(OutcomeModel).filter(OutcomeModel.is_active.is_(True)).all()
    if len(rows) > 1:
        raise OutcomeTrainingConflict("Multiple active Outcome models require repair")
    return _serialize_model(rows[0]) if rows else None


def training_overview(db: Session, *, model_limit: int = 20) -> dict[str, Any]:
    return {
        "preflight": outcome_preflight(),
        "runs": list_training_runs(db, limit=20),
        "models": list_models(db, limit=model_limit),
        "active_model": active_model(db),
        "independent_test_opened": False,
    }


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
        "metric_rows": [
            {
                "dataset_split": metric.dataset_split,
                "phase": metric.phase,
                "scope_type": metric.scope_type,
                "scope_value": metric.scope_value,
                "weighting": metric.weighting,
                "metric_name": metric.metric_name,
                "metric_value": metric.metric_value,
                "metric_status": metric.metric_status,
                "sample_size": metric.sample_size,
                "details": _json(metric.details),
            }
            for metric in db.query(OutcomeModelMetric).filter_by(
                model_id=model_id
            ).order_by(
                OutcomeModelMetric.dataset_split,
                OutcomeModelMetric.phase,
                OutcomeModelMetric.scope_type,
                OutcomeModelMetric.scope_value,
                OutcomeModelMetric.weighting,
                OutcomeModelMetric.metric_name,
            ).all()
        ],
    })
    return result


def activate_model(
    db: Session,
    model_id: int,
    *,
    expected_active_model_id: int | None,
    user_id: int,
) -> dict[str, Any]:
    """Activate a qualified real Outcome model, or roll back to one, atomically."""
    config = get_or_create_admin_config(db)
    db.query(SystemConfig).filter(
        SystemConfig.config_id == config.config_id
    ).with_for_update().one()

    active_rows = db.query(OutcomeModel).filter(
        OutcomeModel.is_active.is_(True)
    ).with_for_update().all()
    if len(active_rows) > 1:
        raise OutcomeTrainingConflict("Multiple active Outcome models require repair")
    current = active_rows[0] if active_rows else None
    if (current.model_id if current else None) != expected_active_model_id:
        raise OutcomeTrainingConflict(
            "Active Outcome model changed; refresh before confirming activation"
        )

    target = db.get(OutcomeModel, model_id)
    if target is None:
        raise LookupError("Outcome model not found")
    detail = _serialize_model(target)
    if not detail["can_activate"]:
        reasons = ", ".join(detail["activation_reason_codes"])
        raise ValueError(f"Outcome model activation blocked: {reasons}")

    load_outcome_artifact(
        Path(target.artifact_path),
        trusted_root=ARTIFACT_ROOT,
        expected_sha256=target.artifact_sha256,
        expected_protocol_sha256=target.protocol_sha256,
        expected_feature_schema_sha256=target.feature_schema_sha256,
    )
    previous_id = current.model_id if current else None
    if current is not None:
        current.is_active = False
    target.is_active = True
    log_system_event(
        db,
        user_id=user_id,
        action="outcome_model_activate",
        status="success",
        detail=json.dumps({
            "previous_model_id": previous_id,
            "model_id": target.model_id,
            "rollback": previous_id is not None and target.model_id < previous_id,
        }),
    )
    db.commit()
    db.refresh(target)
    return _serialize_model(target)
