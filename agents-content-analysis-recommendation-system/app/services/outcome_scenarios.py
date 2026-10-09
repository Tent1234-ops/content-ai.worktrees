"""Guarded hypothetical topic scenarios for saved Outcome assessments."""
from __future__ import annotations

import copy
import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.database.models import AnalysisResult, UserContent
from app.services.outcome_inference import (
    SCENARIO_SCHEMA_VERSION,
    assessment_fingerprint,
    predict_frozen_model_input,
)
from app.services.recommendation_evidence import text_hash


def _json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _empty(
    status: str, reason_codes: list[str], *, analysis_id: int,
    selected_topic_ids: list[str], assessment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    assessment = assessment or {}
    return {
        "schema_version": SCENARIO_SCHEMA_VERSION,
        "status": status,
        "reason_codes": sorted(set(reason_codes)),
        "hypothetical": True,
        "unit": "percentage_points",
        "analysis_id": analysis_id,
        "input_transcript_sha256": assessment.get("input_transcript_sha256"),
        "selected_topic_ids": selected_topic_ids,
        "context": copy.deepcopy(assessment.get("context")),
        "model_id": assessment.get("model_id"),
        "model_version": assessment.get("model_version"),
        "artifact_sha256": assessment.get("artifact_sha256"),
        "probability_before": None,
        "probability_after": None,
        "delta_percentage_points": None,
        "limitation": "เป็นการจำลองค่าประเมินของโมเดล ไม่ใช่ผลเพิ่มยอดวิวหรือหลักฐานเชิงเหตุและผล",
    }


def simulate_outcome_scenario(
    db: Session,
    *,
    user_id: int,
    content_id: int,
    analysis_id: int,
    assessment_digest: str,
    selected_topic_ids: list[str],
    allow_synthetic_fixture: bool = False,
) -> dict[str, Any]:
    selected = [str(item) for item in selected_topic_ids]
    if len(selected) != len(set(selected)):
        raise HTTPException(422, "selected_topic_ids must be unique")
    content = db.query(UserContent).filter_by(content_id=content_id, user_id=user_id).first()
    if content is None:
        raise HTTPException(404, "Content not found")
    analysis = db.query(AnalysisResult).filter_by(
        result_id=analysis_id, content_id=content_id
    ).first()
    if analysis is None:
        raise HTTPException(404, "Analysis not found")
    summary = _json(analysis.summary)
    recommendation = summary.get("recommendation") or {}
    assessment = summary.get("outcome_assessment")
    if not isinstance(assessment, dict):
        assessment = recommendation.get("outcome_assessment")
    if not isinstance(assessment, dict):
        return _empty(
            "legacy_not_assessed", ["saved_before_outcome_assessment_v1"],
            analysis_id=analysis_id, selected_topic_ids=selected,
        )
    if assessment_fingerprint(assessment) != assessment_digest:
        raise HTTPException(409, "Outcome assessment changed; reload the saved result")

    action_topics = {
        str(item.get("topic_id")): item
        for item in ((recommendation.get("evidence_bundle") or {}).get("action_topics") or [])
        if isinstance(item, dict) and item.get("topic_id")
    }
    comparisons = {
        str(item.get("evidence_topic_id")): item
        for item in (((recommendation.get("evidence_bundle") or {})
                      .get("topic_comparisons") or {}).get("items") or [])
        if isinstance(item, dict) and item.get("evidence_topic_id")
    }
    allowed = set(assessment.get("evidence_topic_ids") or [])
    for topic_id in selected:
        topic = action_topics.get(topic_id)
        if topic_id not in allowed or topic is None:
            raise HTTPException(422, f"Topic {topic_id} is not allowed by this assessment")
        if (topic.get("user") or {}).get("status") != "not_detected":
            raise HTTPException(422, f"Topic {topic_id} is already detected or unassessable")
        views = ((comparisons.get(topic_id) or {}).get("metrics") or {}).get("views") or {}
        if views.get("status") != "comparison_supported":
            return _empty(
                "insufficient_data", [f"paired_evidence_not_supported:{topic_id}"],
                analysis_id=analysis_id, selected_topic_ids=selected, assessment=assessment,
            )

    if assessment.get("status") != "available":
        return _empty(
            str(assessment.get("status") or "model_unavailable"),
            list(assessment.get("reason_codes") or ["saved_assessment_not_available"]),
            analysis_id=analysis_id, selected_topic_ids=selected, assessment=assessment,
        )
    frozen_feature = assessment.get("feature_snapshot") or {}
    before_input = frozen_feature.get("model_input")
    if not isinstance(before_input, dict):
        return _empty(
            "error", ["saved_feature_snapshot_missing"], analysis_id=analysis_id,
            selected_topic_ids=selected, assessment=assessment,
        )
    current_transcript = str(content.raw_transcript or content.transcript or "")
    if text_hash(current_transcript) != assessment.get("input_transcript_sha256"):
        return _empty(
            "error", ["saved_input_transcript_hash_mismatch"], analysis_id=analysis_id,
            selected_topic_ids=selected, assessment=assessment,
        )

    after_input = copy.deepcopy(before_input)
    topic_features = after_input.get("canonical_topic_presence")
    if not isinstance(topic_features, dict):
        return _empty(
            "error", ["saved_topic_features_missing"], analysis_id=analysis_id,
            selected_topic_ids=selected, assessment=assessment,
        )
    canonical_topics = []
    for topic_id in selected:
        canonical = str(action_topics[topic_id].get("canonical_topic") or "")
        if canonical not in topic_features:
            return _empty(
                "unsupported_context", [f"topic_not_in_feature_schema:{topic_id}"],
                analysis_id=analysis_id, selected_topic_ids=selected, assessment=assessment,
            )
        topic_features[canonical] = True
        canonical_topics.append(canonical)

    before = predict_frozen_model_input(
        db, assessment=assessment, model_input=before_input,
        allow_synthetic_fixture=allow_synthetic_fixture,
    )
    if before["status"] != "available":
        return _empty(
            before["status"], before["reason_codes"], analysis_id=analysis_id,
            selected_topic_ids=selected, assessment=assessment,
        )
    after = predict_frozen_model_input(
        db, assessment=assessment, model_input=after_input,
        allow_synthetic_fixture=allow_synthetic_fixture,
    )
    if after["status"] != "available":
        result = _empty(
            after["status"], after["reason_codes"], analysis_id=analysis_id,
            selected_topic_ids=selected, assessment=assessment,
        )
        result["joint_feature_support"] = after.get("support_summary")
        return result
    before_probability = float(before["probability"])
    if abs(before_probability - float(assessment["probability"])) > 1e-7:
        return _empty(
            "error", ["saved_probability_reproduction_mismatch"], analysis_id=analysis_id,
            selected_topic_ids=selected, assessment=assessment,
        )
    after_probability = float(after["probability"])
    return {
        **_empty("available", [], analysis_id=analysis_id,
                 selected_topic_ids=selected, assessment=assessment),
        "canonical_topics": canonical_topics,
        "probability_before": before_probability,
        "probability_after": after_probability,
        "delta_percentage_points": round((after_probability - before_probability) * 100, 6),
        "joint_feature_support": after.get("support_summary"),
        "input_mutated": False,
    }
