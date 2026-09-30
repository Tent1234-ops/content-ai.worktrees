"""Persistent revision jobs and transcript-only before/after comparisons."""
from __future__ import annotations

import json
import os
import re
import socket
import uuid
from datetime import datetime, timezone

import psutil
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.core.datetime_utils import utc_isoformat
from app.database.models import (
    AnalysisResult,
    ClipRevisionComparison,
    ClipRevisionPlan,
    User,
    UserContent,
)
from app.runtime import get as runtime_get
from app.services.actionable_recommendations import template_catalog
from app.services.contents import _latest_analysis, get_user_content_detail
from app.services.recommendation_evidence import (
    METHOD_VERSION as TOPIC_MATCHER_VERSION,
    _observation,
    fingerprint,
    locate_terms,
    text_hash,
)
from app.services.saved_recommendations import stored_recommendation


SCHEMA_VERSION = "clip-revision-comparison-v1"
METHOD_VERSION = "same-topic-derived-comparison-v2"
TERMINAL_STATUSES = {"completed", "failed", "interrupted", "cancelled"}


def _process_owner() -> dict:
    return {"host": socket.gethostname(), "pid": os.getpid(),
            "started_at": psutil.Process().create_time()}


def _owner_is_alive(owner: dict) -> bool:
    if owner.get("host") != socket.gethostname():
        return True  # Another machine's work cannot be declared interrupted here.
    try:
        return psutil.Process(int(owner["pid"])).create_time() == owner["started_at"]
    except psutil.AccessDenied:
        return True
    except (psutil.NoSuchProcess, KeyError, TypeError, ValueError):
        return False


def claim_revision_job(db, comparison_id: int, *, expected_job_id: str | None):
    row = db.get(ClipRevisionComparison, comparison_id)
    if row is None or (expected_job_id and row.job_id != expected_job_id):
        raise RuntimeError("Revision attempt is no longer available")
    if row.status == "completed":
        return row
    changed = db.query(ClipRevisionComparison).filter_by(
        comparison_id=comparison_id, job_id=row.job_id, status="queued",
    ).update({"status": "running", "stage": "extracting_audio", "progress": 12,
              "started_at": datetime.utcnow(), "updated_at": datetime.utcnow()},
             synchronize_session=False)
    db.commit()
    if changed != 1:
        raise RuntimeError("Revision attempt is already running or no longer queued")
    db.refresh(row)
    return row


def _json(value, default=None):
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return {} if default is None else default


def _accepted_classification(recommendation: dict) -> tuple[bool, str]:
    classification = recommendation.get("classification") or {}
    acceptance = classification.get("acceptance") or {}
    accepted = bool(classification) and classification.get("is_unknown") is False
    if "accepted" in acceptance:
        accepted = acceptance["accepted"] is True and classification.get("is_unknown") is not True
    domain = str(
        classification.get("taxonomy_leaf_key")
        or recommendation.get("domain")
        or "unknown"
    )
    return accepted and domain in {"phone", "camera", "laptop"}, domain


def _topic_snapshot(recommendation: dict, selected_ids: list[str]) -> list[dict]:
    actions = recommendation.get("actionable_recommendations") or {}
    action_rows = {
        str(row.get("id")): row
        for row in actions.get("items", [])
        if isinstance(row, dict) and row.get("id")
    }
    topics = {
        str(row.get("topic_id")): row
        for row in (recommendation.get("evidence_bundle") or {}).get("action_topics", [])
        if isinstance(row, dict) and row.get("topic_id")
    }
    domain = str(recommendation.get("domain") or "unknown")
    templates = {
        str(row.get("key")): row
        for row in template_catalog().get("categories", {}).get(domain, [])
    }
    result = []
    for advice_id in selected_ids:
        advice = action_rows.get(str(advice_id))
        if advice is None:
            raise HTTPException(409, "หัวข้อในแผนไม่ตรงกับผลที่บันทึก กรุณาโหลดแผนใหม่")
        evidence_topic_id = str(advice.get("evidence_topic_id") or "")
        topic = topics.get(evidence_topic_id)
        if topic is None:
            raise HTTPException(409, "ผลเก่านี้ไม่มีนิยามหัวข้อเพียงพอสำหรับการเทียบอัตโนมัติ")
        key = str(advice.get("template_key") or topic.get("canonical_topic") or "")
        template = templates.get(key, {})
        aliases = [str(item) for item in topic.get("synonyms", []) if str(item).strip()]
        if key and key not in aliases:
            aliases.insert(0, key)
        result.append(
            {
                "advice_id": str(advice_id),
                "evidence_topic_id": evidence_topic_id,
                "canonical_topic": key,
                "title": str(advice.get("title") or topic.get("title_th") or key),
                "aliases": list(dict.fromkeys(aliases)),
                "context_terms": [
                    str(item)
                    for item in template.get("context_terms", [])
                    if str(item).strip()
                ],
                "advice_snapshot": {
                    field: advice.get(field)
                    for field in ("finding", "proposal", "condition", "steps", "example")
                },
            }
        )
    return result


def capture_plan_snapshot(
    db,
    *,
    user_id: int,
    parent_content_id: int,
    parent_analysis_id: int,
    parent_fingerprint: str,
    expected_plan_revision: int,
) -> dict:
    content = db.query(UserContent).filter_by(
        content_id=parent_content_id, user_id=user_id
    ).first()
    if content is None:
        raise HTTPException(404, "ไม่พบผลวิเคราะห์ต้นฉบับ")
    analysis = _latest_analysis(content)
    if analysis is None or analysis.result_id != parent_analysis_id:
        raise HTTPException(409, "ผลวิเคราะห์ต้นฉบับเปลี่ยนแล้ว กรุณาโหลดใหม่")
    recommendation = stored_recommendation(content, analysis)
    digest = fingerprint(recommendation)
    if digest != parent_fingerprint:
        raise HTTPException(409, "หลักฐานต้นฉบับเปลี่ยนแล้ว กรุณาโหลดผลใหม่")
    plan = db.get(ClipRevisionPlan, analysis.result_id)
    if plan is None or plan.revision <= 0:
        raise HTTPException(409, "กรุณาบันทึกแผนก่อนอัปโหลดฉบับแก้ไข")
    if plan.revision != expected_plan_revision:
        raise HTTPException(409, "แผนถูกแก้ไขแล้ว กรุณาโหลดแผนล่าสุดก่อนอัปโหลด")
    if plan.recommendation_fingerprint != digest:
        raise HTTPException(409, "แผนไม่ตรงกับหลักฐานต้นฉบับ กรุณาโหลดใหม่")
    selected = _json(plan.selected_advice_ids, [])
    if not isinstance(selected, list):
        raise HTTPException(409, "รูปแบบแผนที่บันทึกไว้ไม่ถูกต้อง")
    bundle = recommendation.get("evidence_bundle") or {}
    parent_context = bundle.get("input") or {}
    current_raw = str(content.raw_transcript or content.transcript or "")
    current_cleaned = str(content.cleaned_transcript or content.transcript or "")
    frozen_raw = str(parent_context.get("raw_transcript") or "")
    frozen_cleaned = str(parent_context.get("cleaned_transcript") or "")
    if frozen_raw and text_hash(current_raw) != text_hash(frozen_raw):
        raise HTTPException(409, "ข้อความต้นฉบับเปลี่ยนหลังบันทึกผล จึงยังเทียบไม่ได้")
    if frozen_cleaned and text_hash(current_cleaned) != text_hash(frozen_cleaned):
        raise HTTPException(409, "ข้อความหลังปรับศัพท์ของต้นฉบับเปลี่ยน จึงยังเทียบไม่ได้")
    accepted, domain = _accepted_classification(recommendation)
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "parent_content_id": parent_content_id,
        "parent_analysis_id": parent_analysis_id,
        "parent_title": content.title,
        "parent_created_at": utc_isoformat(content.created_at),
        "parent_recommendation_fingerprint": digest,
        "plan_revision": plan.revision,
        "plan_saved_at": utc_isoformat(plan.updated_at),
        "selected_advice_ids": [str(item) for item in selected],
        "notes": plan.notes,
        "topics": _topic_snapshot(recommendation, selected),
        "parent_context": parent_context,
        "parent_input_hashes": {
            "raw_transcript_sha256": text_hash(frozen_raw or current_raw),
            "cleaned_transcript_sha256": text_hash(frozen_cleaned or current_cleaned),
        },
        "parent_classification": recommendation.get("classification") or {},
        "parent_category_accepted": accepted,
        "parent_domain": domain,
        "parent_analysis_settings": parent_context.get("analysis_settings")
        or (_json(analysis.summary).get("ai_analysis") or {}).get("analysis_settings")
        or {},
        "versions": {
            "topic_matcher": TOPIC_MATCHER_VERSION,
            "context_template_version": template_catalog().get("version"),
            "context_template_sha256": fingerprint(template_catalog()),
            "action_method": (recommendation.get("actionable_recommendations") or {}).get("method_version"),
            "template_version": (recommendation.get("actionable_recommendations") or {}).get("template_version"),
            "alias_sha256": fingerprint(
                [row["aliases"] for row in _topic_snapshot(recommendation, selected)]
            ),
        },
    }
    return snapshot


def create_revision_job(
    db,
    *,
    user_id: int,
    parent_content_id: int,
    parent_analysis_id: int,
    parent_fingerprint: str,
    expected_plan_revision: int,
    client_request_id: str,
    file_sha256: str,
    file_path: str,
    filename: str,
    settings_snapshot: dict,
) -> tuple[ClipRevisionComparison, bool]:
    request_payload = {
        "parent_content_id": parent_content_id,
        "parent_analysis_id": parent_analysis_id,
        "parent_fingerprint": parent_fingerprint,
        "expected_plan_revision": expected_plan_revision,
        "client_request_id": client_request_id,
        "file_sha256": file_sha256,
    }
    request_digest = fingerprint(request_payload)
    existing = db.query(ClipRevisionComparison).filter_by(
        user_id=user_id, client_request_id=client_request_id
    ).first()
    if existing is not None:
        if existing.request_fingerprint != request_digest:
            raise HTTPException(409, "รหัสคำขอนี้ถูกใช้กับไฟล์หรือแผนอื่นแล้ว")
        return existing, False
    snapshot = capture_plan_snapshot(
        db,
        user_id=user_id,
        parent_content_id=parent_content_id,
        parent_analysis_id=parent_analysis_id,
        parent_fingerprint=parent_fingerprint,
        expected_plan_revision=expected_plan_revision,
    )
    captured_at = datetime.utcnow()
    row = ClipRevisionComparison(
        user_id=user_id,
        parent_content_id=parent_content_id,
        parent_analysis_id=parent_analysis_id,
        parent_recommendation_fingerprint=parent_fingerprint,
        plan_revision=expected_plan_revision,
        client_request_id=client_request_id,
        request_fingerprint=request_digest,
        file_sha256=file_sha256,
        file_path=file_path,
        original_filename=filename[:255],
        job_id=uuid.uuid4().hex,
        job_backend=str(runtime_get("job_backend") or "inprocess"),
        status="queued",
        stage="queued",
        progress=0,
        plan_snapshot_json=json.dumps(snapshot, ensure_ascii=False),
        settings_snapshot_json=json.dumps({**settings_snapshot, "revision_process_owner": _process_owner()}, ensure_ascii=False),
        snapshot_sha256=fingerprint(snapshot),
        captured_at=captured_at,
        created_at=captured_at,
        updated_at=captured_at,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        existing = db.query(ClipRevisionComparison).filter_by(
            user_id=user_id, client_request_id=client_request_id
        ).first()
        if existing is not None and existing.request_fingerprint == request_digest:
            return existing, False
        raise HTTPException(409, "คำขอนี้กำลังถูกรับจากอีกหน้าต่าง") from exc
    db.refresh(row)
    return row, True


def _same_context(topic_hits: list[dict], context_hits: list[dict], text: str) -> bool:
    for topic in topic_hits:
        for context in context_hits:
            topic_time = topic.get("timestamp") or {}
            context_time = context.get("timestamp") or {}
            if topic_time and context_time and topic_time.get("segment_index") == context_time.get("segment_index"):
                return True
            left = min(int(topic["start_char"]), int(context["start_char"]))
            right = max(int(topic["end_char"]), int(context["end_char"]))
            if right - left <= 180 and not re.search(r"[.!?\n]|[。！？]", text[left:right]):
                return True
    return False


def _context_status(context: dict, aliases: list[str], context_terms: list[str], observation: dict) -> dict:
    if observation.get("status") != "detected":
        return {"status": "unclear", "reason": "topic_not_assessable_or_not_detected", "occurrences": []}
    alias_set = {item.casefold() for item in aliases}
    terms = [item for item in context_terms if item.casefold() not in alias_set]
    if not terms:
        return {"status": "keyword_only", "reason": "no_independent_context_rule", "occurrences": []}
    source = observation.get("source_field") or "raw_transcript"
    raw = str(context.get(source) or "")
    hits = locate_terms(raw, terms, segments=context.get("segments") if source == "raw_transcript" else None)
    if not hits:
        return {"status": "keyword_only", "reason": "no_nearby_context_evidence", "occurrences": []}
    if _same_context(observation.get("occurrences", []), hits, raw):
        return {"status": "context_present", "reason": "same_segment_or_sentence", "occurrences": hits[:3]}
    return {"status": "keyword_only", "reason": "context_found_elsewhere", "occurrences": hits[:3]}


def _revision_observation(context: dict, aliases: list[str]) -> dict:
    if context.get("availability") != "available":
        return {
            "status": "unassessable",
            "reason": context.get("reason") or "transcript_not_full_or_unavailable",
            "occurrences": [],
        }
    return _observation(context, aliases)


def _pair_message(before: str, after: str) -> str:
    if "unassessable" in {before, after}:
        return "ข้อมูลยังไม่พอเปรียบเทียบ"
    return {
        ("not_detected", "detected"): "ตรวจพบการกล่าวถึงในฉบับใหม่",
        ("detected", "detected"): "ตรวจพบในทั้งสองฉบับ",
        ("detected", "not_detected"): "ยังไม่ตรวจพบในข้อความฉบับใหม่",
        ("not_detected", "not_detected"): "ยังไม่ตรวจพบในข้อความทั้งสองฉบับ",
    }.get((before, after), "ข้อมูลยังไม่พอเปรียบเทียบ")


def build_revision_comparison(plan_snapshot: dict, child_recommendation: dict) -> dict:
    parent_context = plan_snapshot.get("parent_context") or {}
    child_context = (child_recommendation.get("evidence_bundle") or {}).get("input") or {}
    child_accepted, child_domain = _accepted_classification(child_recommendation)
    parent_accepted = bool(plan_snapshot.get("parent_category_accepted"))
    parent_domain = str(plan_snapshot.get("parent_domain") or "unknown")
    same_category = parent_domain == child_domain
    withheld = not parent_accepted or not child_accepted or not same_category
    topics = plan_snapshot.get("topics") or []
    status = "no_topics_selected" if not topics else "withheld_category" if withheld else "ready"
    method_status = "derived_same_matcher"
    if not parent_context or not child_context:
        method_status = "method_mismatch"
        status = "method_mismatch"

    parent_settings = plan_snapshot.get("parent_analysis_settings") or {}
    child_settings = child_context.get("analysis_settings") or {}
    parent_asr = str(parent_settings.get("asr_model") or "unknown")
    child_asr = str(child_settings.get("asr_model") or "unknown")
    limitations = [
        "ผลนี้ตรวจเฉพาะการเปลี่ยนแปลงของข้อความ ไม่ใช่คะแนนคุณภาพหรือการรับประกันผลตอบรับ",
        "แม้ใช้ ASR รุ่นเดียวกัน การถอดเสียงอาจคลาดเคลื่อนได้ จึงควรเปิดคลิปยืนยัน",
    ]
    if parent_asr != child_asr:
        limitations.append("asr_method_changed: แยกไม่ได้ว่าความต่างเกิดจากเนื้อหาหรือรุ่นถอดเสียง")
    if "unknown" in {parent_asr, child_asr}:
        limitations.append("ไม่ทราบรุ่นถอดเสียงของบางฉบับ จึงยืนยันว่าใช้วิธีถอดเสียงเดียวกันไม่ได้")
    if withheld:
        limitations.append("withheld_category: หมวดไม่ผ่านเกณฑ์หรือหมวดของสองฉบับไม่ตรงกัน")

    rows = []
    for topic in topics:
        aliases = list(topic.get("aliases") or [])
        if status in {"withheld_category", "method_mismatch"}:
            before = {"status": "unassessable", "reason": status, "occurrences": []}
            after = {"status": "unassessable", "reason": status, "occurrences": []}
        else:
            before = _revision_observation(parent_context, aliases)
            after = _revision_observation(child_context, aliases)
        rows.append(
            {
                "advice_id": topic.get("advice_id"),
                "evidence_topic_id": topic.get("evidence_topic_id"),
                "canonical_topic": topic.get("canonical_topic"),
                "title": topic.get("title"),
                "aliases": aliases,
                "before": {
                    **before,
                    "context": _context_status(parent_context, aliases, topic.get("context_terms") or [], before),
                },
                "after": {
                    **after,
                    "context": _context_status(child_context, aliases, topic.get("context_terms") or [], after),
                },
                "message": _pair_message(str(before.get("status")), str(after.get("status"))),
                "automatic_completion": False,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "method_version": METHOD_VERSION,
        "captured_method_versions": plan_snapshot.get("versions") or {},
        "derived_topic_matcher_version": TOPIC_MATCHER_VERSION,
        "status": status,
        "method_status": method_status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "plan": {
            "revision": plan_snapshot.get("plan_revision"),
            "captured_at": plan_snapshot.get("captured_at"),
            "saved_at": plan_snapshot.get("plan_saved_at"),
            "selected_advice_ids": plan_snapshot.get("selected_advice_ids") or [],
            "snapshot_sha256": fingerprint(plan_snapshot),
        },
        "parent": {
            "content_id": plan_snapshot.get("parent_content_id"),
            "analysis_id": plan_snapshot.get("parent_analysis_id"),
            "title": plan_snapshot.get("parent_title"),
            "created_at": plan_snapshot.get("parent_created_at"),
            "domain": parent_domain,
            "category_accepted": parent_accepted,
            "asr_model": parent_asr,
            "transcript_scope": parent_context.get("scope"),
            "input_hashes": plan_snapshot.get("parent_input_hashes") or {},
        },
        "child": {
            "domain": child_domain,
            "category_accepted": child_accepted,
            "asr_model": child_asr,
            "transcript_scope": child_context.get("scope"),
            "input_hashes": {
                "raw_transcript_sha256": text_hash(str(child_context.get("raw_transcript") or "")),
                "cleaned_transcript_sha256": text_hash(str(child_context.get("cleaned_transcript") or "")),
            },
        },
        "compatibility": {
            "same_topic_matcher": method_status == "derived_same_matcher",
            "same_alias_snapshot": True,
            "same_category": same_category,
            "parent_transcript_scope": parent_context.get("scope"),
            "child_transcript_scope": child_context.get("scope"),
            "asr_method_changed": parent_asr != child_asr,
        },
        "topics": rows,
        "limitations": limitations,
        "causal_or_quality_claim": False,
    }


def update_revision_job(db, comparison_id: int, *, expected_job_id: str | None = None, **values):
    values["updated_at"] = datetime.utcnow()
    query = db.query(ClipRevisionComparison).filter_by(comparison_id=comparison_id)
    if expected_job_id:
        query = query.filter_by(job_id=expected_job_id, status="running")
    changed = query.update(values, synchronize_session=False)
    db.commit()
    if expected_job_id and changed != 1:
        raise RuntimeError("Revision attempt changed while processing")


def revision_job_response(db, row: ClipRevisionComparison) -> dict:
    snapshot = _json(row.plan_snapshot_json)
    comparison = _json(row.comparison_result_json)
    result = None
    if row.status == "completed" and row.child_content_id is not None:
        result = get_user_content_detail(
            db, user_id=row.user_id, content_id=row.child_content_id
        )
        if result is not None:
            result["saved"] = True
            result["revision_comparison"] = comparison
    return {
        "job_id": row.job_id,
        "status": row.status,
        "stage": row.stage,
        "progress": row.progress,
        "message": row.error_message or row.stage,
        "error": row.error_message if row.status == "failed" else None,
        "error_code": row.error_code,
        "created_at": utc_isoformat(row.created_at),
        "updated_at": utc_isoformat(row.updated_at),
        "result": result,
        "revision_context": {
            "parent_content_id": row.parent_content_id,
            "parent_analysis_id": row.parent_analysis_id,
            "plan_revision": row.plan_revision,
            "plan_saved_at": snapshot.get("plan_saved_at"),
            "selected_topics": [item.get("title") for item in snapshot.get("topics", [])],
            "notes_only": not bool(snapshot.get("topics")),
        },
    }


def get_revision_job(db, *, user_id: int, job_id: str) -> ClipRevisionComparison:
    row = db.query(ClipRevisionComparison).filter_by(job_id=job_id, user_id=user_id).first()
    if row is None:
        raise HTTPException(404, "ไม่พบงานอัปโหลดฉบับแก้ไข")
    return row


def mark_inprocess_jobs_interrupted(db) -> int:
    now = datetime.utcnow()
    rows = db.query(ClipRevisionComparison).filter(
        ClipRevisionComparison.job_backend == "inprocess",
        ClipRevisionComparison.status.in_(("queued", "running")),
    ).all()
    count = 0
    for row in rows:
        owner = _json(row.settings_snapshot_json).get("revision_process_owner")
        if owner and _owner_is_alive(owner):
            continue
        count += db.query(ClipRevisionComparison).filter_by(
            comparison_id=row.comparison_id, job_id=row.job_id, status=row.status,
        ).update(
            {
                "status": "interrupted",
                "stage": "interrupted",
                "error_code": "backend_restarted",
                "error_message": "Backend รีสตาร์ตก่อนงานเสร็จ กรุณากดลองใหม่",
                "updated_at": now,
            },
            synchronize_session=False,
        )
    db.commit()
    return int(count or 0)


def prepare_retry(db, *, user_id: int, job_id: str) -> ClipRevisionComparison:
    row = get_revision_job(db, user_id=user_id, job_id=job_id)
    if row.status not in {"failed", "interrupted"}:
        raise HTTPException(409, "งานนี้ยังไม่อยู่ในสถานะที่ลองใหม่ได้")
    if not os.path.isfile(row.file_path):
        raise HTTPException(409, "ไม่พบไฟล์ฉบับแก้ไขเดิม กรุณาอัปโหลดใหม่")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(403, "บัญชีนี้ไม่สามารถเริ่มงานใหม่ได้")
    if db.get(AnalysisResult, row.parent_analysis_id) is None:
        raise HTTPException(409, "ผลต้นฉบับถูกลบแล้ว ไม่สามารถลองเทียบใหม่ได้")
    settings = _json(row.settings_snapshot_json)
    settings["revision_process_owner"] = _process_owner()
    changed = db.query(ClipRevisionComparison).filter(
        ClipRevisionComparison.comparison_id == row.comparison_id,
        ClipRevisionComparison.job_id == job_id,
        ClipRevisionComparison.status.in_(("failed", "interrupted")),
    ).update({"job_id": uuid.uuid4().hex, "job_backend": str(runtime_get("job_backend") or "inprocess"),
              "status": "queued", "stage": "queued", "progress": 0, "error_code": None,
              "error_message": None, "started_at": None, "completed_at": None,
              "updated_at": datetime.utcnow(), "settings_snapshot_json": json.dumps(settings, ensure_ascii=False)},
             synchronize_session=False)
    db.commit()
    if changed != 1:
        raise HTTPException(409, "งานนี้เริ่มลองใหม่จากอีกหน้าต่างแล้ว")
    db.refresh(row)
    return row
