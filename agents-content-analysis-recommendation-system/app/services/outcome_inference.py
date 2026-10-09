"""Fail-closed Outcome Prediction inference for frozen analysis snapshots.

The probability produced here is reference-relative.  It is not a forecast of
views and it is not an estimate of the causal effect of a recommendation.
"""
from __future__ import annotations

import copy
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from sqlalchemy.orm import Session

from app.database.models import OutcomeModel
from app.services.outcome_dataset import build_feature_record
from app.services.outcome_prediction_readiness import (
    data_use_gate,
    sha256_json,
    validate_protocol,
)
from app.services.outcome_training import (
    TRAINING_SUPPORT_VERSION,
    _matrix,
    _positive_probability,
    _topic_signature,
    load_outcome_artifact,
)
from app.services.recommendation_evidence import fingerprint, text_hash


ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = ROOT / "docs" / "implementation" / "outcome-prediction-protocol-v1.json"
DATA_USE_PATH = ROOT / "docs" / "implementation" / "outcome-prediction-data-use-v1.json"
ARTIFACT_ROOT = ROOT / "artifacts" / "outcome-prediction" / "phase-3" / "registry"

SCHEMA_VERSION = "outcome-assessment-v1"
SCENARIO_SCHEMA_VERSION = "outcome-scenario-v1"
SUPPORTED_CATEGORIES = {"phone", "camera", "laptop"}
SUPPORTED_FORMATS = {"short_form", "long_form"}
FULL_TRANSCRIPT_SCOPES = {"full_clip", "full_video"}
LIMITATIONS = [
    "ค่าประเมินนี้หมายถึงโอกาสอยู่เหนือค่ากลางของกลุ่มอ้างอิงที่ระบุ ไม่ใช่การคาดการณ์ยอดวิวจริง",
    "ผลเป็นความสัมพันธ์จากข้อมูลเชิงสังเกต ไม่ได้พิสูจน์ว่าการเพิ่มหัวข้อทำให้ยอดวิวเพิ่ม",
    "ชื่อช่อง งบโฆษณา ภาพปก เวลาเผยแพร่ และปัจจัยภายนอกอื่นอาจมีผลแต่ไม่ได้อยู่ในโมเดลรุ่นนี้",
]

_ARTIFACT_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}
_CACHE_LOCK = Lock()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _base_assessment(
    *,
    status: str,
    reason_codes: list[str] | None = None,
    protocol: dict[str, Any] | None = None,
    transcript_sha256: str | None = None,
    evidence_topic_ids: list[str] | None = None,
    evidence_pointers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    protocol = protocol or _load_json(PROTOCOL_PATH)
    validation = validate_protocol(protocol) if protocol else {
        "protocol_sha256": None,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "reason_codes": sorted(set(reason_codes or [])),
        "target_version": (protocol.get("target") or {}).get("version"),
        "protocol_version": protocol.get("protocol_version"),
        "protocol_sha256": validation.get("protocol_sha256"),
        "feature_version": (protocol.get("feature_policy") or {}).get("version"),
        "model_id": None,
        "model_version": None,
        "artifact_sha256": None,
        "calibration_version": None,
        "dataset_manifest_sha256": None,
        "split_manifest_sha256": None,
        "reference_cutoff": None,
        "input_transcript_sha256": transcript_sha256,
        "context": None,
        "evaluated_scope": None,
        "probability": None,
        "support_summary": None,
        "evidence_topic_ids": list(dict.fromkeys(evidence_topic_ids or [])),
        "evidence_pointers": copy.deepcopy(evidence_pointers or []),
        "limitations": list(LIMITATIONS),
        "assessed_at": _utc_now(),
        "feature_snapshot": None,
        "fixture_only": False,
    }


def legacy_outcome_assessment() -> dict[str, Any]:
    result = _base_assessment(
        status="legacy_not_assessed",
        reason_codes=["saved_before_outcome_assessment_v1"],
    )
    # Legacy reads are deterministic and never pretend an assessment happened now.
    result["assessed_at"] = None
    return result


def withdraw_outcome_assessment(
    assessment: dict[str, Any], *, reason: str, inaccessible: bool = False,
) -> dict[str, Any]:
    """Create an explicit redacted status without reconstructing withdrawn data."""
    result = copy.deepcopy(assessment) if isinstance(assessment, dict) else legacy_outcome_assessment()
    result["status"] = "inaccessible" if inaccessible else "withdrawn"
    result["reason_codes"] = sorted(set([*(result.get("reason_codes") or []), reason]))
    result["probability"] = None
    result["support_summary"] = None
    result["evidence_pointers"] = []
    result["feature_snapshot"] = None
    return result


def _classification_status(classification: dict[str, Any], category: str) -> list[str]:
    acceptance = classification.get("acceptance") or {}
    classified = str(
        classification.get("taxonomy_leaf_key")
        or classification.get("domain")
        or category
        or "unknown"
    )
    reasons = []
    if classified not in SUPPORTED_CATEGORIES or category not in SUPPORTED_CATEGORIES:
        reasons.append("unsupported_or_unknown_category")
    if classified != category:
        reasons.append("accepted_category_mismatch")
    if classification.get("is_unknown") is not False:
        reasons.append("classifier_returned_unknown")
    if acceptance.get("accepted") is not True:
        reasons.append(str(acceptance.get("reason") or "classification_acceptance_missing"))
    return sorted(set(reasons))


def _active_model_snapshot(db: Session) -> tuple[dict[str, Any] | None, list[str]]:
    rows = db.query(OutcomeModel).filter(OutcomeModel.is_active.is_(True)).order_by(
        OutcomeModel.model_id
    ).all()
    if not rows:
        return None, ["active_outcome_model_missing"]
    if len(rows) != 1:
        return None, ["multiple_active_outcome_models"]
    row = rows[0]
    return {
        "model_id": int(row.model_id),
        "model_version": row.model_version,
        "target_version": row.target_version,
        "protocol_sha256": row.protocol_sha256,
        "feature_schema_sha256": row.feature_schema_sha256,
        "manifest_sha256": row.manifest_sha256,
        "split_hashes": _parse_json(row.split_hashes_json, {}),
        "calibration_version": row.calibration_version,
        "source_kind": row.source_kind,
        "status": row.status,
        "artifact_path": row.artifact_path,
        "artifact_sha256": row.artifact_sha256,
        "independent_test_passed": bool(row.independent_test_passed),
        "production_eligible": bool(row.production_eligible),
    }, []


def _parse_json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
    except (TypeError, ValueError):
        return default
    return parsed


def _model_snapshot_by_id(db: Session, model_id: int) -> dict[str, Any] | None:
    row = db.get(OutcomeModel, int(model_id))
    if row is None:
        return None
    return {
        "model_id": int(row.model_id),
        "model_version": row.model_version,
        "target_version": row.target_version,
        "protocol_sha256": row.protocol_sha256,
        "feature_schema_sha256": row.feature_schema_sha256,
        "manifest_sha256": row.manifest_sha256,
        "split_hashes": _parse_json(row.split_hashes_json, {}),
        "calibration_version": row.calibration_version,
        "source_kind": row.source_kind,
        "status": row.status,
        "artifact_path": row.artifact_path,
        "artifact_sha256": row.artifact_sha256,
        "independent_test_passed": bool(row.independent_test_passed),
        "production_eligible": bool(row.production_eligible),
    }


def _load_cached_artifact(model: dict[str, Any]) -> dict[str, Any]:
    key = (
        model["model_id"], model["artifact_sha256"], model["artifact_path"],
        model["protocol_sha256"], model["feature_schema_sha256"],
    )
    with _CACHE_LOCK:
        cached = _ARTIFACT_CACHE.get(key)
    if cached is not None:
        return cached
    loaded = load_outcome_artifact(
        Path(model["artifact_path"]),
        trusted_root=ARTIFACT_ROOT,
        expected_sha256=model["artifact_sha256"],
        expected_protocol_sha256=model["protocol_sha256"],
        expected_feature_schema_sha256=model["feature_schema_sha256"],
    )
    with _CACHE_LOCK:
        _ARTIFACT_CACHE[key] = loaded
    return loaded


def clear_outcome_artifact_cache() -> None:
    with _CACHE_LOCK:
        _ARTIFACT_CACHE.clear()


def _qualification_reasons(
    model: dict[str, Any], artifact: dict[str, Any] | None, *, allow_synthetic_fixture: bool,
) -> list[str]:
    reasons = []
    if model.get("status") != "qualified":
        reasons.append("model_status_not_qualified")
    if model.get("independent_test_passed") is not True:
        reasons.append("independent_test_not_passed")
    if model.get("production_eligible") is not True:
        reasons.append("production_eligibility_false")
    if model.get("source_kind") == "synthetic_fixture" and not allow_synthetic_fixture:
        reasons.append("synthetic_fixture_not_allowed_for_live_serving")
    if artifact is not None:
        qualification = artifact.get("qualification") or {}
        if qualification.get("status") != "qualified" and qualification.get("qualified") is not True:
            reasons.append("artifact_not_qualified")
        if artifact.get("production_eligible") is not True:
            reasons.append("artifact_production_eligibility_false")
    return sorted(set(reasons))


def _resolve_context(
    artifact: dict[str, Any], *, category: str, input_metadata: dict[str, Any],
    protocol: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    confirmed_format = input_metadata.get("confirmed_format")
    duration = input_metadata.get("duration_seconds")
    age_context = input_metadata.get("reference_age_context")
    reasons = []
    if confirmed_format not in SUPPORTED_FORMATS:
        reasons.append("confirmed_format_required")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration <= 0:
        reasons.append("duration_required")
    valid_ages = {
        str(cell.get("cell", [None, None, None])[2])
        for cell in (artifact.get("benchmarks") or {}).get("cells", [])
        if len(cell.get("cell") or []) == 4
    }
    if age_context not in valid_ages:
        reasons.append("reference_age_context_required")
    if reasons:
        return None, sorted(set(reasons))

    candidates = [
        cell for cell in (artifact.get("benchmarks") or {}).get("cells", [])
        if list(cell.get("cell") or [])[:3] == [category, confirmed_format, age_context]
        and cell.get("status") == "supported"
    ]
    metric_order = list((protocol.get("cutoff_policy") or {}).get("supported_view_metric_versions") or [])
    by_metric = {str(cell["cell"][3]): cell for cell in candidates}
    selected = next((by_metric[metric] for metric in metric_order if metric in by_metric), None)
    if selected is None:
        return None, ["supported_benchmark_context_missing"]
    return {
        "accepted_category": category,
        "confirmed_format": confirmed_format,
        "confirmed_format_provenance": input_metadata.get("confirmed_format_provenance"),
        "duration_seconds": float(duration),
        "frozen_age_context": age_context,
        "reference_age_context_provenance": input_metadata.get("reference_age_context_provenance"),
        "view_metric_version": selected["cell"][3],
        "benchmark_sha256": selected.get("benchmark_sha256"),
        "benchmark_threshold_views": selected.get("threshold_views"),
        "selection_method": "protocol_metric_order_first_supported",
    }, []


def _training_support(
    artifact: dict[str, Any], model_input: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    support = artifact.get("training_support") or {}
    if support.get("version") != TRAINING_SUPPORT_VERSION:
        return {"status": "unsupported"}, ["training_support_artifact_missing"]
    signature = _topic_signature(model_input)
    match = next((
        item for item in support.get("signatures", [])
        if item.get("accepted_category") == model_input.get("accepted_category")
        and item.get("confirmed_format") == model_input.get("confirmed_format")
        and item.get("frozen_age_context") == model_input.get("frozen_age_context")
        and item.get("topic_signature") == signature
    ), None)
    if match is None:
        return {
            "status": "unsupported", "topic_signature": signature,
            "policy_version": support.get("version"),
        }, ["joint_feature_signature_not_seen_in_fit"]
    minimum_videos = int(support.get("minimum_signature_videos", 0))
    minimum_channels = int(support.get("minimum_signature_channels", 0))
    reasons = []
    if int(match.get("video_count", 0)) < minimum_videos:
        reasons.append("joint_feature_minimum_videos_not_met")
    if int(match.get("channel_count", 0)) < minimum_channels:
        reasons.append("joint_feature_minimum_channels_not_met")
    return {
        "status": "supported" if not reasons else "unsupported",
        "policy_version": support.get("version"),
        "source_partition": support.get("source_partition"),
        "topic_signature": signature,
        "video_count": int(match.get("video_count", 0)),
        "channel_count": int(match.get("channel_count", 0)),
        "minimum_video_count": minimum_videos,
        "minimum_channel_count": minimum_channels,
    }, reasons


def _predict(artifact: dict[str, Any], model_input: dict[str, Any]) -> float:
    selected = str(artifact.get("selected_model") or "metadata_topics_logistic_regression")
    candidate = (artifact.get("models") or {}).get(selected) or {}
    estimator = candidate.get("estimator")
    calibrator = candidate.get("calibrator")
    layout = candidate.get("layout")
    if estimator is None or calibrator is None or not isinstance(layout, dict):
        raise ValueError("Outcome estimator or calibrator missing")
    matrix = _matrix([{"model_input": model_input}], layout)
    raw = _positive_probability(estimator, matrix)
    calibrated = calibrator.predict(raw)
    value = float(calibrated[0])
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Outcome calibrated probability invalid")
    return value


def _model_fields(result: dict[str, Any], model: dict[str, Any], artifact: dict[str, Any]) -> None:
    result.update({
        "model_id": model["model_id"],
        "model_version": model["model_version"],
        "artifact_sha256": model["artifact_sha256"],
        "calibration_version": model["calibration_version"],
        "dataset_manifest_sha256": model["manifest_sha256"],
        "split_manifest_sha256": sha256_json(model.get("split_hashes") or {}),
        "reference_cutoff": artifact.get("observation_cutoff"),
        "fixture_only": model.get("source_kind") == "synthetic_fixture",
    })


def assess_outcome(
    db: Session,
    *,
    category: str,
    classification: dict[str, Any],
    evidence_context: dict[str, Any],
    input_metadata: dict[str, Any] | None,
    evidence_topic_ids: list[str] | None = None,
    evidence_pointers: list[dict[str, Any]] | None = None,
    allow_synthetic_fixture: bool = False,
) -> dict[str, Any]:
    """Assess one upload once.  Every failed gate returns a null probability."""
    started = time.monotonic()
    protocol = _load_json(PROTOCOL_PATH)
    transcript = str(evidence_context.get("raw_transcript") or "")
    transcript_sha = text_hash(transcript) if transcript else None
    result = _base_assessment(
        status="error", protocol=protocol, transcript_sha256=transcript_sha,
        evidence_topic_ids=evidence_topic_ids, evidence_pointers=evidence_pointers,
    )
    try:
        validation = validate_protocol(protocol)
        if not validation["valid"]:
            result.update(status="error", reason_codes=validation["errors"])
            return result

        classification_reasons = _classification_status(classification, category)
        if classification_reasons:
            result.update(status="classification_withheld", reason_codes=classification_reasons)
            return result

        if (evidence_context.get("availability") != "available"
                or evidence_context.get("scope") not in FULL_TRANSCRIPT_SCOPES
                or not transcript.strip()):
            result.update(
                status="unassessable_transcript",
                reason_codes=[str(evidence_context.get("reason") or "full_transcript_required")],
            )
            return result

        rights = data_use_gate(_load_json(DATA_USE_PATH), "serving")
        if not rights["allowed"]:
            result.update(status="data_use_unverified", reason_codes=rights["reason_codes"])
            return result

        model, model_reasons = _active_model_snapshot(db)
        if model is None:
            result.update(status="model_unavailable", reason_codes=model_reasons)
            return result
        if model["protocol_sha256"] != validation["protocol_sha256"]:
            result.update(status="model_unqualified", reason_codes=["active_model_protocol_mismatch"])
            return result
        preliminary = _qualification_reasons(
            model, None, allow_synthetic_fixture=allow_synthetic_fixture
        )
        if preliminary:
            result.update(status="model_unqualified", reason_codes=preliminary)
            result.update(model_id=model["model_id"], model_version=model["model_version"])
            return result

        artifact = _load_cached_artifact(model)
        _model_fields(result, model, artifact)
        qualification = _qualification_reasons(
            model, artifact, allow_synthetic_fixture=allow_synthetic_fixture
        )
        if qualification:
            result.update(status="model_unqualified", reason_codes=qualification)
            return result

        context, context_reasons = _resolve_context(
            artifact, category=category, input_metadata=input_metadata or {}, protocol=protocol
        )
        if context is None:
            result.update(status="unsupported_context", reason_codes=context_reasons)
            return result

        record = {
            "transcript": transcript,
            "transcript_sha256": transcript_sha,
            "transcript_scope": "full_video",
            "transcript_segments": evidence_context.get("segments") or [],
            "accepted_category": category,
            "confirmed_format": context["confirmed_format"],
            "duration_seconds": context["duration_seconds"],
            "frozen_age_context": context["frozen_age_context"],
        }
        feature = build_feature_record(record, protocol)
        if feature.get("status") != "usable":
            result.update(status="unassessable_transcript", reason_codes=feature.get("reason_codes") or [])
            return result
        if feature.get("feature_schema_sha256") != model["feature_schema_sha256"]:
            result.update(status="error", reason_codes=["inference_feature_schema_mismatch"])
            return result

        support, support_reasons = _training_support(artifact, feature["model_input"])
        benchmark = next((
            cell for cell in (artifact.get("benchmarks") or {}).get("cells", [])
            if cell.get("benchmark_sha256") == context["benchmark_sha256"]
        ), None)
        result["context"] = context
        result["evaluated_scope"] = {
            "category": category,
            "confirmed_format": context["confirmed_format"],
            "frozen_age_context": context["frozen_age_context"],
            "view_metric_version": context["view_metric_version"],
        }
        result["support_summary"] = {
            "benchmark": copy.deepcopy(benchmark),
            "joint_feature_support": support,
        }
        result["feature_snapshot"] = {
            "feature_schema_sha256": feature["feature_schema_sha256"],
            "feature_sha256": feature["feature_sha256"],
            "model_input": copy.deepcopy(feature["model_input"]),
        }
        if support_reasons:
            result.update(status="unsupported_context", reason_codes=support_reasons)
            return result

        timeout_ms = int((protocol.get("resources") or {}).get("inference_timeout_milliseconds", 1500))
        probability = _predict(artifact, feature["model_input"])
        if (time.monotonic() - started) * 1000 > timeout_ms:
            result.update(status="error", reason_codes=["inference_timeout"], probability=None)
            return result
        result.update(
            status="available", reason_codes=[], probability=round(probability, 8),
        )
        return result
    except Exception as exc:
        result.update(
            status="error", probability=None,
            reason_codes=[f"outcome_inference_error:{exc.__class__.__name__}"],
        )
        return result


def predict_frozen_model_input(
    db: Session,
    *,
    assessment: dict[str, Any],
    model_input: dict[str, Any],
    allow_synthetic_fixture: bool = False,
) -> dict[str, Any]:
    """Score a copied feature vector using the exact model pinned in a snapshot."""
    rights = data_use_gate(_load_json(DATA_USE_PATH), "serving")
    if not rights["allowed"]:
        return {"status": "data_use_unverified", "reason_codes": rights["reason_codes"],
                "probability": None, "support_summary": None}
    model_id = assessment.get("model_id")
    model = _model_snapshot_by_id(db, int(model_id)) if model_id is not None else None
    if model is None:
        return {"status": "model_unavailable", "reason_codes": ["pinned_model_missing"],
                "probability": None, "support_summary": None}
    pinned_fields = {
        "artifact_sha256": model.get("artifact_sha256"),
        "model_version": model.get("model_version"),
        "target_version": model.get("target_version"),
    }
    mismatches = [key for key, value in pinned_fields.items() if assessment.get(key) != value]
    frozen_feature_schema = (assessment.get("feature_snapshot") or {}).get("feature_schema_sha256")
    if frozen_feature_schema != model.get("feature_schema_sha256"):
        mismatches.append("feature_schema_sha256")
    if mismatches:
        return {"status": "error", "reason_codes": [f"pinned_{key}_mismatch" for key in mismatches],
                "probability": None, "support_summary": None}
    try:
        artifact = _load_cached_artifact(model)
    except Exception as exc:
        return {"status": "error", "reason_codes": [f"artifact_error:{exc.__class__.__name__}"],
                "probability": None, "support_summary": None}
    reasons = _qualification_reasons(model, artifact, allow_synthetic_fixture=allow_synthetic_fixture)
    if reasons:
        return {"status": "model_unqualified", "reason_codes": reasons,
                "probability": None, "support_summary": None}
    support, support_reasons = _training_support(artifact, model_input)
    if support_reasons:
        return {"status": "unsupported_context", "reason_codes": support_reasons,
                "probability": None, "support_summary": support}
    try:
        probability = _predict(artifact, model_input)
    except Exception as exc:
        return {"status": "error", "reason_codes": [f"prediction_error:{exc.__class__.__name__}"],
                "probability": None, "support_summary": support}
    return {"status": "available", "reason_codes": [],
            "probability": round(probability, 8), "support_summary": support}


def assessment_fingerprint(assessment: dict[str, Any]) -> str:
    return fingerprint(assessment)
