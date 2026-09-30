from __future__ import annotations

import secrets
from datetime import datetime

from sqlalchemy.orm import Session

from app.database.models import TrendSnapshotRun, User, UserTrendWatchSession
from app.services.live_trend_snapshots import GLOBAL_SNAPSHOT_KIND, YOUTUBE_CATEGORY_SNAPSHOT_KIND


def _latest_baseline_run(db: Session, *, region: str) -> TrendSnapshotRun | None:
    return (
        db.query(TrendSnapshotRun)
        .filter(
            TrendSnapshotRun.region == region.upper(),
            TrendSnapshotRun.snapshot_kind == GLOBAL_SNAPSHOT_KIND,
            TrendSnapshotRun.status.in_(("completed", "partial")),
        )
        .order_by(TrendSnapshotRun.run_id.desc())
        .first()
    )


def start_trend_watch_session(
    db: Session,
    *,
    user: User,
    region: str,
) -> UserTrendWatchSession:
    baseline = _latest_baseline_run(db, region=region)
    category_baseline = db.query(TrendSnapshotRun).filter(
        TrendSnapshotRun.region == region.upper(),
        TrendSnapshotRun.snapshot_kind == YOUTUBE_CATEGORY_SNAPSHOT_KIND,
        TrendSnapshotRun.status.in_(("completed", "partial")),
    ).order_by(TrendSnapshotRun.run_id.desc()).first()
    now = datetime.utcnow()
    watch_session = UserTrendWatchSession(
        user_id=user.user_id,
        session_key=secrets.token_urlsafe(32),
        baseline_run_id=baseline.run_id if baseline else None,
        last_seen_run_id=baseline.run_id if baseline else None,
        last_seen_category_run_id=category_baseline.run_id if category_baseline else None,
        is_active=True,
        started_at=now,
        last_seen_at=now,
    )
    db.add(watch_session)
    db.commit()
    db.refresh(watch_session)
    return watch_session


def get_active_trend_watch_session(
    db: Session,
    *,
    user_id: int,
    session_key: str,
) -> UserTrendWatchSession | None:
    return (
        db.query(UserTrendWatchSession)
        .filter(
            UserTrendWatchSession.user_id == user_id,
            UserTrendWatchSession.session_key == session_key,
            UserTrendWatchSession.is_active.is_(True),
        )
        .first()
    )


def end_trend_watch_session(db: Session, *, watch_session: UserTrendWatchSession) -> None:
    now = datetime.utcnow()
    watch_session.is_active = False
    watch_session.ended_at = now
    watch_session.last_seen_at = now
    db.commit()
