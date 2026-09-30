"""Account administration with serialized privilege changes and explicit deletion."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.database.models import (
    AnalysisResult, ClusterMembership, ClusterRun, ContentKeyword, DatasetContent,
    FollowedTopic, ModelTrainingRun, Notification, Recommendation, SystemConfig,
    SystemLog, User, UserContent, UserTrendWatchSession,
)
from app.schemas.user_management import CreateAccount, UpdateAccount
from app.services.admin_settings import get_or_create_admin_config
from app.services.persistence import log_system_event

ROOT = Path(__file__).resolve().parents[2]
UPLOAD_ROOT = ROOT / "videos"


def _identity(user: User) -> dict:
    return {key: getattr(user, key) for key in ("user_id", "username", "email", "role", "is_active")}


def _revision(user: User) -> str:
    value = {**_identity(user), "updated_at": str(user.updated_at)}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _audit(db: Session, actor_id: int, action: str, target: User, **details) -> None:
    log_system_event(db, user_id=actor_id, action=action, status="success",
                     detail=json.dumps({"target_user_id": target.user_id, **details}, ensure_ascii=False))


def _lock_admin(db: Session, actor_id: int) -> None:
    # Serialize all web account mutations so two admins cannot remove each other.
    config = get_or_create_admin_config(db)
    db.query(SystemConfig).filter_by(config_id=config.config_id).with_for_update().one()
    actor = db.query(User).filter_by(user_id=actor_id).populate_existing().with_for_update().first()
    if actor is None or not actor.is_active or actor.role != "admin":
        raise HTTPException(403, "สิทธิ์ผู้ดูแลของคุณเปลี่ยนไป กรุณาเข้าสู่ระบบใหม่")


def _target(db: Session, user_id: int, revision: str) -> User:
    user = db.query(User).filter_by(user_id=user_id).populate_existing().with_for_update().first()
    if user is None:
        raise HTTPException(404, "ไม่พบบัญชีผู้ใช้")
    if _revision(user) != revision:
        raise HTTPException(409, "ข้อมูลบัญชีเปลี่ยนไปแล้ว กรุณาโหลดข้อมูลล่าสุดและยืนยันใหม่")
    return user


def _protect(db: Session, actor_id: int, user: User, *, remove_admin: bool) -> None:
    if user.user_id == actor_id:
        raise HTTPException(409, "ไม่สามารถเปลี่ยนบัญชีที่กำลังใช้งานผ่านหน้าจัดการผู้ใช้ได้")
    if remove_admin and user.role == "admin" and user.is_active:
        admins = db.query(User.user_id).filter_by(role="admin", is_active=True).with_for_update().all()
        if len(admins) <= 1:
            raise HTTPException(409, "ต้องมีผู้ดูแลระบบที่เปิดใช้งานเหลืออย่างน้อย 1 บัญชี")


def _revoke(db: Session, user_id: int) -> int:
    return db.query(UserTrendWatchSession).filter_by(user_id=user_id, is_active=True).update(
        {"is_active": False, "ended_at": datetime.utcnow()}, synchronize_session=False)


def _stats(db: Session, ids: list[int]) -> dict[int, dict]:
    stats = {i: {"contents": 0, "analyses": 0, "follows": 0, "sessions": 0,
                 "last_login_at": None, "last_seen_at": None} for i in ids}
    for model, name in ((UserContent, "contents"), (FollowedTopic, "follows")):
        for user_id, count in db.query(model.user_id, func.count()).filter(model.user_id.in_(ids)).group_by(model.user_id):
            stats[user_id][name] = count
    for user_id, count in db.query(UserContent.user_id, func.count(AnalysisResult.result_id)).join(
        AnalysisResult, AnalysisResult.content_id == UserContent.content_id
    ).filter(UserContent.user_id.in_(ids)).group_by(UserContent.user_id):
        stats[user_id]["analyses"] = count
    for user_id, count in db.query(UserTrendWatchSession.user_id, func.count()).filter(
        UserTrendWatchSession.user_id.in_(ids), UserTrendWatchSession.is_active.is_(True)
    ).group_by(UserTrendWatchSession.user_id):
        stats[user_id]["sessions"] = count
    for user_id, login, seen in db.query(UserTrendWatchSession.user_id,
        func.max(UserTrendWatchSession.started_at), func.max(UserTrendWatchSession.last_seen_at)
    ).filter(UserTrendWatchSession.user_id.in_(ids)).group_by(UserTrendWatchSession.user_id):
        stats[user_id].update(last_login_at=login, last_seen_at=seen)
    return stats


def _serialize(user: User, stats: dict, actor_id: int) -> dict:
    return {**_identity(user), "created_at": user.created_at, "updated_at": user.updated_at,
            "revision": _revision(user), "is_self": user.user_id == actor_id, "stats": stats}


def list_accounts(db: Session, *, actor_id: int, query: str = "", role: str = "all",
                  state: str = "all", offset: int = 0, limit: int = 20) -> dict:
    rows = db.query(User)
    if query.strip():
        term = query.strip().lower()
        rows = rows.filter(or_(func.lower(User.username).contains(term, autoescape=True),
                               func.lower(User.email).contains(term, autoescape=True)))
    if role != "all":
        rows = rows.filter(User.role == role)
    if state != "all":
        rows = rows.filter(User.is_active.is_(state == "active"))
    total = rows.count()
    users = rows.order_by(User.user_id.desc()).offset(offset).limit(limit).all()
    stats = _stats(db, [u.user_id for u in users])
    return {"total": total, "items": [_serialize(u, stats[u.user_id], actor_id) for u in users],
            "summary": {"total": db.query(User).count(),
                        "active": db.query(User).filter_by(is_active=True).count(),
                        "active_admins": db.query(User).filter_by(role="admin", is_active=True).count()}}


def account_detail(db: Session, user_id: int, *, actor_id: int) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "ไม่พบบัญชีผู้ใช้")
    return _serialize(user, _stats(db, [user_id])[user_id], actor_id)


def create_account(db: Session, payload: CreateAccount, *, actor_id: int) -> dict:
    password_hash = hash_password(payload.password)
    _lock_admin(db, actor_id)
    user = User(username=payload.username, email=payload.email, role=payload.role, password_hash=password_hash)
    db.add(user)
    db.flush()
    _audit(db, actor_id, "admin_user_create", user, role=user.role)
    db.commit()
    db.refresh(user)
    return account_detail(db, user.user_id, actor_id=actor_id)


def update_account(db: Session, user_id: int, payload: UpdateAccount, *, actor_id: int) -> dict:
    _lock_admin(db, actor_id)
    user = _target(db, user_id, payload.expected_revision)
    _protect(db, actor_id, user, remove_admin=payload.role != "admin" or not payload.is_active)
    before = _identity(user)
    for field in ("username", "email", "role", "is_active"):
        setattr(user, field, getattr(payload, field))
    after = _identity(user)
    changes = {key: {"before": before[key], "after": after[key]} for key in before if before[key] != after[key]}
    if changes:
        revoked = _revoke(db, user_id) if any(k in changes for k in ("email", "role", "is_active")) else 0
        _audit(db, actor_id, "admin_user_update", user, changes=changes, revoked_sessions=revoked)
    db.commit()
    db.refresh(user)
    return account_detail(db, user_id, actor_id=actor_id)


def revoke_sessions(db: Session, user_id: int, revision: str, *, actor_id: int) -> dict:
    _lock_admin(db, actor_id)
    user = _target(db, user_id, revision)
    _protect(db, actor_id, user, remove_admin=False)
    count = _revoke(db, user_id)
    _audit(db, actor_id, "admin_user_sessions_revoke", user, revoked_sessions=count)
    db.commit()
    return {"revoked_sessions": count}


def _owned_upload(raw: str | None) -> Path | None:
    if not raw:
        return None
    try:
        path = Path(raw)
        if not path.is_absolute():
            path = ROOT / path
        path = path.resolve()
    except (OSError, ValueError):
        return None
    if path.parent != UPLOAD_ROOT.resolve() or not re.match(r"^[0-9a-f]{32}_", path.name):
        return None
    return path


def delete_account(db: Session, user_id: int, revision: str, confirmation: str, *, actor_id: int) -> dict:
    _lock_admin(db, actor_id)
    user = _target(db, user_id, revision)
    _protect(db, actor_id, user, remove_admin=True)
    if confirmation != user.username:
        raise HTTPException(422, "ชื่อยืนยันไม่ตรงกับบัญชีที่ต้องการลบ")
    if db.query(ModelTrainingRun).filter_by(requested_by=user_id, active_slot=1).first():
        raise HTTPException(409, "บัญชีนี้มีงานเทรนที่ยังไม่จบ กรุณารอให้จบหรือระงับบัญชีไว้ก่อน")
    counts = _stats(db, [user_id])[user_id]
    contents = db.query(UserContent).filter_by(user_id=user_id).all()
    ids = [c.content_id for c in contents]
    files = set()
    referenced = {
        _owned_upload(raw) for (raw,) in db.query(UserContent.video_url).filter(UserContent.user_id != user_id)
    } | {_owned_upload(raw) for (raw,) in db.query(DatasetContent.video_url)}
    for content in contents:
        path = _owned_upload(content.video_url)
        if path and path not in referenced:
            files.add(path)
    # Delete private children first; retain shared training data and audit history.
    for model in (ContentKeyword, Recommendation, AnalysisResult, ClusterMembership):
        db.query(model).filter(model.content_id.in_(ids)).delete(synchronize_session=False)
    db.query(UserContent).filter_by(user_id=user_id).delete(synchronize_session=False)
    for model in (Notification, FollowedTopic, UserTrendWatchSession):
        db.query(model).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(SystemConfig).filter_by(user_id=user_id).delete(synchronize_session=False)
    for log in db.query(SystemLog).filter_by(user_id=user_id).all():
        try:
            detail = json.loads(log.detail or "{}")
        except (TypeError, ValueError):
            detail = {"original_detail": log.detail}
        if not isinstance(detail, dict):
            detail = {"original_detail": detail}
        log.detail = json.dumps({**detail, "deleted_actor_user_id": user_id}, ensure_ascii=False)
        log.user_id = None
    db.query(ClusterRun).filter_by(user_id=user_id).update({"user_id": None}, synchronize_session=False)
    run_ids = [r[0] for r in db.query(ModelTrainingRun.run_id).filter_by(requested_by=user_id)]
    db.query(ModelTrainingRun).filter_by(requested_by=user_id).update({"requested_by": None}, synchronize_session=False)
    _audit(db, actor_id, "admin_user_delete", user, retained_training_run_ids=run_ids,
           deleted_counts={k: v for k, v in counts.items() if isinstance(v, int)})
    db.query(User).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.commit()
    failed = 0
    for path in files:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            failed += 1
    if failed:
        log_system_event(db, actor_id, "admin_user_file_cleanup", "warning",
                         json.dumps({"target_user_id": user_id, "files_remaining": failed}))
        db.commit()
    return {"deleted": True, "user_id": user_id, "files_remaining": failed}
