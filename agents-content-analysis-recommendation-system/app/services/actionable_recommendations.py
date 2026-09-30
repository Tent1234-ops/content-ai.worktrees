"""Deterministic Thai editing advice derived only from frozen transcript evidence."""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

from app.services.nlp import COMPARABLE_SYNONYMS_BY_DOMAIN
from app.services.recommendation_evidence import _observation, fingerprint, locate_terms, text_hash

METHOD_VERSION = "thai-action-advice-v1"
DISPLAY_LIMIT = 3
MINIMUM_CLIPS = 2
MINIMUM_CHANNELS = 2
REVIEW_TERMS = ["รีวิว", "ลองใช้", "ใช้งานจริง", "ประสบการณ์ใช้งาน", "review", "hands on", "hands-on"]
LIMITATION = "หลักฐานนี้เป็นความสัมพันธ์ในคลิปอ้างอิง ไม่ยืนยันว่าเพิ่มหัวข้อนี้แล้วจะทำให้ยอดวิว ไลก์ หรือความคิดเห็นเพิ่มขึ้น"


@lru_cache(maxsize=1)
def template_catalog() -> dict:
    return json.loads(Path(__file__).with_name("recommendation_templates.json").read_text(encoding="utf-8"))


def _aliases(template: dict, domain: str) -> list[str]:
    existing = COMPARABLE_SYNONYMS_BY_DOMAIN.get("smartphone", {}) if domain == "phone" else {}
    return list(dict.fromkeys([template["key"], *template["aliases"], *existing.get(template["key"], ())]))


def _documents(result: dict) -> list[dict]:
    bundle = result["evidence_bundle"]
    # Duration-only samples are not members of the high-performing keyword cohort.
    allowed_ids = set(result["dataset_profile"].get("dataset_row_ids", []))
    documents = {}
    for doc in bundle.get("reference_documents", []):
        if (doc.get("dataset_id") not in allowed_ids or
                doc.get("taxonomy_leaf_key") != result["domain"] or
                doc.get("data_split") != "train" or doc.get("source_type") != "dataset_transcript" or
                not doc.get("video_id") or not doc.get("channel_id") or not doc.get("url") or
                not doc.get("published_at") or not doc.get("statistics_captured_at") or
                not doc.get("transcript") or text_hash(doc["transcript"]) != doc.get("transcript_sha256")):
            continue
        documents.setdefault(doc["video_id"], doc)
    return list(documents.values())


def build_actionable_recommendations(result: dict) -> dict:
    """The display limit never truncates topic assessment or the transcript search."""
    bundle = result["evidence_bundle"]
    context = bundle["input"]
    domain = result["domain"]
    catalog = template_catalog()
    templates = catalog["categories"].get(domain, [])
    output = {
        "method_version": METHOD_VERSION, "template_version": catalog["version"],
        "catalog_sha256": fingerprint(catalog), "evidence_data_fingerprint": bundle["data_fingerprint"],
        "display_limit": DISPLAY_LIMIT, "minimum_support_count": MINIMUM_CLIPS,
        "minimum_channel_count": MINIMUM_CHANNELS, "items": [], "assessments": [],
        "eligible_count": 0, "assessed_topic_count": 0, "status": "no_supported_gap",
        "ranking_rule": "relevance_then_support_ratio_then_channels_then_mean_log_frequency",
        "limitation": LIMITATION,
    }
    bundle["action_topics"] = []
    classification = context.get("classification") or result.get("classification") or {}
    if (domain == "unknown" or result.get("status") == "withheld_unknown" or
            classification.get("is_unknown") or
            (classification.get("acceptance") or {}).get("accepted") is False):
        output["status"] = "withheld_unknown"
        return output
    if context.get("availability") != "available":
        output["status"] = "withheld_input_unassessable"
        return output
    if not templates:
        output["status"] = "unsupported_category"
        return output

    documents = _documents(result)
    observed = {t["key"]: _observation(context, _aliases(t, domain)) for t in templates}
    found = [t for t in templates if observed[t["key"]]["status"] == "detected"]
    broad_review = _observation(context, REVIEW_TERMS)
    candidates = []
    for template in templates:
        key, title = template["key"], template["title"]
        aliases = _aliases(template, domain)
        user = observed[key]
        relevance = _observation(context, template["context_terms"])
        # Context raises relevance; classification alone does not prove the video's focus.
        relevance_level = 2 if relevance["status"] == "detected" else 1 if found and broad_review["status"] == "detected" else 0
        supports = []
        for doc in documents:
            occurrences = locate_terms(doc["transcript"], aliases, segments=doc.get("segments"))
            if occurrences:
                supports.append({"dataset_id": doc["dataset_id"], "channel_id": doc["channel_id"],
                                 "frequency": len(occurrences), "occurrences": occurrences[:3]})
        channels = sorted({support["channel_id"] for support in supports})
        topic_id = fingerprint(["action", domain, key])[:24]
        topic = {
            "topic_id": topic_id, "canonical_topic": key, "title_th": title, "synonyms": aliases,
            "source_type": "transcript", "user": user, "user_hook": _observation(context, aliases, hook=True),
            "support_count": len(supports), "channel_count": len(channels), "channel_ids": channels,
            "sample_size": len(documents), "supporting_dataset_row_ids": [s["dataset_id"] for s in supports],
            "references": supports,
        }
        bundle["action_topics"].append(topic)
        ranking = {"relevance_level": relevance_level,
                   "support_ratio": len(supports) / len(documents) if documents else 0.0,
                   "channel_count": len(channels),
                   "mean_log_frequency": sum(math.log1p(s["frequency"]) for s in supports) / len(supports) if supports else 0.0}
        reason = ("already_detected" if user["status"] == "detected" else
                  "unassessable" if user["status"] != "not_detected" else
                  "insufficient_user_context" if not found or relevance_level == 0 else
                  "insufficient_reference_evidence" if len(supports) < MINIMUM_CLIPS or len(channels) < MINIMUM_CHANNELS else
                  "eligible")
        assessment = {"evidence_topic_id": topic_id, "template_key": key, "title": title,
                      "decision": reason, "ranking": ranking, "relevance_evidence": relevance,
                      "broad_review_evidence": broad_review if relevance_level == 1 else None}
        output["assessments"].append(assessment)
        if reason != "eligible":
            continue
        related = [t for t in found if any(hit["matched_text"].casefold() in {a.casefold() for a in _aliases(t, domain)}
                                         for hit in relevance.get("occurrences", []))]
        anchors = (related or found)[:2]
        found_topics = [{"title": t["title"], "canonical_topic": t["key"], "observation": observed[t["key"]]} for t in anchors]
        candidates.append({
            "id": fingerprint([domain, key, catalog["version"]])[:24], "evidence_topic_id": topic_id,
            "template_key": key, "title": title,
            "finding": f"ตรวจพบเรื่อง{' และ '.join(t['title'] for t in anchors)}ในข้อความของคุณ แต่ยังไม่ตรวจพบเรื่อง{title}ในข้อความที่วิเคราะห์",
            "found_topics": found_topics, "proposal": template["proposal"],
            "condition": template["condition"], "steps": template["steps"], "example": template["example"],
            "example_status": "suggested_script_not_observed_result",
            "reason": f"พบหัวข้อนี้ใน {len(supports)} จาก {len(documents)} คลิปอ้างอิงหมวดเดียวกัน จาก {len(channels)} ช่อง ซึ่งผ่านเกณฑ์คัดเลือกผลตอบรับของระบบ",
            "relevance_reason": "มีข้อความเกี่ยวกับการใช้งานที่เชื่อมกับหัวข้อนี้" if relevance_level == 2 else "เป็นประเด็นพื้นฐานของหมวดที่เชื่อมกับบริบทการรีวิวและสิ่งที่ตรวจพบ",
            "ranking": ranking, "support_count": len(supports), "channel_count": len(channels),
            "sample_size": len(documents), "supporting_dataset_row_ids": topic["supporting_dataset_row_ids"],
            "product_verification": "unverified_use_condition", "causal_engagement_claim": False,
        })
    candidates.sort(key=lambda item: (-item["ranking"]["relevance_level"], -item["ranking"]["support_ratio"],
        -item["ranking"]["channel_count"], -item["ranking"]["mean_log_frequency"], item["template_key"]))
    for index, item in enumerate(candidates, start=1):
        item["priority"] = index
    output["items"] = candidates[:DISPLAY_LIMIT]
    output["eligible_count"] = len(candidates)
    output["assessed_topic_count"] = len(templates)
    if output["items"]:
        output["status"] = "ready"
    elif not documents:
        output["status"] = "insufficient_reference_evidence"
    elif not found:
        output["status"] = "insufficient_user_context"
    elif all(o["status"] == "detected" for o in observed.values()):
        output["status"] = "all_topics_detected"
    return output
