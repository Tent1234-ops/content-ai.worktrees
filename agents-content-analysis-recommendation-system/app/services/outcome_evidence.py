"""Deterministic Thai evidence copy for recommendation snapshots."""
from __future__ import annotations

import copy
from typing import Any


SCHEMA_VERSION = "recommendation-evidence-explanation-v1"


def _number(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "ไม่ทราบ"
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{float(value):,.2f}"


def _comparison_message(comparison: dict[str, Any] | None, item: dict[str, Any]) -> dict[str, Any]:
    if not comparison:
        clips = int(item.get("support_count") or 0)
        channels = int(item.get("channel_count") or 0)
        return {
            "level": "reference_examples",
            "message_th": f"พบประเด็นนี้ในคลิปอ้างอิง {clips} คลิป จาก {channels} ช่อง",
            "statistics": {"support_video_count": clips, "support_channel_count": channels},
            "causal_claim": False,
        }
    views = (comparison.get("metrics") or {}).get("views") or {}
    cohort = comparison.get("cohort") or {}
    status = str(views.get("status") or "not_comparable")
    detected = views.get("detected") or {}
    absent = views.get("not_detected") or {}
    statistics = {
        "metric": "views",
        "metric_unit": views.get("unit"),
        "comparison_status": status,
        "direction": views.get("direction"),
        "detected_video_count": detected.get("count", cohort.get("detected_count")),
        "not_detected_video_count": absent.get("count", cohort.get("not_detected_count")),
        "detected_median": detected.get("median"),
        "not_detected_median": absent.get("median"),
        "paired_channel_count": views.get("paired_channel_count"),
        "within_channel_median_difference": views.get("within_channel_median_difference"),
        "uncertainty": copy.deepcopy(views.get("uncertainty")),
        "as_of": comparison.get("as_of"),
    }
    if status in {"not_comparable", "reference_only"}:
        clips = int(cohort.get("detected_count") or item.get("support_count") or 0)
        channels = len({
            str(row.get("channel_id")) for row in comparison.get("records", [])
            if row.get("topic_status") == "detected" and row.get("channel_id")
        }) or int(item.get("channel_count") or 0)
        return {
            "level": "reference_examples",
            "message_th": f"พบประเด็นนี้ในคลิปอ้างอิง {clips} คลิป จาก {channels} ช่อง แต่ข้อมูลยังไม่พอเปรียบเทียบผลตอบรับ",
            "statistics": statistics,
            "causal_claim": False,
        }
    if status in {"comparison_descriptive", "comparison_uncertain"}:
        uncertainty = views.get("uncertainty") or {}
        interval = ""
        if uncertainty.get("low") is not None and uncertainty.get("high") is not None:
            interval = f" ช่วงความไม่แน่นอน {_number(uncertainty['low'])} ถึง {_number(uncertainty['high'])}"
        return {
            "level": "comparison_uncertain",
            "message_th": (
                f"ในตัวอย่างที่เทียบกันได้ ค่ากลางยอดวิวของกลุ่มที่พบหัวข้อนี้คือ {_number(detected.get('median'))} "
                f"และกลุ่มที่ไม่พบคือ {_number(absent.get('median'))}.{interval} ยังสรุปความต่างไม่ได้"
            ),
            "statistics": statistics,
            "causal_claim": False,
        }
    direction = {
        "higher": "สูงกว่า", "lower": "ต่ำกว่า", "equal": "เท่ากัน",
    }.get(str(views.get("direction")), "แตกต่างกัน")
    return {
        "level": "comparison_supported",
        "message_th": (
            f"ในคลิปอ้างอิงหมวดและบริบทที่เทียบกันได้ ณ {comparison.get('as_of') or 'เวลาที่บันทึกหลักฐาน'} "
            f"กลุ่มที่พบหัวข้อนี้มีค่ากลางยอดวิว {_number(detected.get('median'))} ซึ่ง{direction}กลุ่มที่ไม่พบ "
            f"({_number(absent.get('median'))}) นี่เป็นความสัมพันธ์ในตัวอย่าง ไม่ใช่เหตุยืนยันว่ายอดวิวจะเพิ่ม"
        ),
        "statistics": statistics,
        "causal_claim": False,
    }


def attach_outcome_evidence_explanations(
    recommendation: dict[str, Any], assessment: dict[str, Any],
) -> dict[str, Any]:
    """Attach copy without changing item selection or ranking."""
    comparison_bundle = ((recommendation.get("evidence_bundle") or {})
                         .get("topic_comparisons") or {})
    comparisons = {
        str(row.get("evidence_topic_id")): {
            **row, "as_of": row.get("as_of") or comparison_bundle.get("as_of")
        }
        for row in comparison_bundle.get("items", [])
        if isinstance(row, dict) and row.get("evidence_topic_id")
    }
    actions = (recommendation.get("actionable_recommendations") or {}).get("items", [])
    for item in actions:
        topic_id = str(item.get("evidence_topic_id") or "")
        evidence = _comparison_message(comparisons.get(topic_id), item)
        if assessment.get("status") == "available":
            probability = float(assessment["probability"]) * 100
            evidence["outcome"] = {
                "status": "available",
                "message_th": (
                    f"ภายใต้บริบทอ้างอิงที่ระบุ โมเดลประเมินโอกาสอยู่ในกลุ่มยอดวิวเหนือค่ากลางที่ {probability:.1f}% "
                    "ค่านี้ไม่ใช่โอกาสที่การทำตามคำแนะนำจะทำให้ยอดวิวเพิ่ม"
                ),
                "probability": assessment["probability"],
                "context": copy.deepcopy(assessment.get("context")),
            }
        else:
            evidence["outcome"] = {
                "status": assessment.get("status"),
                "message_th": "ยังไม่มีค่าประเมิน Outcome ที่ผ่านเกณฑ์ แต่คำแนะนำและหลักฐานอ้างอิงด้านบนยังตรวจสอบได้",
                "probability": None,
                "reason_codes": list(assessment.get("reason_codes") or []),
            }
        evidence.update(schema_version=SCHEMA_VERSION, evidence_topic_id=topic_id)
        item["evidence_explanation"] = evidence
    recommendation["outcome_assessment"] = assessment
    return recommendation
