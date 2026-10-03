"""Public chart data: observed ranks, never inferred popularity or search counts."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy.orm import Session, selectinload

from app.core.datetime_utils import utc_isoformat
from app.database.models import SystemConfig, TrendHistoryAttempt, TrendHistoryBucket, TrendSnapshotItem, TrendSnapshotRun
from app.services.view_metrics import view_metrics_are_comparable

RETENTION_DAYS = 90
GAP_SECONDS = 90 * 60


def _samples_for_run(run: TrendSnapshotRun) -> list[tuple[str, str, dict]]:
    if run.status not in {"completed", "partial"} or not run.completed_at:
        return []
    providers = json.loads(run.provider_status or "{}")
    grouped = defaultdict(list)
    for item in run.items:
        if 1 <= item.provider_rank <= 50:
            grouped[(item.platform, item.ranking_scope)].append({
                "key": item.trend_key, "title": item.title,
                "rank": item.provider_rank, "category": item.category,
                "video_url": item.video_url,
                "channel_title": item.channel_title,
                "snapshot_item_id": item.item_id,
                "views": item.views if item.platform == "youtube" and item.views_available is True else None,
                "view_metric_version": item.view_metric_version,
            })
    scopes = []
    for platform in ("youtube", "google"):
        provider = providers.get(platform, {})
        if provider.get("mode") != "live":
            continue
        if run.snapshot_kind == "global":
            if provider.get("status") in {"ok", "empty"}:
                scopes.append((platform, "global"))
        elif run.snapshot_kind == "youtube_categories" and platform == "youtube":
            for category, result in provider.get("categories", {}).items():
                if (result.get("status") in {"ok", "empty"}
                        and result.get("mode", provider.get("mode")) == "live"):
                    scopes.append((platform, f"category:{category}"))
    return [(platform, scope, {
        "run_id": run.run_id,
        "observed_at": utc_isoformat(run.completed_at),
        "items": sorted(grouped[(platform, scope)], key=lambda i: i["rank"]),
    }) for platform, scope in scopes]


def _enrich_source_metadata(stored: dict, sample: dict) -> str:
    by_key = {item["key"]: item for item in sample["items"]}
    for item in stored["items"]:
        source = by_key.get(item["key"], {})
        if source.get("title") == item.get("title"):
            for field in ("video_url", "channel_title"):
                if not item.get(field):
                    item[field] = source.get(field)
            # Only replaying this exact run may enrich a missing counter; never
            # replace an old observation with a newer run's cumulative views.
            for field in ("snapshot_item_id", "views", "view_metric_version"):
                if field not in item:
                    item[field] = source.get(field)
    return json.dumps(stored, ensure_ascii=False, separators=(",", ":"))


def archive_snapshot_run(db: Session, run: TrendSnapshotRun) -> None:
    """Same transaction as the snapshot; no FK to raw rows pruned later."""
    db.flush()
    archive_attempts(db, run)
    samples = _samples_for_run(run)
    for platform, scope, sample in samples:
        observed_at = run.completed_at
        hour = observed_at.replace(minute=0, second=0, microsecond=0)
        bucket = db.query(TrendHistoryBucket).filter_by(
            region=run.region, platform=platform, ranking_scope=scope,
            bucket_at=hour,
        ).first()
        payload = json.dumps(sample, ensure_ascii=False, separators=(",", ":"))
        if bucket is None:
            db.add(TrendHistoryBucket(
                region=run.region, platform=platform, ranking_scope=scope,
                bucket_at=hour, first_at=observed_at, last_at=observed_at,
                first_sample=payload, last_sample=payload,
            ))
        else:
            first, last = json.loads(bucket.first_sample), json.loads(bucket.last_sample)
            # Reprocessing the same run must preserve its original timestamp/ranks.
            if first.get("run_id") == run.run_id:
                bucket.first_sample = _enrich_source_metadata(first, sample)
            elif observed_at < bucket.first_at:
                bucket.first_at, bucket.first_sample = observed_at, payload
            if last.get("run_id") == run.run_id:
                bucket.last_sample = _enrich_source_metadata(last, sample)
            elif observed_at >= bucket.last_at:
                bucket.last_at, bucket.last_sample = observed_at, payload

    from app.services.trend_topic_store import capture_snapshot_topics
    capture_snapshot_topics(db, run, samples)


def archive_attempts(db: Session, run: TrendSnapshotRun) -> None:
    if not run.completed_at:
        return
    providers = json.loads(run.provider_status or "{}")
    for platform, provider in providers.items():
        if platform not in {"youtube", "google"}:
            continue
        scopes = {"global": provider} if run.snapshot_kind == "global" else {
            f"category:{key}": value for key, value in provider.get("categories", {}).items()}
        if not scopes and run.snapshot_kind == "youtube_categories" and platform == "youtube":
            from app.core.config import settings
            scopes = {f"category:{key}": provider for key in settings.youtube_trend_category_ids}
        for scope, result in scopes.items():
            live = result.get("mode", provider.get("mode")) == "live"
            completed = run.status in {"completed", "partial"}
            status = "observed" if completed and live and result.get("status") in {"ok", "empty"} else "failed"
            if result.get("mode", provider.get("mode")) == "mock":
                status = "excluded_mock"
            exists = db.query(TrendHistoryAttempt).filter_by(
                run_id=run.run_id, platform=platform, ranking_scope=scope).first()
            if exists is None:
                count = sum(1 for item in run.items if item.platform == platform and
                            item.ranking_scope == scope and 1 <= item.provider_rank <= 50)
                db.add(TrendHistoryAttempt(run_id=run.run_id, region=run.region,
                    platform=platform, ranking_scope=scope, observed_at=run.completed_at,
                    status=status, sample_count=count if status == "observed" else None))


def prune_trend_history(db: Session, *, now: datetime | None = None) -> None:
    cutoff = (now or datetime.utcnow()) - timedelta(days=RETENTION_DAYS)
    db.query(TrendHistoryBucket).filter(
        TrendHistoryBucket.last_at < cutoff,
    ).delete(synchronize_session=False)
    db.query(TrendHistoryAttempt).filter(TrendHistoryAttempt.observed_at < cutoff).delete(synchronize_session=False)


def backfill_retained_history(db: Session, *, now: datetime | None = None) -> None:
    """Only still-existing observations, including failed collection attempts."""
    cutoff = (now or datetime.utcnow()) - timedelta(days=RETENTION_DAYS)
    runs = db.query(TrendSnapshotRun).options(selectinload(TrendSnapshotRun.items).load_only(
        TrendSnapshotItem.platform, TrendSnapshotItem.ranking_scope,
        TrendSnapshotItem.trend_key, TrendSnapshotItem.title,
        TrendSnapshotItem.provider_rank, TrendSnapshotItem.category,
        TrendSnapshotItem.video_url, TrendSnapshotItem.channel_title,
        TrendSnapshotItem.views, TrendSnapshotItem.views_available,
        TrendSnapshotItem.view_metric_version,
    )).filter(
        TrendSnapshotRun.completed_at >= cutoff,
        TrendSnapshotRun.status.in_(["completed", "partial", "failed"]),
    ).order_by(TrendSnapshotRun.completed_at).all()
    for run in runs:
        archive_snapshot_run(db, run)
    prune_trend_history(db, now=now)
    db.commit()


def _view_interval(previous: dict | None, current: dict, key: str) -> dict:
    result = {"status": "no_baseline", "delta": None, "per_hour": None,
              "from_at": previous["observed_at"] if previous else None,
              "to_at": current["observed_at"],
              "from_run_id": previous["run_id"] if previous else None,
              "to_run_id": current["run_id"],
              "from_item_id": previous["item_ids"].get(key) if previous else None,
              "to_item_id": current["item_ids"].get(key),
              "from_views": previous["views"].get(key) if previous else None,
              "to_views": current["views"].get(key), "elapsed_seconds": None}
    if previous is None:
        return result
    elapsed = (datetime.fromisoformat(current["observed_at"].replace("Z", "+00:00")) -
               datetime.fromisoformat(previous["observed_at"].replace("Z", "+00:00"))).total_seconds()
    result["elapsed_seconds"] = elapsed
    if current["break_before"] or elapsed <= 0:
        result["status"] = "collection_gap"
    elif key not in current["ranks"] or key not in previous["ranks"]:
        result["status"] = "not_in_both_samples"
    elif result["from_views"] is None or result["to_views"] is None:
        result["status"] = "missing_views"
    elif not view_metrics_are_comparable("youtube", current["view_metrics"].get(key), previous["view_metrics"].get(key)):
        result["status"] = "metric_changed"
    elif result["to_views"] < result["from_views"]:
        result["status"] = "counter_decreased"
    else:
        result["status"] = "measured"
        result["delta"] = result["to_views"] - result["from_views"]
        result["per_hour"] = round(result["delta"] * 3600 / elapsed, 2)
    return result


def _rank_movement(points: list[dict], key: str, *, stale: bool, interrupted: bool) -> dict:
    current = points[-1]
    previous = points[-2] if len(points) > 1 else None
    before = previous["ranks"].get(key) if previous else None
    after = current["ranks"].get(key)
    result = {"status": "insufficient", "previous_rank": before, "current_rank": after,
              "change": None, "from_at": previous["observed_at"] if previous else None,
              "to_at": current["observed_at"], "from_run_id": previous["run_id"] if previous else None,
              "to_run_id": current["run_id"]}
    if interrupted:
        result["status"] = "latest_unavailable"
    elif stale:
        result["status"] = "stale"
    elif previous is None:
        pass
    elif current["break_before"]:
        result["status"] = "collection_gap"
    elif current["total"] == 0 or previous["total"] == 0:
        result["status"] = "empty_sample"
    elif before is not None and after is None:
        result["status"] = "not_in_latest"
    elif before is None and after is not None:
        result["status"] = "new_entry"
    elif after is None:
        result["status"] = "not_in_latest"
    else:
        result["change"] = before - after
        result["status"] = "up" if before > after else "down" if before < after else "unchanged"
    return result


def load_trend_history(
    db: Session, *, region: str, platform: str, days: int = 7,
    category_id: str | None = None, item_key: str | None = None, now: datetime | None = None,
) -> dict:
    if platform not in {"youtube", "google"} or days not in {1, 5, 7, 30, 90}:
        raise ValueError("Unsupported platform or history period")
    if category_id and platform != "youtube":
        raise ValueError("Category history is available for YouTube only")
    scope = f"category:{category_id}" if category_id else "global"
    end = now or datetime.utcnow()
    start = end - timedelta(days=days)
    if days == 7:
        # Seven Bangkok calendar dates, including the unfinished current day.
        start = (end + timedelta(hours=7)).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=6, hours=7)
    buckets = db.query(TrendHistoryBucket).filter(
        TrendHistoryBucket.region == region,
        TrendHistoryBucket.platform == platform,
        TrendHistoryBucket.ranking_scope == scope,
        TrendHistoryBucket.bucket_at >= start.replace(minute=0, second=0, microsecond=0),
        TrendHistoryBucket.bucket_at <= end,
    ).order_by(TrendHistoryBucket.bucket_at).all()
    samples = {}
    for bucket in buckets:
        for timestamp, payload in ((bucket.first_at, bucket.first_sample),
                                   (bucket.last_at, bucket.last_sample)):
            if start <= timestamp <= end:
                samples[timestamp] = json.loads(payload)
    ordered = sorted(samples.items())
    attempts = db.query(TrendHistoryAttempt).filter(
        TrendHistoryAttempt.region == region, TrendHistoryAttempt.platform == platform,
        TrendHistoryAttempt.ranking_scope == scope, TrendHistoryAttempt.observed_at >= start,
        TrendHistoryAttempt.observed_at <= end).order_by(TrendHistoryAttempt.observed_at, TrendHistoryAttempt.id).all()
    failures = [attempt.observed_at for attempt in attempts if attempt.status == "failed"]
    interruptions = [attempt.observed_at for attempt in attempts if attempt.status != "observed"]
    points = []
    titles = {}
    last_seen = {}
    previous_at = None
    for timestamp, sample in ordered:
        items = {item["key"]: item for item in sample["items"] if 1 <= item["rank"] <= 50}
        ranks = {key: item["rank"] for key, item in items.items()}
        counts = Counter(item["category"] for item in items.values())
        for item in items.values():
            titles[item["key"]] = item["title"]
            last_seen[item["key"]] = sample["observed_at"]
        points.append({
            "observed_at": sample["observed_at"], "run_id": sample["run_id"],
            "break_before": previous_at is not None and
                ((timestamp - previous_at).total_seconds() > GAP_SECONDS or
                 any(previous_at < failed <= timestamp for failed in interruptions)),
            "total": len(ranks), "ranks": ranks,
            "category_counts": dict(counts) if platform == "youtube" and not category_id else {},
            "views": {key: item["views"] for key, item in items.items()
                      if platform == "youtube" and isinstance(item.get("views"), int)
                      and not isinstance(item["views"], bool) and item["views"] >= 0},
            "view_metrics": {key: item.get("view_metric_version") for key, item in items.items()} if platform == "youtube" else {},
            "item_ids": {key: item.get("snapshot_item_id") for key, item in items.items()},
        })
        previous_at = timestamp
    latest_ranks = points[-1]["ranks"] if points else {}
    keys = sorted(titles, key=lambda k: (latest_ranks.get(k, 999), titles[k]))
    occurrences = Counter(key for point in points for key in point["ranks"])
    candidates = list(latest_ranks) or keys
    default_key = min(candidates, key=lambda k: (-occurrences[k], latest_ranks.get(k, 999), k)) if candidates else None
    selected_key = item_key if item_key in titles else default_key
    previous = None
    for point in points:
        for field in ("views", "view_metrics", "item_ids"):
            point[field] = {selected_key: point[field][selected_key]} if selected_key in point[field] else {}
        point["view_intervals"] = {selected_key: _view_interval(previous, point, selected_key)} if (
            platform == "youtube" and selected_key is not None) else {}
        previous = point
    hourly = defaultdict(list)
    for attempt in attempts:
        hourly[attempt.observed_at.replace(minute=0, second=0, microsecond=0)].append(attempt)
    observed_hours = {timestamp.replace(minute=0, second=0, microsecond=0) for timestamp, _ in ordered}
    hours, hour = [], start.replace(minute=0, second=0, microsecond=0)
    while hour <= end:
        records = hourly[hour]
        bad = sum(record.status == "failed" for record in records)
        good = hour in observed_hours
        hours.append({"hour": utc_isoformat(hour),
                      "status": "partial" if good and bad else "observed" if good else "failed" if bad else "no_observation",
                      "failed_attempts": bad, "observed": good})
        hour += timedelta(hours=1)
    stale = not ordered or (end - ordered[-1][0]).total_seconds() > GAP_SECONDS
    latest_attempt = attempts[-1] if attempts else None
    interrupted = bool(latest_attempt and latest_attempt.status != "observed"
                       and (not ordered or latest_attempt.observed_at >= ordered[-1][0]))
    daily = {}
    for entry in hours:
        local = datetime.fromisoformat(entry["hour"].replace("Z", "+00:00")) + timedelta(hours=7)
        day = daily.setdefault(local.date().isoformat(), {"date": local.date().isoformat(),
            "observed_hours": 0, "failed_attempts": 0, "unobserved_hours": 0})
        day["observed_hours"] += int(entry["observed"])
        day["unobserved_hours"] += int(not entry["observed"])
        day["failed_attempts"] += entry["failed_attempts"]
    config = db.query(SystemConfig).filter(SystemConfig.user_id.is_(None)).order_by(SystemConfig.config_id).first()
    schedule = None if config is None else {
        "mode": config.trend_schedule_mode, "enabled": bool(config.trend_refresh_enabled),
        "start_hour": config.trend_window_start_hour, "end_hour": config.trend_window_end_hour,
        "timezone": "Asia/Bangkok", "applies_to": "current_configuration_only",
    }
    return {
        "platform": platform, "region": region, "ranking_scope": scope,
        "selected_key": selected_key,
        "requested_from": utc_isoformat(start), "requested_to": utc_isoformat(end),
        "sampling": "first_and_last_observation_per_hour",
        "retention_days": RETENTION_DAYS,
        "method_version": "observed-scope-history-v2",
        "gap_threshold_seconds": GAP_SECONDS,
        "hours": hours,
        "daily_coverage": list(daily.values()),
        "collection_schedule": schedule,
        "default_selection": "most_observed_in_latest_ranking",
        "coverage": {
            "sample_count": len(points), "hours_observed": len(observed_hours),
            "hours_requested": len(hours),
            "latest_attempt_at": utc_isoformat(latest_attempt.observed_at) if latest_attempt else None,
            "latest_attempt_status": latest_attempt.status if latest_attempt else None,
            "latest_unavailable": interrupted,
            "first_at": points[0]["observed_at"] if points else None,
            "last_at": points[-1]["observed_at"] if points else None,
            "gap_count": sum(point["break_before"] for point in points),
            "failed_attempts": len(failures),
            "unobserved_hours": sum(not hour["observed"] for hour in hours),
            "is_stale": stale,
        },
        "items": [{"key": k, "title": titles[k], "latest_rank": latest_ranks.get(k),
                   "observation_count": occurrences[k],
                   "last_seen_at": last_seen[k],
                   "movement": _rank_movement(points, k, stale=stale, interrupted=interrupted)} for k in keys],
        "points": points,
    }
