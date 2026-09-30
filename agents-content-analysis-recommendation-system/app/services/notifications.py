import json
from datetime import datetime
from typing import Dict, List

from sqlalchemy.orm import Session

from app.core.datetime_utils import utc_isoformat
from app.database.models import Notification, TrendSnapshotItem


def create_live_trend_notification(
    db: Session,
    *,
    user_id: int,
    watch_session_id: int,
    item: TrendSnapshotItem,
    detected_at: datetime,
    matched_interests: list[str] | None = None,
) -> Notification | None:
    existing = (
        db.query(Notification)
        .filter(
            Notification.user_id == user_id,
            Notification.watch_session_id == watch_session_id,
            Notification.trend_key == item.trend_key,
        )
        .first()
    )
    if existing is not None:
        return None

    notification = Notification(
        user_id=user_id,
        watch_session_id=watch_session_id,
        type="new_live_trend",
        trend_key=item.trend_key,
        platform=item.platform,
        title=item.title,
        category=item.category or "general",
        detected_at=detected_at,
        payload=json.dumps(
            {
                "trend_key": item.trend_key,
                "platform": item.platform,
                "title": item.title,
                "category": item.category or "general",
                "detected_at": utc_isoformat(detected_at),
                "video_url": item.video_url,
                "views": item.views,
                "likes": item.likes,
                "comments": item.comments,
                "published_at": item.published_at,
                "matched_interests": matched_interests or [],
                "ranking_scope": item.ranking_scope,
            },
            ensure_ascii=False,
        ),
        is_read=False,
    )
    db.add(notification)
    db.flush()
    return notification


def get_notifications(
    db: Session,
    *,
    user_id: int,
    watch_session_id: int,
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, object]:
    query = db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.watch_session_id == watch_session_id,
        Notification.type == "new_live_trend",
    )
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))
    total = query.count()
    items = (
        query.order_by(Notification.detected_at.desc(), Notification.notification_id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"total": total, "items": items}


def mark_notifications_read(
    db: Session,
    *,
    user_id: int,
    watch_session_id: int,
    ids: List[int],
) -> int:
    if not ids:
        return 0
    rows = (
        db.query(Notification)
        .filter(
            Notification.user_id == user_id,
            Notification.watch_session_id == watch_session_id,
            Notification.notification_id.in_(ids),
        )
        .all()
    )
    for row in rows:
        row.is_read = True
    db.commit()
    return len(rows)
