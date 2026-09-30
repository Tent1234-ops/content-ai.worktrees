import json
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from app.core.config import settings
from app.database.db import SessionLocal
from app.services.jobs import enqueue
from app.services.live_trend_snapshots import (
    refresh_global_live_trends,
    refresh_youtube_category_live_trends,
)
from app.services.persistence import log_system_event, save_trending_items
from app.services.simple_cache import get as cache_get, set as cache_set
from app.services.trends import get_google_trending, get_tiktok_trending, get_youtube_trending
from app.services.trend_settings import trend_schedule
from app.services.trend_scheduler import collect_due


_RATE_LIMIT_SECONDS = {
    "youtube": 60,
    "google": 60,
    "tiktok": 60,
}
_DEFAULT_SOURCES = ["youtube", "google", "tiktok"]
_CACHE_TTL_SECONDS = 60

_last_fetch: Dict[str, datetime] = {}
_lock = threading.Lock()
_fetch_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()


class RateLimitedError(Exception):
    pass


def _now() -> datetime:
    return datetime.utcnow()


def _normalize_trend_item(item: object, source_name: str) -> Dict[str, object]:
    if hasattr(item, "dict") and callable(getattr(item, "dict")):
        data = item.dict()
    elif hasattr(item, "__dict__"):
        data = {k: v for k, v in item.__dict__.items() if not k.startswith("_")}
    else:
        data = {}

    keyword = data.get("query") or data.get("title") or data.get("channel_title") or data.get("creator") or source_name
    keyword = str(keyword).strip()
    if not keyword:
        keyword = source_name

    domain = data.get("category") or data.get("source_platform") or data.get("channel_title") or "general"
    domain = str(domain).strip() if domain is not None else "general"

    score = float(data.get("trend_score") or data.get("score") or 0.0)
    fetched_at = _now()
    meta = json.dumps({**data, "source_name": source_name}, ensure_ascii=False, default=str)

    return {
        "keyword": keyword,
        "score": score,
        "source": source_name,
        "domain": domain,
        "fetched_at": fetched_at,
        "meta": meta,
    }


def _get_rate_limit_for_source(source: str) -> int:
    return _RATE_LIMIT_SECONDS.get(source, 60)


def _should_fetch(source: str) -> bool:
    with _lock:
        last = _last_fetch.get(source)
        if last is None:
            return True
        return (datetime.utcnow() - last).total_seconds() >= _get_rate_limit_for_source(source)


def _touch_source_fetch(source: str) -> None:
    with _lock:
        _last_fetch[source] = datetime.utcnow()


def _cache_fetch_result(result: Dict[str, object]) -> None:
    cache_set("trending_fetcher:last_result", result, ttl_seconds=_CACHE_TTL_SECONDS)


def get_cached_fetch_result() -> Optional[Dict[str, object]]:
    return cache_get("trending_fetcher:last_result")


def _fetch_source_items(source: str, mode: str, limit: int) -> Tuple[str, List[object]]:
    if source == "youtube":
        return get_youtube_trending(region=settings.youtube_region, limit=limit, mode=mode)
    if source == "google":
        return get_google_trending(region=settings.google_region, limit=limit, mode=mode)
    if source == "tiktok":
        return get_tiktok_trending(region=settings.tiktok_region, limit=limit, mode=mode)
    raise ValueError(f"Unsupported source: {source}")


def fetch_trending_items(
    limit: int = 10,
    mode: str = "auto",
    sources: Optional[List[str]] = None,
    user_id: Optional[int] = None,
) -> Dict[str, object]:
    sources = sources or _DEFAULT_SOURCES
    stats: Dict[str, object] = {"created": 0, "updated": 0, "skipped": 0, "sources": {}}
    normalized_items: List[Dict[str, object]] = []

    for source in sources:
        try:
            if not _should_fetch(source):
                stats["skipped"] += 1
                stats["sources"][source] = {"status": "rate_limited"}
                continue

            source_mode, items = _fetch_source_items(source, mode=mode, limit=limit)
            normalized = [_normalize_trend_item(item, source_name=source) for item in items]
            normalized_items.extend(normalized)
            stats["sources"][source] = {
                "mode": source_mode,
                "total_fetched": len(normalized),
            }
            _touch_source_fetch(source)
        except Exception as exc:
            stats["sources"][source] = {"status": "error", "error": str(exc)}
            log_system_event(
                db=SessionLocal(),
                user_id=user_id,
                action=f"trending_fetch_{source}",
                status="failed",
                detail=str(exc),
            )

    if normalized_items:
        db = SessionLocal()
        try:
            save_stats = save_trending_items(db=db, items=normalized_items, user_id=user_id)
            stats["created"] = save_stats.get("created", 0)
            stats["updated"] = save_stats.get("updated", 0)
        finally:
            db.close()

    stats["fetched_at"] = datetime.utcnow().isoformat()
    _cache_fetch_result(stats)
    return stats


def fetch_trending_items_job(
    limit: int = 10,
    mode: str = "auto",
    sources: Optional[List[str]] = None,
    user_id: Optional[int] = None,
) -> Dict[str, object]:
    return fetch_trending_items(limit=limit, mode=mode, sources=sources, user_id=user_id)


def refresh_global_live_trends_job(
    limit: int | None = None,
    sources: Optional[List[str]] = None,
    user_id: Optional[int] = None,
) -> Dict[str, object]:
    selected_sources = sources or _DEFAULT_SOURCES
    result = refresh_global_live_trends(
        region=settings.youtube_region,
        limit=limit or settings.live_trend_limit,
        platforms=selected_sources,
    )
    if result.get("status") != "busy":
        for source in selected_sources:
            _touch_source_fetch(source)
    return result


def refresh_youtube_category_live_trends_job() -> Dict[str, object]:
    return refresh_youtube_category_live_trends(
        region=settings.youtube_region,
        limit=settings.youtube_category_trend_limit,
        category_ids=settings.youtube_trend_category_ids,
    )


def trigger_trending_refresh(
    limit: int | None = None,
    mode: str = "auto",
    sources: Optional[List[str]] = None,
    user_id: Optional[int] = None,
) -> Dict[str, object]:
    sources = sources or _DEFAULT_SOURCES
    now = _now()
    next_allowed = None
    for source in sources:
        with _lock:
            last = _last_fetch.get(source)
        if last is not None:
            elapsed = (now - last).total_seconds()
            wait = _get_rate_limit_for_source(source) - elapsed
            if wait > 0:
                next_allowed = (now + timedelta(seconds=wait)).isoformat()
                raise RateLimitedError(
                    f"Refresh for {source} is rate-limited. Try again after {round(wait)}s."
                )

    job_id = enqueue(
        refresh_global_live_trends_job,
        limit=limit or settings.live_trend_limit,
        sources=sources,
        user_id=user_id,
    )
    return {"job_id": job_id, "status": "queued", "rate_limited": False}


def run_scheduled_refreshes(*, session_factory=SessionLocal, now=None,
                            global_fetch=None, category_fetch=None) -> list[str]:
    from app.services.reference_statistics import refresh_reference_statistics
    result = collect_due(
        session_factory=session_factory, now=now,
        global_fetch=global_fetch or (lambda: refresh_global_live_trends_job(sources=["youtube", "google"])),
        category_fetch=category_fetch or refresh_youtube_category_live_trends_job,
        reference_fetch=(lambda: refresh_reference_statistics(session_factory=session_factory, now=now))
            if global_fetch is None and category_fetch is None else None,
        interval_runner=lambda: _run_interval_refreshes(session_factory=session_factory, now=now,
                                                       global_fetch=global_fetch, category_fetch=category_fetch),
    )
    return result["executed"]


def _run_interval_refreshes(*, session_factory=SessionLocal, now=None,
                            global_fetch=None, category_fetch=None) -> list[str]:
    executed = []
    failures = []
    for kind, fetch in (
        ("global", global_fetch or refresh_global_live_trends_job),
        ("youtube_categories", category_fetch or refresh_youtube_category_live_trends_job),
    ):
        # A provider call can be slow; apply a newly saved pause before the next job.
        with session_factory() as db:
            schedule = trend_schedule(db, now=now)
        if not schedule["runs"][kind]["due"]:
            continue
        try:
            fetch()
            executed.append(kind)
        except Exception as exc:
            failures.append(f"{kind}: {exc}")
    if failures:
        raise RuntimeError("; ".join(failures))
    return executed


def _fetch_loop() -> None:
    while not _stop_event.is_set():
        try:
            run_scheduled_refreshes()
        except Exception as exc:
            try:
                with SessionLocal() as db:
                    log_system_event(db=db, user_id=None, action="trending_fetcher_loop",
                                     status="failed", detail=str(exc))
                    db.commit()
            except Exception:
                logging.exception("Unable to persist trend scheduler error")
            finally:
                # Also back off when an error occurred before a run could be saved.
                _stop_event.wait(60)
        # Reload database configuration without requesting provider data on every tick.
        _stop_event.wait(5)


def start_trending_fetcher() -> None:
    global _fetch_thread
    if _fetch_thread and _fetch_thread.is_alive():
        return
    _stop_event.clear()
    _fetch_thread = threading.Thread(target=_fetch_loop, daemon=True)
    _fetch_thread.start()


def stop_trending_fetcher() -> None:
    _stop_event.set()
    global _fetch_thread
    if _fetch_thread:
        _fetch_thread.join(timeout=5)
        _fetch_thread = None
