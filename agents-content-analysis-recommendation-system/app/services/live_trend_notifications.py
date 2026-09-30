from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Iterable, List

from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.models import (
    Notification,
    FollowedTopic,
    TrendSnapshotItem,
    TrendSnapshotRun,
    User,
    UserTrendWatchSession,
)
from app.services.live_trend_snapshots import (
    GLOBAL_RANKING_SCOPE,
    GLOBAL_SNAPSHOT_KIND,
    PLATFORMS,
    load_latest_live_snapshot,
)
from app.services.notifications import create_live_trend_notification
from app.services.view_metrics import view_metrics_are_comparable
from app.services.follows import notification_mode, matched_interests
from app.services.category_interest_notifications import compare_category_interests


SUCCESS_PROVIDER_STATES = {"ok", "empty"}


def _provider_states(run: TrendSnapshotRun) -> Dict[str, str]:
    try:
        payload = json.loads(run.provider_status or "{}")
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        platform: str(details.get("status") or "error")
        for platform, details in payload.items()
        if isinstance(details, dict)
    }


def _items_by_platform(db: Session, *, run_id: int) -> Dict[str, List[TrendSnapshotItem]]:
    grouped: Dict[str, List[TrendSnapshotItem]] = defaultdict(list)
    rows = (
        db.query(TrendSnapshotItem)
        .filter(
            TrendSnapshotItem.run_id == run_id,
            TrendSnapshotItem.ranking_scope == GLOBAL_RANKING_SCOPE,
        )
        .order_by(
            TrendSnapshotItem.platform,
            TrendSnapshotItem.provider_rank,
            TrendSnapshotItem.item_id,
        )
        .all()
    )
    for row in rows:
        grouped[row.platform].append(row)
    return grouped


def _latest_successful_items_before(
    db: Session,
    *,
    region: str,
    platform: str,
    run_id: int,
) -> List[TrendSnapshotItem] | None:
    runs = (
        db.query(TrendSnapshotRun)
        .filter(
            TrendSnapshotRun.region == region,
            TrendSnapshotRun.snapshot_kind == GLOBAL_SNAPSHOT_KIND,
            TrendSnapshotRun.run_id <= run_id,
            TrendSnapshotRun.status.in_(("completed", "partial")),
        )
        .order_by(TrendSnapshotRun.run_id.desc())
        .limit(120)
        .all()
    )
    for run in runs:
        if _provider_states(run).get(platform) not in SUCCESS_PROVIDER_STATES:
            continue
        return (
            db.query(TrendSnapshotItem)
            .filter(
                TrendSnapshotItem.run_id == run.run_id,
                TrendSnapshotItem.platform == platform,
                TrendSnapshotItem.ranking_scope == GLOBAL_RANKING_SCOPE,
            )
            .order_by(
                TrendSnapshotItem.provider_rank,
                TrendSnapshotItem.item_id,
            )
            .all()
        )
    return None


def _latest_successful_run_and_items_before(
    db: Session,
    *,
    region: str,
    platform: str,
    run_id: int,
    completed_before: datetime | None = None,
) -> tuple[TrendSnapshotRun, List[TrendSnapshotItem]] | None:
    runs = (
        db.query(TrendSnapshotRun)
        .filter(
            TrendSnapshotRun.region == region,
            TrendSnapshotRun.snapshot_kind == GLOBAL_SNAPSHOT_KIND,
            TrendSnapshotRun.run_id <= run_id,
            TrendSnapshotRun.status.in_(("completed", "partial")),
        )
        .order_by(TrendSnapshotRun.run_id.desc())
        .limit(120)
        .all()
    )
    for run in runs:
        run_timestamp = run.completed_at or run.started_at
        if completed_before is not None and run_timestamp > completed_before:
            continue
        if _provider_states(run).get(platform) not in SUCCESS_PROVIDER_STATES:
            continue
        rows = (
            db.query(TrendSnapshotItem)
            .filter(
                TrendSnapshotItem.run_id == run.run_id,
                TrendSnapshotItem.platform == platform,
                TrendSnapshotItem.ranking_scope == GLOBAL_RANKING_SCOPE,
            )
            .order_by(
                TrendSnapshotItem.provider_rank,
                TrendSnapshotItem.item_id,
            )
            .all()
        )
        return run, rows
    return None


def _percentile(value: float, positive_values: List[float]) -> float:
    if value <= 0 or not positive_values:
        return 0.0
    at_or_below = sum(1 for candidate in positive_values if candidate <= value)
    return (at_or_below / len(positive_values)) * 100.0


def _apply_session_and_engagement_status(
    db: Session,
    *,
    snapshot: Dict[str, object],
    watch_session: UserTrendWatchSession | None,
) -> None:
    notified_keys = {
        key
        for (key,) in (
            db.query(Notification.trend_key)
            .filter(Notification.watch_session_id == watch_session.watch_session_id)
            .all()
        )
    } if watch_session is not None else set()
    default_run_id = snapshot.get("run_id")
    if not isinstance(default_run_id, int):
        return

    region = str(snapshot.get("region") or "TH")
    for platform in PLATFORMS:
        platform_payload = snapshot.get("platforms", {}).get(platform, {})
        items = platform_payload.get("items", [])
        data_run_id = platform_payload.get("data_run_id")
        if not isinstance(data_run_id, int):
            data_run_id = default_run_id
        current_run = db.get(TrendSnapshotRun, data_run_id)
        if current_run is None:
            continue
        current_timestamp = current_run.completed_at or current_run.started_at
        comparison_cutoff = current_timestamp - timedelta(
            seconds=settings.live_trend_momentum_window_seconds
        )
        previous_snapshot = _latest_successful_run_and_items_before(
            db,
            region=region,
            platform=platform,
            run_id=data_run_id - 1,
            completed_before=comparison_cutoff,
        )
        previous_run, previous_rows = previous_snapshot or (None, [])
        previous_by_key = {row.trend_key: row for row in previous_rows}
        previous_ranks = {
            row.trend_key: row.provider_rank or index
            for index, row in enumerate(previous_rows, start=1)
        }
        previous_timestamp = (
            previous_run.completed_at or previous_run.started_at
            if previous_run is not None
            else None
        )
        comparison_seconds = max(
            1.0,
            (current_timestamp - previous_timestamp).total_seconds(),
        ) if previous_timestamp is not None else 0.0
        comparison_minutes = comparison_seconds / 60.0 if comparison_seconds else 0.0

        calculated: List[Dict[str, object]] = []
        for item in items:
            key = str(item.get("key") or "")
            current = float(item.get("engagement_signal") or 0.0)
            previous_row = previous_by_key.get(key)
            current_metric_version = str(
                item.get("view_metric_version") or ""
            )
            previous_metric_version = (
                str(previous_row.view_metric_version or "")
                if previous_row is not None
                else ""
            )
            metric_versions_comparable = (
                previous_row is not None
                and view_metrics_are_comparable(
                    platform,
                    current_metric_version,
                    previous_metric_version,
                )
            )
            metric_version_changed = (
                previous_row is not None and not metric_versions_comparable
            )
            previous = (
                float(previous_row.engagement_signal or 0.0)
                if metric_versions_comparable
                else None
            )
            delta = current - previous if previous is not None else 0.0
            raw_change = (
                (delta / previous) * 100.0
                if previous is not None and previous > 0
                else 0.0
            )
            if abs(raw_change) < 0.005:
                raw_change = 0.0
            rate = delta / comparison_minutes if comparison_minutes > 0 else 0.0
            current_rank = int(item.get("rank") or (len(calculated) + 1))
            previous_rank = (
                previous_ranks.get(key)
                if not metric_version_changed
                else None
            )
            rank_change = previous_rank - current_rank if previous_rank is not None else 0
            is_new = key in notified_keys

            if previous_snapshot is None:
                change_kind = "baseline"
                change_label = "Baseline"
            elif metric_version_changed:
                change_kind = "metric_baseline"
                change_label = "Metric baseline"
            elif previous_row is None:
                change_kind = "new"
                change_label = "New"
            elif platform == "google" or (
                int(item.get("views") or 0) == 0
                and int(item.get("likes") or 0) == 0
                and int(item.get("comments") or 0) == 0
            ):
                if rank_change > 0:
                    change_kind = "rank_up"
                    change_label = f"Up {rank_change} rank{'s' if rank_change != 1 else ''}"
                elif rank_change < 0:
                    change_kind = "rank_down"
                    moved = abs(rank_change)
                    change_label = f"Down {moved} rank{'s' if moved != 1 else ''}"
                elif abs(raw_change) >= 0.1:
                    change_kind = "interest"
                    prefix = "+" if raw_change > 0 else ""
                    change_label = f"{prefix}{raw_change:.1f}% interest"
                else:
                    change_kind = "none"
                    change_label = "No change"
            else:
                if abs(rate) < 0.05:
                    change_kind = "none"
                    change_label = "No change"
                else:
                    change_kind = "velocity_up" if rate > 0 else "velocity_down"
                    change_label = (
                        "Audience activity increased"
                        if rate > 0
                        else "Audience activity decreased"
                    )

            calculated.append(
                {
                    "item": item,
                    "rate": rate,
                    "rank_change": rank_change,
                    "change_kind": change_kind,
                    "change_label": change_label,
                    "raw_change": raw_change,
                    "delta": delta,
                    "is_new": is_new,
                    "has_previous": metric_versions_comparable,
                    "metric_version_changed": metric_version_changed,
                }
            )

        positive_rates = [
            float(row["rate"]) for row in calculated if float(row["rate"]) > 0
        ]
        negative_rates = [
            abs(float(row["rate"]))
            for row in calculated
            if float(row["rate"]) < 0
        ]
        hot_count = max(1, math.ceil(len(items) * 0.1)) if items else 0
        for row in calculated:
            item = row["item"]
            rate_percentile = _percentile(float(row["rate"]), positive_rates)
            cooling_percentile = _percentile(
                abs(float(row["rate"])),
                negative_rates,
            )
            rank_change = int(row["rank_change"])
            rank_momentum = min(100.0, 45.0 + (rank_change * 12.0)) if rank_change > 0 else 0.0
            momentum_score = max(rate_percentile, rank_momentum)
            meaningful_rising = (
                row["change_kind"] not in {"baseline", "new", "none"}
                and (rank_change >= 2 or rate_percentile >= 75.0)
            )
            meaningful_cooling = (
                row["change_kind"] not in {"baseline", "new", "none"}
                and (rank_change <= -2 or cooling_percentile >= 75.0)
            )
            change_label = str(row["change_label"])
            if row["change_kind"] == "velocity_up":
                if rate_percentile >= 90.0:
                    change_label = "Gaining fastest"
                elif rate_percentile >= 75.0:
                    change_label = "Gaining quickly"
            elif row["change_kind"] == "velocity_down":
                change_label = "Cooling"
            current_rank = int(item.get("rank") or 0)
            if current_rank > 0 and current_rank <= hot_count:
                status = "Hot"
            elif meaningful_rising or row["is_new"]:
                status = "Rising"
            elif meaningful_cooling:
                status = "Cooling"
            else:
                status = "Stable"

            item["engagement_change_percent"] = round(float(row["raw_change"]), 2)
            item["engagement_delta"] = round(float(row["delta"]), 2)
            item["engagement_rate_per_minute"] = round(float(row["rate"]), 2)
            item["rank_change"] = rank_change
            item["momentum_score"] = round(momentum_score, 1)
            item["change_kind"] = row["change_kind"]
            item["change_label"] = change_label
            item["has_previous_snapshot"] = bool(row["has_previous"])
            item["metric_version_changed"] = bool(
                row["metric_version_changed"]
            )
            item["comparison_window_seconds"] = int(round(comparison_seconds))
            item["is_meaningful_rising"] = meaningful_rising
            item["status"] = status
            item["is_new"] = bool(row["is_new"])


def load_public_trend_snapshot(
    db: Session,
    *,
    region: str,
    limit: int,
) -> Dict[str, object]:
    """Read shared rankings without creating a user session or notifications."""
    snapshot = load_latest_live_snapshot(db, region=region, limit=limit)
    _apply_session_and_engagement_status(db, snapshot=snapshot, watch_session=None)
    return snapshot


def compare_live_trend_snapshot(
    db: Session,
    *,
    user: User,
    watch_session: UserTrendWatchSession,
    region: str,
    limit: int,
    platforms: Iterable[str] = PLATFORMS,
) -> Dict[str, object]:
    region = region.upper()
    platforms = tuple(platforms)
    watch_session = db.query(UserTrendWatchSession).filter(
        UserTrendWatchSession.watch_session_id == watch_session.watch_session_id,
        UserTrendWatchSession.user_id == user.user_id,
    ).populate_existing().with_for_update().one()
    mode = notification_mode(db, user.user_id)
    topics = db.query(FollowedTopic).filter(FollowedTopic.user_id == user.user_id).all()
    snapshot = load_latest_live_snapshot(db, region=region, limit=limit)
    latest_run = (
        db.query(TrendSnapshotRun)
        .filter(
            TrendSnapshotRun.region == region,
            TrendSnapshotRun.snapshot_kind == GLOBAL_SNAPSHOT_KIND,
            TrendSnapshotRun.status.in_(("completed", "partial")),
        )
        .order_by(TrendSnapshotRun.run_id.desc())
        .first()
    )
    new_notifications = compare_category_interests(
        db, watch_session=watch_session, region=region, topics=topics, mode=mode)

    if latest_run is None:
        db.commit()
        _apply_session_and_engagement_status(db, snapshot=snapshot, watch_session=watch_session)
        return {
            **snapshot,
            "new_count": len(new_notifications),
            "new_notifications": new_notifications,
        }

    if watch_session.baseline_run_id is None or watch_session.last_seen_run_id is None:
        watch_session.baseline_run_id = latest_run.run_id
        watch_session.last_seen_run_id = latest_run.run_id
        watch_session.last_seen_at = datetime.utcnow()
        db.commit()
        _apply_session_and_engagement_status(db, snapshot=snapshot, watch_session=watch_session)
        return {
            **snapshot,
            "new_count": len(new_notifications),
            "new_notifications": new_notifications,
        }

    last_seen_run_id = int(watch_session.last_seen_run_id)
    if latest_run.run_id > last_seen_run_id:
        known_keys: Dict[str, set[str] | None] = {}
        for platform in platforms:
            previous_items = _latest_successful_items_before(
                db,
                region=region,
                platform=platform,
                run_id=last_seen_run_id,
            )
            known_keys[platform] = (
                {item.trend_key for item in previous_items}
                if previous_items is not None
                else None
            )

        runs = (
            db.query(TrendSnapshotRun)
            .filter(
                TrendSnapshotRun.region == region,
                TrendSnapshotRun.snapshot_kind == GLOBAL_SNAPSHOT_KIND,
                TrendSnapshotRun.run_id > last_seen_run_id,
                TrendSnapshotRun.run_id <= latest_run.run_id,
                TrendSnapshotRun.status.in_(("completed", "partial")),
            )
            .order_by(TrendSnapshotRun.run_id)
            .all()
        )
        for run in runs:
            states = _provider_states(run)
            grouped_items = _items_by_platform(db, run_id=run.run_id)
            detected_at = run.completed_at or datetime.utcnow()
            for platform in platforms:
                if states.get(platform) not in SUCCESS_PROVIDER_STATES:
                    continue
                current_items = grouped_items.get(platform, [])
                current_keys = {item.trend_key for item in current_items}
                previous_keys = known_keys.get(platform)
                if previous_keys is not None:
                    for item in current_items:
                        if item.trend_key in previous_keys:
                            continue
                        interests = matched_interests(item, topics, detected_at=detected_at)
                        if mode == 'off' or (mode == 'following' and not interests):
                            continue
                        notification = create_live_trend_notification(
                            db,
                            user_id=user.user_id,
                            watch_session_id=watch_session.watch_session_id,
                            item=item,
                            detected_at=detected_at,
                            matched_interests=interests,
                        )
                        if notification is not None:
                            new_notifications.append(notification)
                known_keys[platform] = current_keys

        watch_session.last_seen_run_id = latest_run.run_id
        watch_session.last_seen_at = datetime.utcnow()
        db.commit()

    db.commit()
    _apply_session_and_engagement_status(db, snapshot=snapshot, watch_session=watch_session)
    return {
        **snapshot,
        "new_count": len(new_notifications),
        "new_notifications": new_notifications,
    }
