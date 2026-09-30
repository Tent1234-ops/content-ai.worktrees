"""Append-only observations of reference videos; never re-transcribe or re-label."""
from datetime import datetime, timedelta
from math import ceil

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.datetime_utils import utc_isoformat
from app.database.db import SessionLocal
from app.database.models import (DatasetContent, ReferenceStatisticsConfig,
                                 ReferenceStatisticsRun, ReferenceVideoStatistic)
from app.services.dataset_eligibility import reference_transcript_rows
from app.services.persistence import log_system_event
from app.services.trend_scheduler import collector_lock
from app.services.trend_settings import trend_schedule
from app.services.view_metrics import view_metric_version_for, view_metrics_are_comparable
from app.services.youtube_cc_dataset import _youtube_get, YouTubeQuotaExceededError


class ReferenceStatisticsParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    interval_seconds: int = Field(ge=3600, le=604800)
    daily_request_budget: int = Field(ge=1, le=1000)


def _config(db):
    config = db.get(ReferenceStatisticsConfig, 1)
    if config is None:
        config = ReferenceStatisticsConfig(config_id=1)
        db.add(config)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            config = db.get(ReferenceStatisticsConfig, 1)
    return config


def _used_today(db, now):
    midnight = (now + timedelta(hours=7)).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=7)
    return int(db.query(func.coalesce(func.sum(ReferenceStatisticsRun.requests_used), 0)).filter(
        ReferenceStatisticsRun.started_at >= midnight,
        ReferenceStatisticsRun.started_at < midnight + timedelta(days=1)).scalar())


def statistics_settings(db, *, now=None):
    now = now or datetime.utcnow()
    config = _config(db)
    count = len(reference_transcript_rows(db, now=now))
    last = db.query(ReferenceStatisticsRun).order_by(ReferenceStatisticsRun.run_id.desc()).first()
    schedule = trend_schedule(db, now=now)
    window_hours = schedule["window"]["collections_per_day"] if schedule["schedule_mode"] == "hourly_window" else 24
    rounds = ceil(window_hours * 3600 / config.interval_seconds)
    calls = ceil(count / 50)
    effective_interval = _effective_interval(config, count, schedule)
    return {
        "enabled": config.enabled, "interval_seconds": config.interval_seconds,
        "daily_request_budget": config.daily_request_budget,
        "requests_used_today": _used_today(db, now), "budget_timezone": "Asia/Bangkok",
        "candidate_count": count, "requests_per_round": calls,
        "requested_requests_per_day": calls * rounds,
        "estimated_requests_per_day": min(config.daily_request_budget,
            calls * ceil(window_hours * 3600 / effective_interval)) if config.enabled and schedule["enabled"] else 0,
        "effective_interval_seconds": effective_interval,
        "blocked_until": utc_isoformat(config.blocked_until),
        "next_due_at": utc_isoformat(max(
            (last.started_at + timedelta(seconds=_effective_interval(config, count, schedule))) if last else now,
            config.blocked_until or now)) if config.enabled else None,
        "last_run": _run_dict(last) if last else None,
        "trend_history_retention_days": 90,
        "budget_scope": "reference_statistics_only",
    }


def _effective_interval(config, count, schedule):
    hours = schedule["window"]["collections_per_day"] if schedule["schedule_mode"] == "hourly_window" else 24
    affordable_rounds = max(1, config.daily_request_budget // max(1, ceil(count / 50)))
    return max(config.interval_seconds, ceil(hours * 3600 / affordable_rounds))


def save_statistics_settings(db, values, *, user_id):
    config = _config(db)
    for name, value in values.model_dump().items():
        setattr(config, name, value)
    config.updated_at = datetime.utcnow()
    log_system_event(db, user_id=user_id, action="reference_statistics_settings_update",
                     status="success", detail=values.model_dump_json())
    db.commit()
    return statistics_settings(db)


def _run_dict(run):
    return {"run_id": run.run_id, "status": run.status,
            "started_at": utc_isoformat(run.started_at), "completed_at": utc_isoformat(run.completed_at),
            "requests_used": run.requests_used, "candidate_count": run.candidate_count,
            "error_code": run.error_code}


def _fetch(ids):
    return _youtube_get("videos", api_key=settings.youtube_api_key, timeout_seconds=20,
                        part="statistics", id=",".join(ids))


def _count(value):
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
        return number if 0 <= number <= 9223372036854775807 and str(number) == str(value) else None
    except (ValueError, TypeError):
        return None


def refresh_reference_statistics(*, session_factory=SessionLocal, now=None, actor="backend",
                                 force=False, fetch=None):
    with collector_lock(session_factory, scope="references") as acquired:
        if not acquired:
            return {"status": "busy"}
        return _refresh(session_factory, now=now, actor=actor, force=force, fetch=fetch or _fetch)


def _refresh(session_factory, *, now, actor, force, fetch):
    clock = (lambda: now) if now is not None else datetime.utcnow
    now = clock()
    with session_factory() as db:
        config = _config(db)
        schedule = trend_schedule(db, now=now)
        if not config.enabled or (not force and not schedule["enabled"]):
            return {"status": "paused"}
        if not force and schedule["schedule_mode"] == "hourly_window":
            hour = (now + timedelta(hours=7)).hour
            if not schedule["window"]["start_hour"] <= hour <= schedule["window"]["end_hour"]:
                return {"status": "outside_window"}
        if config.blocked_until and now < config.blocked_until:
            return {"status": "quota_wait", "next_at": utc_isoformat(config.blocked_until)}
        last = db.query(ReferenceStatisticsRun).order_by(ReferenceStatisticsRun.run_id.desc()).first()
        if last and last.status == "running":
            if now - last.started_at < timedelta(minutes=15):
                return {"status": "busy"}
            last.status, last.completed_at, last.error_code = "interrupted", now, "worker_interrupted"
            db.commit()
        rows = reference_transcript_rows(db, now=now)
        interval = 60 if force else _effective_interval(config, len(rows), schedule)
        if last and now < last.started_at + timedelta(seconds=interval):
            return {"status": "not_due"}
        if not rows:
            return {"status": "no_candidates"}
        # Rotate oldest-observed first, so a small budget never starves later IDs.
        latest = dict(db.query(ReferenceVideoStatistic.dataset_id,
                              func.max(ReferenceVideoStatistic.observed_at)).group_by(
                                  ReferenceVideoStatistic.dataset_id).all())
        rows.sort(key=lambda r: (latest.get(r.dataset_id, datetime.min), r.dataset_id))
        run = ReferenceStatisticsRun(actor=actor, started_at=now, candidate_count=len(rows))
        db.add(run)
        db.commit()
        successful, failed, incomplete = 0, 0, 0
        for offset in range(0, len(rows), 50):
            batch = rows[offset:offset + 50]
            db.refresh(config)
            if not config.enabled:
                run.error_code = "paused"
                break
            if _used_today(db, clock()) >= config.daily_request_budget:
                run.error_code = "daily_budget"
                break
            # Reserve before I/O, including failed calls and interrupted processes.
            run.requests_used += 1
            db.commit()
            error = None
            try:
                payload = fetch([row.source_youtube_id for row in batch])
                if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
                    raise ValueError("Invalid videos.list payload")
                items = {item["id"]: item for item in payload["items"] if isinstance(item, dict) and "id" in item}
            except YouTubeQuotaExceededError:
                error, items = "provider_quota", {}
                config.blocked_until = clock() + timedelta(hours=24)
            except Exception:
                error, items = "provider_error", {}
            observed = clock()
            for row in batch:
                item = items.get(row.source_youtube_id)
                stats = (item or {}).get("statistics", {})
                if not isinstance(stats, dict):
                    stats = {}
                values = {field: _count(stats.get(key)) for field, key in
                          (("views", "viewCount"), ("likes", "likeCount"), ("comments", "commentCount"))}
                state = "failed" if error else "unavailable" if item is None else (
                    "complete" if all(v is not None for v in values.values()) else "partial")
                version = view_metric_version_for("youtube", observed)
                db.add(ReferenceVideoStatistic(run_id=run.run_id, dataset_id=row.dataset_id,
                    video_id=row.source_youtube_id, source_url=f"https://www.youtube.com/watch?v={row.source_youtube_id}",
                    observed_at=observed, status=state, error_code=error or ("not_returned" if item is None else None),
                    view_metric_version=version, **values))
                if state in {"complete", "partial"}:
                    successful += 1
                    incomplete += state == "partial"
                else:
                    failed += 1
                # Legacy latest-value columns are a single-time bundle. Do not mix
                # old likes with new views or stamp missing values as current zeroes.
                if state == "complete" and (not row.statistics_captured_at or observed >= row.statistics_captured_at):
                    row.views, row.likes, row.comments = values["views"], values["likes"], values["comments"]
                    row.statistics_captured_at, row.view_metric_version = observed, version
                    age = max((observed - row.published_at).total_seconds() / 86400, 1)
                    row.average_views_per_day = row.views / age
                    row.engagement_rate = (row.likes + row.comments) / max(row.views, 1)
            db.commit()
            if error:
                run.error_code = error
                break
        run.status = ("partial" if successful else "failed") if (failed or incomplete or run.error_code) else "completed"
        run.completed_at = clock()
        log_system_event(db, user_id=None, action="reference_statistics_refresh",
                         status="success" if run.status == "completed" else "warning" if run.status == "partial" else "failed",
                         detail=f"run_id={run.run_id}; status={run.status}; requests={run.requests_used}; observed={successful}; failed={failed}")
        db.commit()
        return _run_dict(run)


def video_statistics_history(db, dataset_id, *, now=None, days=90):
    now = now or datetime.utcnow()
    row = db.get(DatasetContent, dataset_id)
    if not row or row.deleted_at:
        raise ValueError("Dataset not found")
    observations = db.query(ReferenceVideoStatistic).filter(
        ReferenceVideoStatistic.dataset_id == dataset_id,
        ReferenceVideoStatistic.observed_at >= now - timedelta(days=days),
        ReferenceVideoStatistic.observed_at <= now).order_by(
            ReferenceVideoStatistic.observed_at, ReferenceVideoStatistic.observation_id).all()
    points, previous = [], None
    for observation in observations:
        point = {"id": observation.observation_id, "run_id": observation.run_id,
                 "observed_at": utc_isoformat(observation.observed_at), "status": observation.status,
                 "source_url": observation.source_url, "video_id": observation.video_id,
                 "error_code": observation.error_code, "view_metric_version": observation.view_metric_version,
                 "views": observation.views, "likes": observation.likes, "comments": observation.comments,
                 "growth": None}
        if previous is not None:
            hours = (observation.observed_at - previous.observed_at).total_seconds() / 3600
            comparable = observation.video_id == previous.video_id and view_metrics_are_comparable(
                "youtube", observation.view_metric_version, previous.view_metric_version)
            growth = {"from_at": utc_isoformat(previous.observed_at), "to_at": point["observed_at"],
                      "elapsed_hours": hours, "status": "observed_interval" if comparable and hours > 0 else "not_comparable"}
            for metric in ("views", "likes", "comments"):
                a, b = getattr(previous, metric), getattr(observation, metric)
                delta = b - a if comparable and hours > 0 and a is not None and b is not None else None
                growth[metric + "_delta"] = delta
                growth[metric + "_per_hour"] = round(delta / hours, 2) if delta is not None and delta >= 0 else None
                if delta is not None and delta < 0:
                    growth["status"] = "counter_correction"
            point["growth"] = growth
        # Failures/missing views break the chain instead of manufacturing a zero.
        previous = observation if observation.views is not None and observation.status in {"complete", "partial"} else None
        points.append(point)
    return {"dataset_id": dataset_id, "title": row.title, "points": points,
            "latest": points[-1] if points else None, "growth_method": "delta_divided_by_actual_elapsed_hours",
            "has_growth": bool(points and points[-1]["growth"] and points[-1]["growth"].get("views_per_hour") is not None)}


def statistics_overview(db, *, offset=0, limit=20, now=None):
    now = now or datetime.utcnow()
    rows = reference_transcript_rows(db, now=now)
    history_ids = {r[0] for r in db.query(ReferenceVideoStatistic.dataset_id).distinct()}
    row_ids = {row.dataset_id for row in rows}
    rows += db.query(DatasetContent).filter(DatasetContent.dataset_id.in_(history_ids - row_ids),
                                           DatasetContent.deleted_at.is_(None)).all()
    rows.sort(key=lambda r: r.dataset_id, reverse=True)
    items = []
    for row in rows[offset:offset + limit]:
        data = video_statistics_history(db, row.dataset_id, now=now)
        data.pop("points")
        data["category"] = row.taxonomy_leaf_key
        data["reference_eligible"] = row.dataset_id in row_ids
        items.append(data)
    return {"settings": statistics_settings(db, now=now), "total": len(rows), "items": items,
            "runs": [_run_dict(run) for run in db.query(ReferenceStatisticsRun).order_by(
                ReferenceStatisticsRun.run_id.desc()).limit(10)]}
