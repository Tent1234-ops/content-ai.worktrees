from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from app.database.models import FollowedTopic, SystemConfig, User, UserTrendWatchSession, TrendSnapshotRun
from app.core.config import settings
from app.services.live_trend_snapshots import YOUTUBE_CATEGORY_TITLES
from datetime import datetime


def follow_topic(db: Session, *, user_id: int, match_type: str, value: str,
                 platform: str = 'all') -> FollowedTopic:
    norm_value = (value or "").strip().lower()
    match_type = (match_type or "").strip().lower()
    if match_type not in ("domain", "keyword", "category"):
        raise ValueError("Invalid follow type")
    if not norm_value or len(norm_value) > 255:
        raise ValueError("A non-empty topic of at most 255 characters is required")
    if platform not in ('all', 'youtube', 'google', 'tiktok'):
        raise ValueError("Invalid platform")
    if match_type == 'category' and (platform != 'youtube' or norm_value not in YOUTUBE_CATEGORY_TITLES):
        raise ValueError("Choose a supported YouTube category")
    db.query(User).filter(User.user_id == user_id).with_for_update().one()
    existing = (
        db.query(FollowedTopic)
        .filter(FollowedTopic.user_id == user_id, FollowedTopic.match_type == match_type,
                FollowedTopic.value == norm_value, FollowedTopic.platform == platform)
        .first()
    )
    if existing:
        db.commit()
        return existing
    ft = FollowedTopic(user_id=user_id, match_type=match_type, value=norm_value,
                       platform=platform, created_at=datetime.utcnow())
    db.add(ft)
    db.flush()
    db.commit()
    return ft


def unfollow_topic(db: Session, *, user_id: int, id: Optional[int] = None, value: Optional[str] = None) -> int:
    if id is None and value is None:
        return 0
    q = db.query(FollowedTopic).filter(FollowedTopic.user_id == user_id)
    if id is not None:
        q = q.filter(FollowedTopic.id == int(id))
    if value is not None:
        q = q.filter(FollowedTopic.value == (value or "").strip().lower())
    rows = q.all()
    deleted = 0
    for r in rows:
        db.delete(r)
        deleted += 1
    if deleted:
        db.commit()
    return deleted


def list_followed_topics(db: Session, *, user_id: int, limit: int = 100, offset: int = 0) -> Dict[str, object]:
    q = db.query(FollowedTopic).filter(FollowedTopic.user_id == user_id)
    total = q.count()
    items = q.order_by(FollowedTopic.created_at.desc()).offset(offset).limit(limit).all()
    return {"total": total, "items": items}


def get_subscribers_for_value(db: Session, *, match_type: str, value: str) -> List[int]:
    # returns list of user_ids following the given match
    norm_value = (value or "").strip().lower()
    q = db.query(FollowedTopic).filter(FollowedTopic.match_type == match_type, FollowedTopic.value == norm_value)
    return [row.user_id for row in q.all()]


def notification_mode(db: Session, user_id: int) -> str:
    row = db.query(SystemConfig).filter(SystemConfig.user_id == user_id).first()
    return row.trend_notification_mode if row else 'all'


def follow_preferences(db: Session, *, user_id: int) -> dict:
    return {'notification_mode': notification_mode(db, user_id),
            'categories': [{'id': key, 'title': title, 'platform': 'youtube'}
                           for key, title in YOUTUBE_CATEGORY_TITLES.items()]}


def save_follow_preferences(db: Session, *, user_id: int, mode: str) -> dict:
    if mode not in ('all', 'following', 'off'):
        raise ValueError('Invalid notification mode')
    db.query(User).filter(User.user_id == user_id).with_for_update().one()
    config = db.query(SystemConfig).filter(SystemConfig.user_id == user_id).first()
    previous_mode = config.trend_notification_mode if config else 'all'
    if config is None:
        config = SystemConfig(user_id=user_id)
        db.add(config)
    config.trend_notification_mode = mode
    if previous_mode != mode:
        # Do not replay changes captured while notifications were disabled.
        cursors = {}
        for kind, field in (('global', 'last_seen_run_id'), ('youtube_categories', 'last_seen_category_run_id')):
            latest = db.query(TrendSnapshotRun).filter(
                TrendSnapshotRun.region == settings.youtube_region,
                TrendSnapshotRun.snapshot_kind == kind,
                TrendSnapshotRun.status.in_(('completed', 'partial')),
            ).order_by(TrendSnapshotRun.run_id.desc()).first()
            cursors[field] = latest.run_id if latest else None
        for watch in db.query(UserTrendWatchSession).filter(
            UserTrendWatchSession.user_id == user_id, UserTrendWatchSession.is_active.is_(True),
        ).with_for_update().all():
            for field, value in cursors.items():
                setattr(watch, field, value)
    db.commit()
    return follow_preferences(db, user_id=user_id)


def matched_interests(item, topics, *, detected_at: datetime) -> list[str]:
    matched = []
    for topic in topics:
        if topic.created_at > detected_at or topic.platform not in ('all', item.platform):
            continue
        value = topic.value.casefold()
        if topic.match_type == 'category':
            category = YOUTUBE_CATEGORY_TITLES.get(value, '')
            matches = item.platform == 'youtube' and (
                item.category_id == value or (item.category or '').casefold() == category.casefold())
            label = category
        elif topic.match_type == 'domain':
            matches = value == (item.category or '').casefold()
            label = topic.value
        else:
            # Only metadata from the provider; this is not transcript keyword extraction.
            matches = value in (item.title or '').casefold()
            label = topic.value
        if matches:
            matched.append(label)
    return matched
