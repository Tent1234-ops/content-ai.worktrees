from __future__ import annotations

import hashlib
import json
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, wait
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Mapping, Sequence

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.datetime_utils import utc_isoformat
from app.database.db import SessionLocal
from app.database.models import TrendSnapshotItem, TrendSnapshotRun, SystemConfig
from app.services.trends import (
    get_google_trending,
    get_tiktok_trending,
    get_youtube_categories,
    get_youtube_trending,
)
from app.services.view_metrics import (
    resolve_view_metric_version,
    view_metrics_are_comparable,
)
from app.services.trend_history import archive_snapshot_run, prune_trend_history


PLATFORMS = ("youtube", "google", "tiktok")
GLOBAL_SNAPSHOT_KIND = "global"
YOUTUBE_CATEGORY_SNAPSHOT_KIND = "youtube_categories"
GLOBAL_RANKING_SCOPE = "global"
YOUTUBE_CATEGORY_TITLES = {
    "1": "Film & Animation",
    "2": "Autos & Vehicles",
    "10": "Music",
    "15": "Pets & Animals",
    "17": "Sports",
    "20": "Gaming",
    "22": "People & Blogs",
    "23": "Comedy",
    "24": "Entertainment",
    "25": "News & Politics",
    "26": "Howto & Style",
    "28": "Science & Technology",
}
ProviderFetcher = Callable[[str, int], tuple[str, List[object]]]
YouTubeCategoryFetcher = Callable[[str, int, str], tuple[str, List[object]]]

_refresh_lock = threading.Lock()
_category_refresh_lock = threading.Lock()


def _item_to_dict(item: object) -> Dict[str, object]:
    if isinstance(item, dict):
        return dict(item)
    if hasattr(item, "model_dump") and callable(getattr(item, "model_dump")):
        return item.model_dump()
    if hasattr(item, "dict") and callable(getattr(item, "dict")):
        return item.dict()
    return {}


def _metric_available(data: Dict[str, object], metric: str) -> bool:
    explicit = data.get(f"{metric}_available")
    if explicit is not None:
        return bool(explicit)
    return metric in data and data.get(metric) is not None


def _parse_search_volume(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        parsed = int(value)
        return parsed if parsed > 0 else None
    normalized = (
        str(value).strip().upper().replace(",", "").replace("+", "").replace(" ", "")
    )
    multiplier = 1
    for suffix, factor in (("B", 1_000_000_000), ("M", 1_000_000), ("K", 1_000)):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            multiplier = factor
            break
    try:
        parsed = int(float(normalized) * multiplier)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _stable_key(platform: str, data: Dict[str, object]) -> str:
    title = str(data.get("title") or data.get("query") or "").strip().lower()
    url = str(data.get("video_url") or data.get("url") or "").strip().lower()
    return hashlib.sha1(f"{platform}|{url or title}".encode("utf-8")).hexdigest()


def normalize_live_item(
    platform: str,
    item: object,
    *,
    captured_at: datetime | None = None,
    ranking_scope: str = GLOBAL_RANKING_SCOPE,
    category_id: str | None = None,
    provider_rank: int = 0,
) -> Dict[str, object]:
    data = _item_to_dict(item)
    title = str(data.get("title") or data.get("query") or "").strip()
    category = str(data.get("category") or data.get("domain") or "general").strip() or "general"
    if platform == "google" and (
        category.casefold() in {"general", "search", "th", "thailand"}
        or (len(category) == 2 and category.isalpha())
    ):
        category = "Search Trends"
    source_platform = str(data.get("source_platform") or data.get("source") or platform).strip()
    published_at = data.get("published_at")
    if hasattr(published_at, "isoformat"):
        published_at = published_at.isoformat()
    elif published_at is not None:
        published_at = str(published_at)

    views = int(data.get("views") or 0)
    likes = int(data.get("likes") or 0)
    comments = int(data.get("comments") or 0)
    duration_raw = data.get("duration_seconds")
    try:
        duration_seconds = int(duration_raw) if duration_raw is not None else None
    except (TypeError, ValueError):
        duration_seconds = None
    trend_score = float(data.get("trend_score") or data.get("score") or 0.0)
    search_volume = _parse_search_volume(data.get("search_volume"))
    if search_volume is None:
        search_volume = _parse_search_volume(data.get("traffic_text"))
    engagement_signal = float((views * 0.2) + (likes * 1.5) + (comments * 3.0))
    if engagement_signal <= 0:
        engagement_signal = trend_score

    return {
        "key": _stable_key(platform, data),
        "platform": platform,
        "ranking_scope": ranking_scope,
        "category_id": category_id,
        "provider_rank": provider_rank,
        "title": title,
        "category": category,
        "source_platform": source_platform or platform,
        "video_url": str(data.get("video_url") or data.get("url") or "").strip(),
        "channel_title": str(
            data.get("channel_title") or data.get("creator") or ""
        ).strip(),
        "thumbnail_url": str(data.get("thumbnail_url") or "").strip(),
        "description": str(data.get("description") or "").strip(),
        "duration_seconds": duration_seconds,
        "views": views,
        "likes": likes,
        "comments": comments,
        "views_available": _metric_available(data, "views"),
        "likes_available": _metric_available(data, "likes"),
        "comments_available": _metric_available(data, "comments"),
        "search_volume": search_volume,
        "trend_score": trend_score,
        "engagement_signal": engagement_signal,
        "view_metric_version": resolve_view_metric_version(
            platform,
            captured_at,
            data.get("view_metric_version"),
        ),
        "published_at": published_at,
    }


def _provider_fetchers(region: str) -> Dict[str, ProviderFetcher]:
    return {
        "youtube": lambda _region, limit: get_youtube_trending(
            region=_region,
            limit=limit,
            mode="live",
        ),
        "google": lambda _region, limit: get_google_trending(
            region=_region,
            limit=limit,
            mode="live",
        ),
        "tiktok": lambda _region, limit: get_tiktok_trending(
            region=_region,
            limit=limit,
            mode="live",
        ),
    }


def _fetch_provider(
    platform: str,
    *,
    region: str,
    limit: int,
    fetcher: ProviderFetcher,
) -> Dict[str, object]:
    started = time.perf_counter()
    mode, raw_items = fetcher(region, limit)
    captured_at = datetime.utcnow()
    items = []
    for index, item in enumerate(raw_items, start=1):
        if not str(
            _item_to_dict(item).get("title")
            or _item_to_dict(item).get("query")
            or ""
        ).strip():
            continue
        items.append(
            normalize_live_item(
                platform,
                item,
                captured_at=captured_at,
                provider_rank=index,
            )
        )
    return {
        "status": "ok" if items else "empty",
        "mode": mode,
        "total": len(items),
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "items": items,
    }


def _cleanup_old_runs(
    db: Session,
    *,
    region: str,
    snapshot_kind: str,
) -> None:
    old_runs = (
        db.query(TrendSnapshotRun)
        .filter(
            TrendSnapshotRun.region == region,
            TrendSnapshotRun.snapshot_kind == snapshot_kind,
        )
        .order_by(TrendSnapshotRun.run_id.desc())
        .offset(settings.live_trend_snapshot_retention_runs)
        .all()
    )
    for run in old_runs:
        archive_snapshot_run(db, run)
        db.delete(run)


def refresh_global_live_trends(
    *,
    region: str | None = None,
    limit: int | None = None,
    platforms: Iterable[str] = PLATFORMS,
    fetchers: Mapping[str, ProviderFetcher] | None = None,
    db: Session | None = None,
) -> Dict[str, object]:
    region = (region or settings.youtube_region).upper()
    limit = min(100, max(1, int(limit or settings.live_trend_limit)))
    selected_platforms = [item.lower() for item in platforms if item.lower() in PLATFORMS]

    if not _refresh_lock.acquire(blocking=False):
        return {"status": "busy", "region": region, "total_items": 0, "providers": {}}

    owns_db = db is None
    session = db or SessionLocal()
    run: TrendSnapshotRun | None = None
    try:
        started_at = datetime.utcnow()
        run = TrendSnapshotRun(
            region=region,
            snapshot_kind=GLOBAL_SNAPSHOT_KIND,
            status="running",
            provider_status="{}",
            total_items=0,
            started_at=started_at,
        )
        session.add(run)
        session.commit()
        session.refresh(run)

        configured_fetchers = dict(fetchers or _provider_fetchers(region))
        executor = ThreadPoolExecutor(max_workers=max(1, len(selected_platforms)))
        futures: Dict[Future[Dict[str, object]], str] = {}
        for platform in selected_platforms:
            fetcher = configured_fetchers.get(platform)
            if fetcher is None:
                continue
            futures[
                executor.submit(
                    _fetch_provider,
                    platform,
                    region=region,
                    limit=limit,
                    fetcher=fetcher,
                )
            ] = platform

        timeout_seconds = settings.live_trend_provider_timeout_seconds
        done, pending = wait(futures, timeout=timeout_seconds)
        provider_results: Dict[str, Dict[str, object]] = {}

        for future in done:
            platform = futures[future]
            try:
                provider_results[platform] = future.result()
            except Exception as exc:
                provider_results[platform] = {
                    "status": "error",
                    "mode": "live_error",
                    "total": 0,
                    "error": str(exc),
                    "items": [],
                }

        for future in pending:
            platform = futures[future]
            future.cancel()
            provider_results[platform] = {
                "status": "error",
                "mode": "live_error",
                "total": 0,
                "error": f"Provider exceeded {timeout_seconds:g}s timeout",
                "items": [],
            }
        executor.shutdown(wait=False, cancel_futures=True)

        for platform in selected_platforms:
            provider_results.setdefault(
                platform,
                {
                    "status": "error",
                    "mode": "live_error",
                    "total": 0,
                    "error": "Provider fetcher is not configured",
                    "items": [],
                },
            )

        total_items = 0
        for platform, result in provider_results.items():
            for item in result.pop("items", []):
                session.add(
                    TrendSnapshotItem(
                        run_id=run.run_id,
                        platform=platform,
                        ranking_scope=str(item["ranking_scope"])[:64],
                        category_id=(
                            str(item["category_id"])[:32]
                            if item.get("category_id")
                            else None
                        ),
                        provider_rank=int(item["provider_rank"]),
                        trend_key=str(item["key"]),
                        title=str(item["title"])[:500],
                        category=str(item["category"])[:100],
                        source_platform=str(item["source_platform"])[:100],
                        video_url=str(item["video_url"])[:1024] or None,
                        channel_title=(
                            str(item["channel_title"])[:255]
                            if item.get("channel_title")
                            else None
                        ),
                        thumbnail_url=(
                            str(item["thumbnail_url"])[:1024]
                            if item.get("thumbnail_url")
                            else None
                        ),
                        description=(
                            str(item["description"])
                            if item.get("description")
                            else None
                        ),
                        duration_seconds=item.get("duration_seconds"),
                        views=int(item["views"]),
                        likes=int(item["likes"]),
                        comments=int(item["comments"]),
                        views_available=bool(item["views_available"]),
                        likes_available=bool(item["likes_available"]),
                        comments_available=bool(item["comments_available"]),
                        search_volume=item.get("search_volume"),
                        trend_score=float(item["trend_score"]),
                        engagement_signal=float(item["engagement_signal"]),
                        view_metric_version=str(item["view_metric_version"])[:64],
                        published_at=str(item["published_at"])[:64] if item["published_at"] else None,
                    )
                )
                total_items += 1

        error_count = sum(1 for result in provider_results.values() if result["status"] == "error")
        if error_count == len(provider_results):
            overall_status = "failed"
        elif error_count:
            overall_status = "partial"
        else:
            overall_status = "completed"

        completed_at = datetime.utcnow()
        run.status = overall_status
        run.provider_status = json.dumps(provider_results, ensure_ascii=False, default=str)
        run.total_items = total_items
        run.completed_at = completed_at
        archive_snapshot_run(session, run)
        _cleanup_old_runs(
            session,
            region=region,
            snapshot_kind=GLOBAL_SNAPSHOT_KIND,
        )
        prune_trend_history(session)
        session.commit()

        return {
            "run_id": run.run_id,
            "status": overall_status,
            "region": region,
            "total_items": total_items,
            "providers": provider_results,
            "started_at": utc_isoformat(started_at),
            "completed_at": utc_isoformat(completed_at),
        }
    except Exception as exc:
        session.rollback()
        if run is not None and run.run_id is not None:
            run = session.get(TrendSnapshotRun, run.run_id)
            if run is not None:
                run.status = "failed"
                run.provider_status = json.dumps({platform: {"status": "error", "mode": "live_error"}
                                                  for platform in selected_platforms})
                run.completed_at = datetime.utcnow()
                archive_snapshot_run(session, run)
                session.commit()
        raise
    finally:
        if owns_db:
            session.close()
        _refresh_lock.release()


def _category_refresh_interval(db: Session) -> int:
    config = db.query(SystemConfig).filter(SystemConfig.user_id.is_(None)).first()
    return (config.youtube_category_refresh_seconds if config else None) or settings.youtube_category_trend_refresh_seconds


def _youtube_category_scope(category_id: str) -> str:
    return f"category:{category_id}"


def _default_youtube_category_fetcher(
    region: str,
    limit: int,
    category_id: str,
) -> tuple[str, List[object]]:
    return get_youtube_trending(
        region=region,
        limit=limit,
        mode="live",
        video_category_id=category_id,
        allow_web_fallback=False,
    )


def _fetch_youtube_category(
    *,
    region: str,
    limit: int,
    category_id: str,
    category_title: str,
    fetcher: YouTubeCategoryFetcher,
) -> Dict[str, object]:
    started = time.perf_counter()
    mode, raw_items = fetcher(region, limit, category_id)
    captured_at = datetime.utcnow()
    scope = _youtube_category_scope(category_id)
    items: List[Dict[str, object]] = []
    for index, item in enumerate(raw_items, start=1):
        data = _item_to_dict(item)
        if not str(data.get("title") or "").strip():
            continue
        normalized = normalize_live_item(
            "youtube",
            item,
            captured_at=captured_at,
            ranking_scope=scope,
            category_id=category_id,
            provider_rank=index,
        )
        normalized["category"] = category_title
        items.append(normalized)
    return {
        "category_id": category_id,
        "title": category_title,
        "status": "ok" if items else "empty",
        "mode": mode,
        "total": len(items),
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "items": items,
    }


def refresh_youtube_category_live_trends(
    *,
    region: str | None = None,
    limit: int | None = None,
    category_ids: Sequence[str] | None = None,
    fetcher: YouTubeCategoryFetcher | None = None,
    category_titles: Mapping[str, str] | None = None,
    db: Session | None = None,
) -> Dict[str, object]:
    region = (region or settings.youtube_region).upper()
    limit = min(
        50,
        max(1, int(limit or settings.youtube_category_trend_limit)),
    )
    selected_ids = list(
        dict.fromkeys(
            str(item).strip()
            for item in (category_ids or settings.youtube_trend_category_ids)
            if str(item).strip()
        )
    )[:12]
    if not selected_ids:
        raise ValueError("No YouTube category IDs are configured")

    if not _category_refresh_lock.acquire(blocking=False):
        return {
            "status": "busy",
            "region": region,
            "snapshot_kind": YOUTUBE_CATEGORY_SNAPSHOT_KIND,
            "total_items": 0,
            "categories": {},
        }

    owns_db = db is None
    session = db or SessionLocal()
    run: TrendSnapshotRun | None = None
    try:
        started_at = datetime.utcnow()
        run = TrendSnapshotRun(
            region=region,
            snapshot_kind=YOUTUBE_CATEGORY_SNAPSHOT_KIND,
            status="running",
            provider_status="{}",
            total_items=0,
            started_at=started_at,
        )
        session.add(run)
        session.commit()
        session.refresh(run)

        titles = dict(YOUTUBE_CATEGORY_TITLES)
        if category_titles is not None:
            titles.update(
                {
                    str(key): str(value)
                    for key, value in category_titles.items()
                    if str(value).strip()
                }
            )
        elif fetcher is None:
            try:
                _, categories = get_youtube_categories(region=region, mode="live")
                titles.update(
                    {
                        item.category_id: item.title
                        for item in categories
                        if item.assignable and item.title
                    }
                )
            except Exception:
                # The configured 12 categories have stable fallback titles, so a
                # temporary metadata failure must not block their chart refresh.
                pass

        active_fetcher = fetcher or _default_youtube_category_fetcher
        executor = ThreadPoolExecutor(max_workers=min(4, len(selected_ids)))
        futures: Dict[Future[Dict[str, object]], str] = {}
        for category_id in selected_ids:
            futures[
                executor.submit(
                    _fetch_youtube_category,
                    region=region,
                    limit=limit,
                    category_id=category_id,
                    category_title=titles.get(category_id, category_id),
                    fetcher=active_fetcher,
                )
            ] = category_id

        done, pending = wait(
            futures,
            timeout=settings.youtube_category_snapshot_timeout_seconds,
        )
        category_results: Dict[str, Dict[str, object]] = {}
        for future in done:
            category_id = futures[future]
            try:
                category_results[category_id] = future.result()
            except Exception as exc:
                category_results[category_id] = {
                    "category_id": category_id,
                    "title": titles.get(category_id, category_id),
                    "status": "error",
                    "mode": "live_error",
                    "total": 0,
                    "error": str(exc),
                    "items": [],
                }
        for future in pending:
            category_id = futures[future]
            future.cancel()
            category_results[category_id] = {
                "category_id": category_id,
                "title": titles.get(category_id, category_id),
                "status": "error",
                "mode": "live_error",
                "total": 0,
                "error": (
                    "Category fetch exceeded "
                    f"{settings.youtube_category_snapshot_timeout_seconds:g}s timeout"
                ),
                "items": [],
            }
        executor.shutdown(wait=False, cancel_futures=True)

        total_items = 0
        for category_id in selected_ids:
            result = category_results.setdefault(
                category_id,
                {
                    "category_id": category_id,
                    "title": titles.get(category_id, category_id),
                    "status": "error",
                    "mode": "live_error",
                    "total": 0,
                    "error": "Category fetcher did not return a result",
                    "items": [],
                },
            )
            for item in result.pop("items", []):
                session.add(
                    TrendSnapshotItem(
                        run_id=run.run_id,
                        platform="youtube",
                        ranking_scope=str(item["ranking_scope"])[:64],
                        category_id=category_id[:32],
                        provider_rank=int(item["provider_rank"]),
                        trend_key=str(item["key"]),
                        title=str(item["title"])[:500],
                        category=str(item["category"])[:100],
                        source_platform=str(item["source_platform"])[:100],
                        video_url=str(item["video_url"])[:1024] or None,
                        channel_title=(
                            str(item["channel_title"])[:255]
                            if item.get("channel_title")
                            else None
                        ),
                        thumbnail_url=(
                            str(item["thumbnail_url"])[:1024]
                            if item.get("thumbnail_url")
                            else None
                        ),
                        description=(
                            str(item["description"])
                            if item.get("description")
                            else None
                        ),
                        duration_seconds=item.get("duration_seconds"),
                        views=int(item["views"]),
                        likes=int(item["likes"]),
                        comments=int(item["comments"]),
                        views_available=bool(item["views_available"]),
                        likes_available=bool(item["likes_available"]),
                        comments_available=bool(item["comments_available"]),
                        search_volume=item.get("search_volume"),
                        trend_score=float(item["trend_score"]),
                        engagement_signal=float(item["engagement_signal"]),
                        view_metric_version=str(item["view_metric_version"])[:64],
                        published_at=(
                            str(item["published_at"])[:64]
                            if item["published_at"]
                            else None
                        ),
                    )
                )
                total_items += 1

        error_count = sum(
            1
            for result in category_results.values()
            if result["status"] == "error"
        )
        if error_count == len(category_results):
            overall_status = "failed"
            provider_state = "error"
        elif error_count:
            overall_status = "partial"
            provider_state = "partial"
        else:
            overall_status = "completed"
            provider_state = "ok"

        completed_at = datetime.utcnow()
        run.status = overall_status
        run.provider_status = json.dumps(
            {
                "youtube": {
                    "status": provider_state,
                    "mode": "live",
                    "total": total_items,
                    "categories": category_results,
                }
            },
            ensure_ascii=False,
            default=str,
        )
        run.total_items = total_items
        run.completed_at = completed_at
        archive_snapshot_run(session, run)
        _cleanup_old_runs(
            session,
            region=region,
            snapshot_kind=YOUTUBE_CATEGORY_SNAPSHOT_KIND,
        )
        prune_trend_history(session)
        session.commit()

        return {
            "run_id": run.run_id,
            "status": overall_status,
            "snapshot_kind": YOUTUBE_CATEGORY_SNAPSHOT_KIND,
            "region": region,
            "total_items": total_items,
            "categories": category_results,
            "started_at": utc_isoformat(started_at),
            "completed_at": utc_isoformat(completed_at),
        }
    except Exception as exc:
        session.rollback()
        if run is not None and run.run_id is not None:
            failed_run = session.get(TrendSnapshotRun, run.run_id)
            if failed_run is not None:
                failed_run.status = "failed"
                failed_run.provider_status = json.dumps(
                    {"youtube": {"status": "error", "error": str(exc)}},
                    ensure_ascii=False,
                )
                failed_run.completed_at = datetime.utcnow()
                archive_snapshot_run(session, failed_run)
                session.commit()
        raise
    finally:
        if owns_db:
            session.close()
        _category_refresh_lock.release()


def _provider_status_for_run(run: TrendSnapshotRun) -> Dict[str, Dict[str, object]]:
    try:
        raw = json.loads(run.provider_status or "{}")
    except Exception:
        raw = {}
    return raw if isinstance(raw, dict) else {}


def _youtube_category_results_for_run(
    run: TrendSnapshotRun,
) -> Dict[str, Dict[str, object]]:
    youtube = _provider_status_for_run(run).get("youtube", {})
    categories = youtube.get("categories", {}) if isinstance(youtube, dict) else {}
    if not isinstance(categories, dict):
        return {}
    return {
        str(category_id): details
        for category_id, details in categories.items()
        if isinstance(details, dict)
    }


def _latest_youtube_category_run(
    db: Session,
    *,
    region: str,
    category_id: str | None = None,
    before_run_id: int | None = None,
    require_success: bool = False,
) -> TrendSnapshotRun | None:
    query = db.query(TrendSnapshotRun).filter(
        TrendSnapshotRun.region == region,
        TrendSnapshotRun.snapshot_kind == YOUTUBE_CATEGORY_SNAPSHOT_KIND,
        TrendSnapshotRun.status.in_(("completed", "partial", "failed")),
    )
    if before_run_id is not None:
        query = query.filter(TrendSnapshotRun.run_id < before_run_id)
    runs = query.order_by(TrendSnapshotRun.run_id.desc()).limit(120).all()
    if category_id is None:
        return runs[0] if runs else None
    for run in runs:
        details = _youtube_category_results_for_run(run).get(category_id, {})
        state = str(details.get("status") or "error")
        if not require_success or state in {"ok", "empty"}:
            return run
    return None


def _youtube_category_rows(
    db: Session,
    *,
    run_id: int,
    category_id: str,
    limit: int,
) -> List[TrendSnapshotItem]:
    return (
        db.query(TrendSnapshotItem)
        .filter(
            TrendSnapshotItem.run_id == run_id,
            TrendSnapshotItem.platform == "youtube",
            TrendSnapshotItem.ranking_scope
            == _youtube_category_scope(category_id),
            TrendSnapshotItem.category_id == category_id,
        )
        .order_by(
            TrendSnapshotItem.provider_rank,
            TrendSnapshotItem.item_id,
        )
        .limit(limit)
        .all()
    )


def _serialize_category_trend_items(
    current_rows: Sequence[TrendSnapshotItem],
    *,
    current_run: TrendSnapshotRun,
    previous_rows: Sequence[TrendSnapshotItem],
    previous_run: TrendSnapshotRun | None,
) -> List[Dict[str, object]]:
    previous_by_key = {row.trend_key: row for row in previous_rows}
    previous_ranks = {
        row.trend_key: row.provider_rank or index
        for index, row in enumerate(previous_rows, start=1)
    }
    current_timestamp = current_run.completed_at or current_run.started_at
    previous_timestamp = (
        previous_run.completed_at or previous_run.started_at
        if previous_run is not None
        else None
    )
    comparison_seconds = (
        max(1.0, (current_timestamp - previous_timestamp).total_seconds())
        if previous_timestamp is not None
        else 0.0
    )
    comparison_minutes = comparison_seconds / 60.0 if comparison_seconds else 0.0
    hot_count = max(1, (len(current_rows) + 9) // 10) if current_rows else 0
    items: List[Dict[str, object]] = []
    for index, row in enumerate(current_rows, start=1):
        rank = row.provider_rank or index
        previous_row = previous_by_key.get(row.trend_key)
        previous_rank = previous_ranks.get(row.trend_key)
        rank_change = previous_rank - rank if previous_rank is not None else 0
        metric_comparable = (
            previous_row is not None
            and view_metrics_are_comparable(
                "youtube",
                row.view_metric_version,
                previous_row.view_metric_version,
            )
        )
        metric_version_changed = previous_row is not None and not metric_comparable
        previous_signal = (
            float(previous_row.engagement_signal or 0.0)
            if metric_comparable
            else None
        )
        current_signal = float(row.engagement_signal or 0.0)
        delta = current_signal - previous_signal if previous_signal is not None else 0.0
        percent = (
            (delta / previous_signal) * 100.0
            if previous_signal is not None and previous_signal > 0
            else 0.0
        )
        rate = delta / comparison_minutes if comparison_minutes > 0 else 0.0
        is_new = previous_run is not None and previous_row is None
        if previous_run is None:
            change_kind = "baseline"
            change_label = "Baseline"
        elif is_new:
            change_kind = "new"
            change_label = "New"
        elif rank_change > 0:
            change_kind = "rank_up"
            change_label = f"Up {rank_change} rank{'s' if rank_change != 1 else ''}"
        elif rank_change < 0:
            moved = abs(rank_change)
            change_kind = "rank_down"
            change_label = f"Down {moved} rank{'s' if moved != 1 else ''}"
        else:
            change_kind = "none"
            change_label = "No change"

        items.append(
            {
                "key": row.trend_key,
                "platform": row.platform,
                "title": row.title,
                "category": row.category,
                "category_id": row.category_id,
                "ranking_scope": row.ranking_scope,
                "source_platform": row.source_platform,
                "video_url": row.video_url or "",
                "channel_title": row.channel_title or "",
                "thumbnail_url": row.thumbnail_url or "",
                "description": row.description or "",
                "duration_seconds": row.duration_seconds,
                "views": row.views,
                "likes": row.likes,
                "comments": row.comments,
                "views_available": row.views_available,
                "likes_available": row.likes_available,
                "comments_available": row.comments_available,
                "search_volume": row.search_volume,
                "trend_score": row.trend_score,
                "engagement_signal": row.engagement_signal,
                "view_metric_version": row.view_metric_version,
                "metric_version_changed": metric_version_changed,
                "engagement_change_percent": round(percent, 2),
                "engagement_delta": round(delta, 2),
                "engagement_rate_per_minute": round(rate, 2),
                "rank": rank,
                "rank_change": rank_change,
                "momentum_score": 0.0,
                "change_kind": change_kind,
                "change_label": change_label,
                "has_previous_snapshot": previous_run is not None,
                "comparison_window_seconds": int(round(comparison_seconds)),
                "is_meaningful_rising": rank_change > 0,
                "status": "Hot" if rank <= hot_count else "Stable",
                "is_new": is_new,
                "published_at": row.published_at,
            }
        )
    return items


def load_youtube_category_snapshot(
    db: Session,
    *,
    region: str,
    category_id: str | None,
    limit: int,
) -> Dict[str, object]:
    region = region.upper()
    limit = min(50, max(1, int(limit)))
    configured_ids = list(settings.youtube_trend_category_ids)[:12]
    recent_runs = (
        db.query(TrendSnapshotRun)
        .filter(
            TrendSnapshotRun.region == region,
            TrendSnapshotRun.snapshot_kind == YOUTUBE_CATEGORY_SNAPSHOT_KIND,
            TrendSnapshotRun.status.in_(("completed", "partial", "failed")),
        )
        .order_by(TrendSnapshotRun.run_id.desc())
        .limit(settings.live_trend_snapshot_retention_runs)
        .all()
    )
    latest = recent_runs[0] if recent_runs else None
    latest_results = (
        _youtube_category_results_for_run(latest) if latest is not None else {}
    )
    successful_runs: Dict[str, TrendSnapshotRun] = {}
    successful_results: Dict[str, Dict[str, object]] = {}
    for run in recent_runs:
        for configured_id, details in _youtube_category_results_for_run(run).items():
            if configured_id in successful_runs:
                continue
            if str(details.get("status") or "error") not in {"ok", "empty"}:
                continue
            successful_runs[configured_id] = run
            successful_results[configured_id] = details

    categories = []
    for configured_id in configured_ids:
        details = successful_results.get(
            configured_id,
            latest_results.get(configured_id, {}),
        )
        category_run = successful_runs.get(configured_id)
        categories.append(
            {
                "category_id": configured_id,
                "title": str(
                    details.get("title")
                    or YOUTUBE_CATEGORY_TITLES.get(configured_id)
                    or configured_id
                ),
                "total": int(details.get("total") or 0),
                "provider_status": str(details.get("status") or "pending"),
                "error": details.get("error"),
                "last_checked_at": utc_isoformat(
                    (category_run.completed_at or category_run.started_at)
                    if category_run is not None
                    else None
                ),
            }
        )

    response: Dict[str, object] = {
        "run_id": latest.run_id if latest is not None else None,
        "snapshot_status": latest.status if latest is not None else "pending",
        "generated_at": utc_isoformat(
            (latest.completed_at or latest.started_at) if latest is not None else None
        ),
        "region": region,
        "refresh_interval_seconds": _category_refresh_interval(db),
        "categories": categories,
        "selected_category": None,
    }
    if category_id is None:
        return response
    if category_id not in configured_ids:
        raise ValueError(f"YouTube category {category_id} is not configured")

    current_run = successful_runs.get(category_id)
    summary = next(
        item for item in categories if item["category_id"] == category_id
    )
    if current_run is None:
        response["selected_category"] = {
            **summary,
            "ranking_scope": _youtube_category_scope(category_id),
            "items": [],
            "has_previous_snapshot": False,
        }
        return response

    current_rows = _youtube_category_rows(
        db,
        run_id=current_run.run_id,
        category_id=category_id,
        limit=limit,
    )
    previous_run = _latest_youtube_category_run(
        db,
        region=region,
        category_id=category_id,
        before_run_id=current_run.run_id,
        require_success=True,
    )
    previous_rows = (
        _youtube_category_rows(
            db,
            run_id=previous_run.run_id,
            category_id=category_id,
            limit=50,
        )
        if previous_run is not None
        else []
    )
    items = _serialize_category_trend_items(
        current_rows,
        current_run=current_run,
        previous_rows=previous_rows,
        previous_run=previous_run,
    )
    current_details = successful_results.get(category_id, {})
    response.update(
        {
            "run_id": current_run.run_id,
            "snapshot_status": current_run.status,
            "generated_at": utc_isoformat(
                current_run.completed_at or current_run.started_at
            ),
            "selected_category": {
                **summary,
                "title": str(
                    current_details.get("title")
                    or summary["title"]
                ),
                "total": len(items),
                "provider_status": str(
                    current_details.get("status") or "ok"
                ),
                "ranking_scope": _youtube_category_scope(category_id),
                "items": items,
                "has_previous_snapshot": previous_run is not None,
            },
        }
    )
    return response


def load_trend_item_detail(
    db: Session,
    *,
    region: str,
    trend_key: str,
    platform: str,
    ranking_scope: str,
    category_id: str | None,
    history_limit: int = 12,
) -> Dict[str, object]:
    """Load one ranked item and its retained snapshot history without provider calls."""
    platform = platform.strip().lower()
    if platform not in PLATFORMS:
        raise ValueError(f"Unsupported trend platform: {platform}")
    ranking_scope = ranking_scope.strip() or GLOBAL_RANKING_SCOPE
    history_limit = min(24, max(1, int(history_limit)))

    query = (
        db.query(TrendSnapshotItem, TrendSnapshotRun)
        .join(
            TrendSnapshotRun,
            TrendSnapshotItem.run_id == TrendSnapshotRun.run_id,
        )
        .filter(
            TrendSnapshotRun.region == region.upper(),
            TrendSnapshotRun.status.in_(("completed", "partial")),
            TrendSnapshotItem.platform == platform,
            TrendSnapshotItem.ranking_scope == ranking_scope,
            TrendSnapshotItem.trend_key == trend_key,
        )
    )
    if category_id:
        query = query.filter(TrendSnapshotItem.category_id == category_id)

    records = (
        query.order_by(TrendSnapshotRun.run_id.desc())
        .limit(history_limit)
        .all()
    )
    if not records:
        raise LookupError("Trend item was not found in retained snapshots")

    current_row, current_run = records[0]
    history = [
        {
            "run_id": run.run_id,
            "rank": row.provider_rank,
            "captured_at": utc_isoformat(run.completed_at or run.started_at),
            "views": row.views,
            "likes": row.likes,
            "comments": row.comments,
            "views_available": row.views_available,
            "likes_available": row.likes_available,
            "comments_available": row.comments_available,
            "view_metric_version": row.view_metric_version,
        }
        for row, run in records
    ]
    return {
        "trend_key": current_row.trend_key,
        "platform": current_row.platform,
        "ranking_scope": current_row.ranking_scope,
        "category_id": current_row.category_id,
        "captured_at": utc_isoformat(
            current_run.completed_at or current_run.started_at
        ),
        "first_seen_in_history_at": history[-1]["captured_at"],
        "history_limit": history_limit,
        "item": {
            "key": current_row.trend_key,
            "platform": current_row.platform,
            "title": current_row.title,
            "category": current_row.category,
            "category_id": current_row.category_id,
            "ranking_scope": current_row.ranking_scope,
            "source_platform": current_row.source_platform,
            "video_url": current_row.video_url or "",
            "channel_title": current_row.channel_title or "",
            "thumbnail_url": current_row.thumbnail_url or "",
            "description": current_row.description or "",
            "duration_seconds": current_row.duration_seconds,
            "views": current_row.views,
            "likes": current_row.likes,
            "comments": current_row.comments,
            "views_available": current_row.views_available,
            "likes_available": current_row.likes_available,
            "comments_available": current_row.comments_available,
            "search_volume": current_row.search_volume,
            "trend_score": current_row.trend_score,
            "engagement_signal": current_row.engagement_signal,
            "view_metric_version": current_row.view_metric_version,
            "rank": current_row.provider_rank,
            "published_at": current_row.published_at,
        },
        "history": history,
    }


def load_latest_live_snapshot(
    db: Session,
    *,
    region: str,
    limit: int,
) -> Dict[str, object]:
    region = region.upper()
    recent_runs = (
        db.query(TrendSnapshotRun)
        .filter(
            TrendSnapshotRun.region == region,
            TrendSnapshotRun.snapshot_kind == GLOBAL_SNAPSHOT_KIND,
            TrendSnapshotRun.status.in_(("completed", "partial", "failed")),
        )
        .order_by(TrendSnapshotRun.run_id.desc())
        .limit(settings.live_trend_snapshot_retention_runs)
        .all()
    )
    if not recent_runs:
        return {
            "run_id": None,
            "latest_attempt_run_id": None,
            "snapshot_status": "pending",
            "generated_at": None,
            "region": region,
            "platforms": {
                platform: {
                    "mode": "pending",
                    "provider_status": "pending",
                    "total": 0,
                    "items": [],
                    "new_items": [],
                    "error": "Waiting for the first background live-trend snapshot",
                }
                for platform in PLATFORMS
            },
        }

    latest_attempt = recent_runs[0]
    latest_attempt_status = _provider_status_for_run(latest_attempt)
    data_runs: Dict[str, TrendSnapshotRun] = {}
    data_statuses: Dict[str, Dict[str, object]] = {}
    for run in recent_runs:
        statuses = _provider_status_for_run(run)
        for platform in PLATFORMS:
            if platform in data_runs:
                continue
            details = statuses.get(platform, {})
            if str(details.get("status") or "error") in {"ok", "empty"}:
                data_runs[platform] = run
                data_statuses[platform] = details

    newest_data_run = max(
        data_runs.values(),
        key=lambda run: run.run_id,
        default=latest_attempt,
    )
    platforms_payload: Dict[str, Dict[str, object]] = {}
    for platform in PLATFORMS:
        data_run = data_runs.get(platform)
        details = data_statuses.get(
            platform,
            latest_attempt_status.get(platform, {}),
        )
        provider_state = str(details.get("status") or "error")
        rows = []
        if data_run is not None:
            rows = (
                db.query(TrendSnapshotItem)
                .filter(
                    TrendSnapshotItem.run_id == data_run.run_id,
                    TrendSnapshotItem.platform == platform,
                    TrendSnapshotItem.ranking_scope == GLOBAL_RANKING_SCOPE,
                )
                .order_by(
                    TrendSnapshotItem.provider_rank,
                    TrendSnapshotItem.item_id,
                )
                .limit(limit)
                .all()
            )

        items: List[Dict[str, object]] = []
        for index, row in enumerate(rows, start=1):
            items.append(
                {
                    "key": row.trend_key,
                    "platform": row.platform,
                    "title": row.title,
                    "category": row.category,
                    "category_id": row.category_id,
                    "ranking_scope": row.ranking_scope,
                    "source_platform": row.source_platform,
                    "video_url": row.video_url or "",
                    "channel_title": row.channel_title or "",
                    "thumbnail_url": row.thumbnail_url or "",
                    "description": row.description or "",
                    "duration_seconds": row.duration_seconds,
                    "views": row.views,
                    "likes": row.likes,
                    "comments": row.comments,
                    "views_available": row.views_available,
                    "likes_available": row.likes_available,
                    "comments_available": row.comments_available,
                    "search_volume": row.search_volume,
                    "trend_score": row.trend_score,
                    "engagement_signal": row.engagement_signal,
                    "view_metric_version": row.view_metric_version,
                    "metric_version_changed": False,
                    "engagement_change_percent": 0.0,
                    "engagement_delta": 0.0,
                    "engagement_rate_per_minute": 0.0,
                    "rank": row.provider_rank or index,
                    "rank_change": 0,
                    "momentum_score": 0.0,
                    "change_kind": "baseline",
                    "change_label": "Baseline",
                    "has_previous_snapshot": False,
                    "comparison_window_seconds": 0,
                    "is_meaningful_rising": False,
                    "status": "Stable",
                    "is_new": False,
                    "published_at": row.published_at,
                }
            )

        data_timestamp = (
            data_run.completed_at or data_run.started_at
            if data_run is not None
            else latest_attempt.completed_at or latest_attempt.started_at
        )
        is_stale = data_run is not None and data_run.run_id != latest_attempt.run_id
        latest_error = latest_attempt_status.get(platform, {}).get("error")
        platforms_payload[platform] = {
            "mode": (
                "live_stale"
                if is_stale
                else "live"
                if provider_state in {"ok", "empty"}
                else "live_error"
            ),
            "provider_status": provider_state,
            "total": len(items),
            "items": items,
            "new_items": [],
            "error": latest_error if is_stale else details.get("error"),
            "last_checked_at": utc_isoformat(data_timestamp),
            "data_run_id": data_run.run_id if data_run is not None else None,
            "is_stale": is_stale,
        }

    generated_at = newest_data_run.completed_at or newest_data_run.started_at
    return {
        "run_id": newest_data_run.run_id,
        "latest_attempt_run_id": latest_attempt.run_id,
        "snapshot_status": newest_data_run.status,
        "generated_at": utc_isoformat(generated_at),
        "region": newest_data_run.region,
        "platforms": platforms_payload,
    }


def get_live_provider_health(db: Session, *, region: str) -> Dict[str, object]:
    snapshot = load_latest_live_snapshot(db, region=region, limit=1)
    providers = {
        platform: {
            "status": details.get("provider_status", "pending"),
            "mode": details.get("mode", "pending"),
            "last_checked_at": details.get("last_checked_at"),
            "error": details.get("error"),
        }
        for platform, details in snapshot["platforms"].items()
    }
    return {
        "run_id": snapshot.get("run_id"),
        "snapshot_status": snapshot.get("snapshot_status"),
        "generated_at": snapshot.get("generated_at"),
        "providers": providers,
    }
