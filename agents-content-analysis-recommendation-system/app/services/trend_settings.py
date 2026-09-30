"""Persisted intervals for trend snapshots, separate from training imports."""
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.models import TrendSnapshotRun, TrendCollectionSlot
from app.services.admin_settings import get_or_create_admin_config
from app.services.persistence import log_system_event


class TrendScheduleParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    global_interval_seconds: int = Field(ge=60, le=86400)
    category_interval_seconds: int = Field(ge=60, le=86400)
    schedule_mode: Literal["interval", "hourly_window"] = "interval"
    start_hour: int = Field(default=14, ge=0, le=23)
    end_hour: int = Field(default=23, ge=0, le=23)

    @model_validator(mode="after")
    def validate_window(self):
        if self.end_hour < self.start_hour:
            raise ValueError("End hour must be at or after start hour (Asia/Bangkok)")
        if self.schedule_mode == "hourly_window":
            self.global_interval_seconds = self.category_interval_seconds = 3600
        return self


def window_schedule(db: Session, config, now: datetime) -> dict:
    # Thailand has no daylight-saving transitions; database timestamps stay UTC.
    local = now + timedelta(hours=7)
    midnight_utc = local.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=7)
    start, end = config.trend_window_start_hour, config.trend_window_end_hour
    entries = db.query(TrendCollectionSlot).filter(
        TrendCollectionSlot.region == settings.youtube_region,
        TrendCollectionSlot.scheduled_for >= midnight_utc,
        TrendCollectionSlot.scheduled_for < midnight_utc + timedelta(days=1),
    ).all()
    by_time = {entry.scheduled_for: entry for entry in entries}
    slots, next_at, current_slot = [], None, None
    for hour in range(start, end + 1):
        scheduled = midnight_utc + timedelta(hours=hour)
        row = by_time.get(scheduled)
        current = scheduled <= now < scheduled + timedelta(hours=1)
        state = row.status if row else (
            "missed" if now >= scheduled + timedelta(hours=1) else "pending" if current else "upcoming")
        if row and row.status == "running" and now - row.started_at > timedelta(minutes=15):
            state = "interrupted"
        if current and row is None:
            current_slot = scheduled
        if next_at is None and row is None and scheduled + timedelta(hours=1) > now:
            next_at = max(scheduled, now)
        slots.append({"scheduled_for": _iso(scheduled), "status": state,
                      "started_at": _iso(row.started_at) if row else None,
                      "completed_at": _iso(row.completed_at) if row else None,
                      "actor": row.actor if row else None})
    if next_at is None:
        next_at = midnight_utc + timedelta(days=1, hours=start)
    return {"timezone": "Asia/Bangkok", "start_hour": start, "end_hour": end,
            "collections_per_day": end - start + 1, "slots_today": slots,
            "current_slot": _iso(current_slot),
            "next_at": _iso(next_at) if config.trend_refresh_enabled else None,
            "due": bool(config.trend_refresh_enabled and current_slot is not None)}


def trend_schedule(db: Session, *, now: datetime | None = None) -> dict:
    now = now or datetime.utcnow()
    config = get_or_create_admin_config(db)
    enabled = bool(config.trend_refresh_enabled)
    intervals = {
        "global": config.trend_refresh_seconds or settings.live_trend_refresh_seconds,
        "youtube_categories": (config.youtube_category_refresh_seconds
                               or settings.youtube_category_trend_refresh_seconds),
    }
    runs = {}
    for kind, interval in intervals.items():
        query = db.query(TrendSnapshotRun).filter(
            TrendSnapshotRun.snapshot_kind == kind,
            TrendSnapshotRun.region == settings.youtube_region,
        )
        last = query.order_by(TrendSnapshotRun.run_id.desc()).first()
        success = query.filter(TrendSnapshotRun.status.in_(("completed", "partial"))).order_by(
            TrendSnapshotRun.run_id.desc()).first()
        # Failed attempts also consume quota. Use their time to avoid a retry loop.
        next_at = (last.completed_at or last.started_at) + timedelta(seconds=interval) if last else now
        running = bool(last and last.status == "running" and
                       now - last.started_at < timedelta(minutes=15))
        runs[kind] = {
            "last_attempt_at": _iso(last.started_at) if last else None,
            "last_success_at": _iso(success.completed_at) if success else None,
            "status": last.status if last else "not_started",
            "next_at": _iso(next_at) if enabled else None,
            "due": enabled and not running and now >= next_at,
        }
    window = window_schedule(db, config, now)
    if config.trend_schedule_mode == "hourly_window":
        for run in runs.values():
            run["due"], run["next_at"] = window["due"], window["next_at"]
    return {
        "enabled": enabled, "global_interval_seconds": intervals["global"],
        "category_interval_seconds": intervals["youtube_categories"], "runs": runs,
        "browser_poll_seconds": 60, "region": settings.youtube_region,
        "estimated_youtube_video_list_calls_per_day": (
            (1 + len(settings.youtube_trend_category_ids)) * window["collections_per_day"]
            if config.trend_schedule_mode == "hourly_window" else
            (86400 + intervals["global"] - 1) // intervals["global"] +
            len(settings.youtube_trend_category_ids) * ((86400 + intervals["youtube_categories"] - 1) // intervals["youtube_categories"])
        ) if enabled else 0,
        "schedule_mode": config.trend_schedule_mode,
        "window": window,
        "worker": {"last_seen_at": _iso(config.trend_worker_seen_at),
                   "status": config.trend_worker_status},
    }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None


def save_trend_schedule(db: Session, parameters: TrendScheduleParameters, *, user_id: int | None) -> dict:
    config = get_or_create_admin_config(db)
    config.trend_refresh_enabled = parameters.enabled
    config.trend_refresh_seconds = parameters.global_interval_seconds
    config.youtube_category_refresh_seconds = parameters.category_interval_seconds
    config.trend_schedule_mode = parameters.schedule_mode
    config.trend_window_start_hour = parameters.start_hour
    config.trend_window_end_hour = parameters.end_hour
    log_system_event(db, user_id=user_id, action="admin_trend_schedule_update",
                     status="success", detail=parameters.model_dump_json())
    db.commit()
    return trend_schedule(db)
