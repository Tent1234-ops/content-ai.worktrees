import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.datetime_utils import utc_isoformat
from app.database.models import ClipRevisionPlan, UserContent
from app.services.contents import _latest_analysis
from app.services.persistence import log_system_event
from app.services.recommendation_evidence import fingerprint
from app.services.saved_recommendations import stored_recommendation


def _source(db, user_id, content_id):
    content = db.query(UserContent).filter_by(user_id=user_id, content_id=content_id).first()
    if content is None:
        raise HTTPException(404, "ไม่พบผลวิเคราะห์นี้")
    analysis = _latest_analysis(content)
    if analysis is None:
        raise HTTPException(409, "ผลเก่านี้ไม่มีรายการวิเคราะห์สำหรับผูกแผน")
    snapshot = stored_recommendation(content, analysis)
    return analysis, snapshot, fingerprint(snapshot)


def _response(content_id, analysis_id, digest, plan):
    return {"content_id": content_id, "analysis_id": analysis_id,
            "recommendation_fingerprint": digest, "revision": plan.revision if plan else 0,
            "selected_advice_ids": json.loads(plan.selected_advice_ids) if plan else [],
            "notes": plan.notes if plan else "", "status": "planning",
            "saved_at": utc_isoformat(plan.updated_at) if plan else None}


def get_revision_plan(db, *, user_id, content_id):
    analysis, _, digest = _source(db, user_id, content_id)
    plan = db.get(ClipRevisionPlan, analysis.result_id)
    if plan and plan.recommendation_fingerprint != digest:
        raise HTTPException(409, "หลักฐานของผลนี้ไม่ตรงกับแผนที่บันทึก กรุณาติดต่อผู้ดูแล ไม่ได้นำข้อมูลใหม่มาแทนแผนเดิม")
    return _response(content_id, analysis.result_id, digest, plan)


def save_revision_plan(db, *, user_id, content_id, payload):
    analysis, snapshot, digest = _source(db, user_id, content_id)
    if payload.analysis_id != analysis.result_id or payload.recommendation_fingerprint != digest:
        raise HTTPException(409, "ผลวิเคราะห์ที่เปิดไม่ตรงกับต้นฉบับ กรุณาโหลดผลที่บันทึกใหม่")
    actions = snapshot.get("actionable_recommendations") or {}
    classification = snapshot.get("classification") or {}
    context = (snapshot.get("evidence_bundle") or {}).get("input") or {}
    withheld = (classification.get("is_unknown") or
                (classification.get("acceptance") or {}).get("accepted") is False or
                (context and context.get("availability") != "available"))
    allowed = {item["id"] for item in actions.get("items", [])} if actions.get("status") == "ready" and not withheld else set()
    selected = payload.selected_advice_ids
    if len(set(selected)) != len(selected) or not set(selected).issubset(allowed):
        raise HTTPException(422, "เลือกได้เฉพาะคำแนะนำในผลวิเคราะห์ที่บันทึกนี้")
    now = datetime.utcnow()
    values = {"recommendation_fingerprint": digest, "selected_advice_ids": json.dumps(selected),
              "notes": payload.notes, "revision": payload.expected_revision + 1, "updated_at": now}
    try:
        if payload.expected_revision == 0:
            db.add(ClipRevisionPlan(analysis_id=analysis.result_id, **values))
            db.flush()
        else:
            changed = db.query(ClipRevisionPlan).filter_by(
                analysis_id=analysis.result_id, revision=payload.expected_revision,
                recommendation_fingerprint=digest).update(values, synchronize_session=False)
            if changed != 1:
                db.rollback()
                raise HTTPException(409, "แผนถูกแก้ไขจากอีกหน้าต่างแล้ว กรุณาโหลดแผนล่าสุดก่อนบันทึกอีกครั้ง")
        log_system_event(db, user_id, "clip_revision_plan_save", "success",
                         f"content_id={content_id}, analysis_id={analysis.result_id}, revision={values['revision']}, selected={len(selected)}")
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "มีแผนถูกบันทึกแล้ว กรุณาโหลดแผนล่าสุดก่อนบันทึกอีกครั้ง") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(503, "บันทึกแผนไม่สำเร็จ กรุณาลองใหม่ ข้อมูลเดิมยังไม่ถูกยืนยันว่าเปลี่ยนแปลง") from exc
    # Return only after commit, without a second read which could fail after a successful write.
    return {"content_id": content_id, "analysis_id": payload.analysis_id,
            "recommendation_fingerprint": digest, "revision": values["revision"],
            "selected_advice_ids": selected, "notes": payload.notes, "status": "planning",
            "saved_at": utc_isoformat(now)}
