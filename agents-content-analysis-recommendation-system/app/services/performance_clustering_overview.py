"""Automatic, per-topic clustering overview using existing saved reference evidence.

Never combines different format/age/metric cells and never predicts user views.
"""
from __future__ import annotations

from datetime import datetime
from fastapi import HTTPException

from app.core.datetime_utils import utc_isoformat
from app.services.contents import get_user_content_detail
from app.services.dataset_eligibility import reference_transcript_rows
from app.services.performance_clustering import performance_for_content
from app.services.performance_clustering_topics import saved_topic_cohort


SCHEMA_VERSION = "performance-clustering-overview-v1"
LIMITATION = (
    "ผลเป็นความคล้ายของ Transcript กับกลุ่มคลิปอ้างอิง ไม่ใช่การทำนายยอดวิว "
    "และแต่ละหัวข้อ/รูปแบบ/ช่วงอายุเป็นชุดเปรียบเทียบแยกกัน "
    "ระบบวิเคราะห์เฉพาะหัวข้อที่บันทึกหลักฐานเปรียบเทียบไว้แล้ว"
)


def performance_overview_for_content(db, *, user_id: int, content_id: int,
                                     now: datetime | None = None) -> dict:
    now = now or datetime.utcnow()
    content = get_user_content_detail(db, user_id=user_id, content_id=content_id)
    if content is None:
        raise HTTPException(status_code=404, detail="Content not found")
    recommendation = content.get("recommendation") or {}
    classification = recommendation.get("classification") or {}
    category = classification.get("taxonomy_leaf_key") or classification.get("domain") or "unknown"
    bundle = recommendation.get("evidence_bundle") or {}
    result = {
        "schema_version": SCHEMA_VERSION, "content_id": content_id,
        "analysis_id": content.get("analysis_id"), "category": category,
        "as_of": utc_isoformat(now), "status": "no_saved_topic_groups",
        "topic_count": 0, "group_count": 0, "ready_count": 0,
        "high_count": 0, "low_count": 0, "inconclusive_count": 0,
        "groups": [], "limitation": LIMITATION,
    }
    accepted = (classification.get("acceptance") or {}).get("accepted")
    if (category not in {"phone", "camera", "laptop"} or
            classification.get("is_unknown") is not False or accepted is not True):
        result["status"] = "classification_not_accepted"
        return result
    if (bundle.get("input") or {}).get("availability") != "available":
        result["status"] = "user_transcript_unavailable"
        return result

    comparisons = (bundle.get("topic_comparisons") or {}).get("items") or []
    available = {topic.get("topic_id") for topic in bundle.get("action_topics", [])
                 if isinstance(topic, dict) and isinstance(topic.get("topic_id"), str)}
    # Validate the saved cohort before querying current reference transcripts.
    choices = []
    seen = set()
    for item in comparisons:
        if not isinstance(item, dict):
            continue
        topic_id = item.get("evidence_topic_id")
        if not isinstance(topic_id, str) or topic_id not in available:
            continue
        summary = item.get("group_response_summary") or {}
        for index, group in enumerate(summary.get("groups") or []):
            key = (topic_id, index)
            if key in seen or not isinstance(group, dict):
                continue
            seen.add(key)
            cohort = saved_topic_cohort(bundle, category, topic_id, index)
            if cohort is not None:
                choices.append(cohort)
    if not choices:
        return result

    # One reference read across all saved topics; K-Means is still fitted
    # independently per topic and comparable historical context cell.
    rows = reference_transcript_rows(db, domain=category, now=now)
    for cohort in choices:
        calculated = performance_for_content(
            db, user_id=user_id, content_id=content_id,
            minimum_views=cohort["threshold_views"],
            topic_id=cohort["topic_id"], group_index=cohort["group_index"],
            now=now, _content=content, _reference_rows=rows,
        )
        clustering = calculated["clustering"]
        similarity = calculated["content_similarity"]
        ready = (clustering.get("status") == "ready" and
                 similarity.get("status") == "ready" and
                 similarity.get("closest_group") in {"low", "high"})
        closest = similarity["closest_group"] if ready else None
        reason = None if ready else (similarity.get("reason")
                  if clustering.get("status") == "ready" else clustering.get("reason"))
        result["groups"].append({
            "topic_id": cohort["topic_id"], "topic_title": cohort["topic_title"],
            "group_index": cohort["group_index"], "format": cohort["format"],
            "age_group": cohort["age_group"], "as_of": cohort["as_of"],
            "threshold_views": cohort["threshold_views"],
            "topic_sample_size": cohort["sample_size"],
            "passing_count": cohort["passing_count"],
            "eligible_count": calculated["eligible_count"],
            "clustering_status": clustering.get("status"),
            "similarity_status": similarity.get("status"),
            "low_score": similarity.get("low_score"),
            "high_score": similarity.get("high_score"),
            "closest_group": closest, "reason": reason,
            "k_used": similarity.get("k_used", 0),
        })
        if ready:
            result["ready_count"] += 1
            result[f"{closest}_count"] += 1
        else:
            result["inconclusive_count"] += 1
    result["topic_count"] = len({group["topic_id"] for group in result["groups"]})
    result["group_count"] = len(result["groups"])
    result["status"] = "ready"
    return result
