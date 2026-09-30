"""Read historical output without consulting today's dataset or active model."""
import json


def json_object(value):
    try:
        result = json.loads(value or "{}")
        return result if isinstance(result, dict) else {}
    except (ValueError, TypeError):
        return {}


def stored_recommendation(content, analysis):
    summary = json_object(analysis.summary if analysis else None)
    saved = summary.get("recommendation")
    if isinstance(saved, dict) and saved:
        return saved
    rows = sorted(content.recommendations, key=lambda row: (row.created_at, row.rec_id), reverse=True)
    old = json_object(rows[0].recommended_keywords if rows else None)
    warning = "ผลเก่านี้ไม่มีหลักฐานและเวอร์ชันคำแนะนำบันทึกครบ แสดงเฉพาะข้อมูลเดิมโดยไม่คำนวณใหม่จาก Dataset ปัจจุบัน"
    domain = old.get("domain") or (analysis.taxonomy_leaf_key if analysis else None) or "unknown"
    duration = {"recommended_seconds": None, "recommended_range": "Insufficient evidence",
                "evidence_status": "insufficient_evidence", "sample_size": 0, "source": "historical_saved_output",
                "historical_seconds": rows[0].recommended_duration if rows else None}
    def keywords(key):
        return [dict(item, score=item.get("score", 0)) if isinstance(item, dict)
                else {"keyword": str(item), "score": 0} for item in (old.get(key) or [])]
    return {
        "domain": domain, "user_keywords": [], "missing_keywords": keywords("missing_keywords"),
        "hook_keywords": keywords("hook_keywords"), "missing_dimensions": [], "recommended_duration": duration,
        "dataset_profile": {"domain": domain, "sample_size": 0, "source": "historical_saved_output",
                            "top_keywords": [], "top_dimensions": [], "hook_keywords": [],
                            "recommended_duration": duration, "exemplar_titles": []},
        "evidence": {"warning": warning},
        "evidence_bundle": {"origin": "historical_legacy_no_snapshot", "topics": [], "reference_documents": []},
    }
