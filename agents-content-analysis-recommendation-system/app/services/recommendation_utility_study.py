"""Pure helpers for the blinded Phase 7 recommendation utility study."""
from __future__ import annotations

import json
from pathlib import Path

from app.services.analysis_evaluation import (
    CRITICAL_FLAGS,
    EVIDENCE_SCORE_FIELD,
    REVIEW_SCHEMA_VERSION,
    UTILITY_SCORE_FIELDS,
    allocation_balance,
    digest,
)


def stable_context_lock(context: dict) -> dict:
    """Remove observation time while retaining every input that can change an output."""
    keys = (
        "settings", "artifact_path", "artifact_sha256", "dataset_manifest_sha256",
        "reference_sha256", "reference_count", "statistics_cutoff", "statistics_sha256",
        "method_versions", "packages", "python_version", "asr_language", "code_sha256",
        "recommendation_parameters",
    )
    result = {key: context.get(key) for key in keys}
    result["settings"] = {key: value for key, value in (context.get("settings") or {}).items()
                          if key != "captured_at"}
    # JSON round trips turn tuple-valued policies into lists.
    return json.loads(json.dumps(result, default=str))


def study_readiness(*, manifest_audit: dict, reviewer_ids: list[str]) -> dict:
    missing = []
    for label, count in manifest_audit.get("eligible_counts", {}).items():
        if count < 3:
            missing.append({"requirement": f"fresh_{label}_clips", "required": 3, "available": count})
    if not manifest_audit.get("diversity_complete"):
        missing.append({"requirement": "pilot_scenario_and_self_recorded_coverage",
                        "required": 1, "available": 0})
    if len(set(reviewer_ids)) < 3:
        missing.append({"requirement": "real_reviewers", "required": 3,
                        "available": len(set(reviewer_ids))})
    return {
        "state": "ready_for_prediction" if not missing else "awaiting_fresh_clips_or_reviewers",
        "manifest_complete": bool(manifest_audit.get("pilot_manifest_complete")),
        "reviewer_plan_complete": len(set(reviewer_ids)) >= 3,
        "missing": missing,
    }


def build_blind_packets(*, protocol: dict, allocations: list[dict], case_outputs: dict) -> tuple[dict, dict]:
    """Return public packets and a private key; packets never reveal A/B/C."""
    packets: dict[str, dict] = {}
    private_rows = []
    for row in allocations:
        case_id = row["case_id"]
        reviewer_id = row["reviewer_id"]
        variant_id = row["variant_id"]
        case = case_outputs[case_id]
        if case.get("analysis_status") not in {None, "completed"} or case.get("exclusions"):
            continue
        variant = case["variants"][variant_id]
        packet = packets.setdefault(reviewer_id, {
            "schema_version": REVIEW_SCHEMA_VERSION,
            "study_id": protocol["study_id"],
            "protocol_sha256": protocol["protocol_sha256"],
            "reviewer_id": reviewer_id,
            "instructions": {
                "blind": "รหัสชุดนำเสนอไม่บอกว่าเป็น A, B หรือ C",
                "sequence": "ดูคลิปและตอบคำถามก่อน จากนั้นประเมินคำแนะนำทีละชุดตามลำดับ",
                "scale": "1=ต่ำมาก, 5=สูงมาก; คะแนนหลักฐานใช้เฉพาะชุดที่มีหลักฐาน",
                "claims": "ประเมินประโยชน์ของคำแนะนำ ไม่ใช่ทำนายยอด Engagement",
            },
            "cases": {},
        })
        public_case = packet["cases"].setdefault(case_id, {
            "case_id": case_id,
            "video_uri": case.get("video_uri"),
            "gold_label_hidden": True,
            "analysis_status": case.get("analysis_status"),
            "presentations": [],
        })
        unit_id = digest([protocol["study_id"], case_id, reviewer_id,
                          row["presentation_id"], "rating-unit"])[:24]
        presentation = {
            "presentation_id": row["presentation_id"],
            "position": row["position"],
            "unit_id": unit_id,
            "output_sha256": variant["output_sha256"],
            "item_count": variant["item_count"],
            "recommendation_status": variant.get("recommendation_status"),
            "items": variant["items"],
            "evidence_score_applicable": variant_id == "C" and variant["item_count"] > 0,
        }
        public_case["presentations"].append(presentation)
        private_rows.append({**row, "output_sha256": variant["output_sha256"],
                             "unit_id": unit_id})
    for packet in packets.values():
        packet["cases"] = [packet["cases"][key] for key in sorted(packet["cases"])]
        for case in packet["cases"]:
            case["presentations"].sort(key=lambda item: item["position"])
        packet["packet_sha256"] = digest(packet)
    private = {
        "study_id": protocol["study_id"],
        "protocol_sha256": protocol["protocol_sha256"],
        "allocation_balance": allocation_balance(allocations),
        "allocations": private_rows,
        "private_mapping_sha256": digest(private_rows),
    }
    return packets, private


def _json_for_script(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def render_review_html(packet: dict) -> str:
    """Render the versioned standalone form without exposing private variant IDs."""
    from app.services.analysis_evaluation import RUBRIC_ANCHORS
    template = Path(__file__).with_name("utility_review.html").read_text(encoding="utf-8")
    config = {"packet": packet, "review_schema": REVIEW_SCHEMA_VERSION,
              "utility_fields": list(UTILITY_SCORE_FIELDS), "critical_flags": list(CRITICAL_FLAGS),
              "rubric": RUBRIC_ANCHORS}
    return template.replace("__REVIEW_CONFIG__", _json_for_script(config))


def audit_actionable_evidence(result: dict) -> list[dict]:
    """Check frozen actionable evidence without claiming semantic usefulness."""
    recommendation = result.get("recommendation") or result
    actionable = recommendation.get("actionable_recommendations") or {}
    bundle = recommendation.get("evidence_bundle") or {}
    topics = {str(row.get("topic_id")): row for row in bundle.get("action_topics", [])
              if isinstance(row, dict)}
    documents = {row.get("dataset_id"): row for row in bundle.get("reference_documents", [])
                 if isinstance(row, dict)}
    comparisons = {str(row.get("evidence_topic_id")): row
                   for row in (bundle.get("topic_comparisons") or {}).get("items", [])
                   if isinstance(row, dict)}
    checks = []
    for item in actionable.get("items", []):
        issues = []
        topic_id = str(item.get("evidence_topic_id") or "")
        topic = topics.get(topic_id)
        if not topic:
            issues.append("missing_action_topic")
            topic = {}
        item_ids = list(item.get("supporting_dataset_row_ids") or [])
        references = list(topic.get("references") or [])
        reference_ids = [row.get("dataset_id") for row in references]
        if len(item_ids) != len(set(item_ids)) or set(item_ids) != set(reference_ids):
            issues.append("supporting_rows_do_not_match_topic")
        if item.get("support_count") != len(set(reference_ids)):
            issues.append("invalid_action_support_count")
        channels = set()
        for reference in references:
            dataset_id = reference.get("dataset_id")
            document = documents.get(dataset_id)
            if not document or document.get("data_split") != "train":
                issues.append("invalid_action_reference_row")
                continue
            if document.get("channel_id"):
                channels.add(document["channel_id"])
            transcript = str(document.get("transcript") or "")
            for occurrence in reference.get("occurrences") or []:
                quote = str(occurrence.get("quote") or "")
                start, end = occurrence.get("quote_start_char"), occurrence.get("quote_end_char")
                if (type(start) is not int or type(end) is not int or not quote or
                        not 0 <= start < end <= len(transcript) or transcript[start:end] != quote):
                    issues.append("fabricated_or_misaligned_quote")
                timestamp = occurrence.get("timestamp")
                if timestamp is not None:
                    from app.services.recommendation_evidence import locate_terms
                    actual = locate_terms(transcript, [str(occurrence.get("matched_text") or "")],
                                          segments=document.get("segments"))
                    if not any(hit.get("start_char") == occurrence.get("start_char") and
                               hit.get("end_char") == occurrence.get("end_char") and
                               hit.get("timestamp") == timestamp and hit.get("timestamp") is not None
                               for hit in actual):
                        issues.append("invalid_timestamp")
            for field in ("published_at", "statistics_captured_at", "video_id", "channel_id"):
                if not document.get(field):
                    issues.append(f"missing_reference_{field}")
        if item.get("channel_count") != len(channels):
            issues.append("invalid_action_channel_count")
        if item.get("causal_engagement_claim") is not False:
            issues.append("causal_engagement_claim")
        if topic_id and topic_id not in comparisons:
            issues.append("missing_topic_comparison_snapshot")
        checks.append({"advice_id": item.get("id"), "evidence_topic_id": topic_id,
                       "structural_issues": sorted(set(issues)),
                       "human_review": "pending"})
    return checks


def evidence_correctness_summary(case_outputs: dict) -> dict:
    primary_cases = [case for case in case_outputs.values()
                     if case.get("role") == "heldout" and case.get("manifest_eligible")]
    regression_cases = [case for case in case_outputs.values() if case.get("role") == "regression"]
    keyword_checks = [check for case in primary_cases
                      for check in case.get("recommendation_checks", [])]
    action_checks = [check for case in primary_cases
                     for check in case.get("actionable_evidence_checks", [])]
    regression_checks = [check for case in regression_cases
                         for lane in ("recommendation_checks", "actionable_evidence_checks")
                         for check in case.get(lane, [])]
    checks = keyword_checks + action_checks
    issues = {}
    for check in checks:
        for issue in check.get("structural_issues", []):
            issues[issue] = issues.get(issue, 0) + 1
    return {
        "scope": "automated traceability and arithmetic checks; not human utility",
        "case_count": len(case_outputs),
        "primary_case_count": len(primary_cases),
        "regression_case_count": len(regression_cases),
        "recommendation_unit_count": len(checks),
        "keyword_unit_count": len(keyword_checks),
        "actionable_unit_count": len(action_checks),
        "units_with_automated_issues": sum(bool(row.get("structural_issues")) for row in checks),
        "issues": issues,
        "regression_unit_count": len(regression_checks),
        "regression_units_with_automated_issues": sum(
            bool(row.get("structural_issues")) for row in regression_checks),
        "human_evidence_correctness": "reported separately from reviewer ratings",
    }


def thai_report(*, status: str, classification: dict, evidence: dict, utility: dict,
                readiness: dict, validated: dict) -> str:
    missing = readiness.get("missing") or []
    lines = [
        "# รายงานประเมินประโยชน์คำแนะนำ Phase 7", "",
        "## สถานะ", "", f"`{status}`", "",
        "รายงานแยกความแม่นการจำแนกหมวด ความถูกต้องของหลักฐาน และประโยชน์ของคำแนะนำออกจากกัน",
        "ผลนี้ไม่ใช่หลักฐานว่าคำแนะนำทำให้ยอดวิว ไลก์ หรือความคิดเห็นเพิ่มขึ้น", "",
        "## ความพร้อมของ Pilot", "",
    ]
    if missing:
        lines.extend(f"- `{row['requirement']}`: มี {row['available']} / ต้องการ {row['required']}" for row in missing)
    else:
        lines.append("- Manifest และแผนผู้ประเมินครบตาม Pilot ที่ลงทะเบียน")
    lines.extend([
        "", "## 1. การจำแนกหมวด", "",
        f"- คลิปที่ลงทะเบียนและเข้าเกณฑ์: {classification.get('registered_eligible_count', 0)}",
        f"- วิเคราะห์สำเร็จ: {classification.get('successful_count', 0)}",
        f"- งานล้มเหลว: {classification.get('failure_count', 0)} (ไม่นับเป็นการปฏิเสธ Unknown)",
        f"- Accuracy แบบปลายทาง: {classification.get('end_to_end_accuracy')}",
        f"- Unknown false acceptance: {classification.get('unknown_false_acceptance')}",
        "", "## 2. ความถูกต้องของหลักฐาน", "",
        f"- หน่วยคำแนะนำที่ตรวจอัตโนมัติ: {evidence.get('recommendation_unit_count', 0)}",
        f"- หน่วยที่พบปัญหา: {evidence.get('units_with_automated_issues', 0)}",
        "- การตรวจอัตโนมัติยืนยันการย้อนแถวข้อมูลและสูตร ไม่ใช้แทนคะแนนความเป็นประโยชน์จากคน",
        "", "## 3. ประโยชน์ของคำแนะนำ", "",
        f"- สถานะ: `{utility.get('status')}`",
        f"- คะแนนที่รับได้: {validated.get('accepted_rating_count', 0)}",
        f"- ผู้ประเมินที่มีคะแนนรับได้: {validated.get('accepted_reviewer_count', 0)}",
        f"- แถวที่ปฏิเสธ: {len(validated.get('rejected', []))}",
        "- คะแนนที่ขาดไม่ถูกแทนด้วยศูนย์ และ A/B ไม่ถูกบังคับให้มีคะแนนหลักฐาน",
        "", "## ขอบเขตข้อสรุป", "",
        "- Classification confidence ไม่ใช่คะแนนคุณภาพคำแนะนำ",
        "- ความสัมพันธ์ใน Dataset ไม่ใช่เหตุและผล",
        "- ต้องมีคลิปใหม่และคะแนนผู้ประเมินจริงครบก่อนใช้คำว่า evaluation_complete",
    ])
    return "\n".join(lines) + "\n"

