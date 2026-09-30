"""Notify followed categories using their own successful snapshot baselines."""
from app.database.models import TrendSnapshotRun
from app.services.follows import matched_interests
from app.services.live_trend_snapshots import (
    YOUTUBE_CATEGORY_SNAPSHOT_KIND, _latest_youtube_category_run,
    _youtube_category_results_for_run, _youtube_category_rows,
)
from app.services.notifications import create_live_trend_notification


def compare_category_interests(db, *, watch_session, region, topics, mode):
    query = db.query(TrendSnapshotRun).filter(
        TrendSnapshotRun.region == region,
        TrendSnapshotRun.snapshot_kind == YOUTUBE_CATEGORY_SNAPSHOT_KIND,
        TrendSnapshotRun.status.in_(("completed", "partial")),
    )
    latest = query.order_by(TrendSnapshotRun.run_id.desc()).first()
    if latest is None:
        return []
    cursor = watch_session.last_seen_category_run_id
    watch_session.last_seen_category_run_id = latest.run_id
    if cursor is None or db.get(TrendSnapshotRun, cursor) is None or mode == 'off' or not topics:
        return []
    notifications = []
    runs = query.filter(TrendSnapshotRun.run_id > cursor).order_by(TrendSnapshotRun.run_id).all()
    for run in runs:
        detected_at = run.completed_at or run.started_at
        for category_id, result in _youtube_category_results_for_run(run).items():
            if result.get('status') not in ('ok', 'empty'):
                continue
            rows = _youtube_category_rows(db, run_id=run.run_id, category_id=category_id, limit=50)
            candidates = [(row, matched_interests(row, topics, detected_at=detected_at)) for row in rows]
            candidates = [(row, interests) for row, interests in candidates if interests]
            if not candidates:
                continue
            previous = _latest_youtube_category_run(
                db, region=region, category_id=category_id, before_run_id=run.run_id, require_success=True)
            if previous is None:
                continue
            known = {row.trend_key for row in _youtube_category_rows(
                db, run_id=previous.run_id, category_id=category_id, limit=50)}
            for row, interests in candidates:
                if row.trend_key in known:
                    continue
                notification = create_live_trend_notification(
                    db, user_id=watch_session.user_id, watch_session_id=watch_session.watch_session_id,
                    item=row, detected_at=detected_at, matched_interests=interests)
                if notification is not None:
                    notifications.append(notification)
    return notifications
