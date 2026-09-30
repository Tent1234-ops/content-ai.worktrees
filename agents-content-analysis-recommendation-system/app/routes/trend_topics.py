"""Read-only public evidence and admin-only, versioned registry operations."""
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.datetime_utils import utc_isoformat
from app.database.db import get_db
from app.database.models import SystemLog, TrendTopicConfig, TrendTopicJob, TrendTopicVersion, User
from app.services.trend_topic_history import load_job_evidence, load_topic_history
from app.services.trend_topic_store import activate_version, packed, register_version

router = APIRouter(tags=["trend-topics"])


@router.get("/dashboard/public/topics/history")
def topic_history(region: str = Query(default="TH", pattern="^[A-Z]{2}$"),
                  scope: str = Query(default="global", pattern=r"^(global|category:\d{1,3})$"),
                  days: int = Query(default=5, ge=1, le=90),
                  version_id: str | None = Query(default=None, pattern="^[a-f0-9]{64}$"),
                  db: Session = Depends(get_db)):
    return load_topic_history(db, region=region, scope=scope, days=days, version_id=version_id)


@router.get("/dashboard/public/topics/evidence/{job_id}")
def topic_evidence(job_id: int, db: Session = Depends(get_db)):
    result = load_job_evidence(db, job_id)
    if result is None:
        raise HTTPException(404, "Topic job not found")
    return result


@router.get("/admin/trend-topics/status")
def topic_status(db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    config = db.get(TrendTopicConfig, 1)
    return {"active_version": config.active_version_id if config else None,
        "jobs": dict(db.query(TrendTopicJob.status, func.count()).group_by(TrendTopicJob.status).all()),
        "versions": [{"version_id": row.version_id, "extractor_version": row.extractor_version,
            "alias_version": row.alias_version, "created_at": utc_isoformat(row.created_at),
            "catalog": json.loads(row.catalog_json)} for row in db.query(TrendTopicVersion)
            .order_by(TrendTopicVersion.created_at.desc()).limit(30)],
        "failed_jobs": [{"job_id": row.job_id, "version_id": row.version_id, "error_code": row.error_code,
            "attempts": row.attempts} for row in db.query(TrendTopicJob).filter_by(status="failed")
            .order_by(TrendTopicJob.job_id.desc()).limit(50)]}


class CatalogRequest(BaseModel):
    catalog: dict
    reason: str = Field(min_length=3, max_length=500)


@router.post("/admin/trend-topics/versions")
def create_topic_version(payload: CatalogRequest, db: Session = Depends(get_db),
                         user: User = Depends(require_roles("admin"))):
    try:
        row = register_version(db, payload.catalog)
        db.add(SystemLog(user_id=user.user_id, action="trend_topic_version_create", status="success",
            detail=packed({"version_id": row.version_id, "reason": payload.reason})))
        db.commit()
        return {"version_id": row.version_id, "activated": False}
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        db.rollback()
        raise HTTPException(400, "Invalid approved topic catalog") from exc


@router.post("/admin/trend-topics/versions/{version_id}/activate")
def use_topic_version(version_id: str, db: Session = Depends(get_db),
                      user: User = Depends(require_roles("admin"))):
    try:
        queued = activate_version(db, version_id)
        db.add(SystemLog(user_id=user.user_id, action="trend_topic_version_activate", status="success",
            detail=packed({"version_id": version_id, "enqueued": queued})))
        db.commit()
        return {"version_id": version_id, "enqueued": queued}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc
