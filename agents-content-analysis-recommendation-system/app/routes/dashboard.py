from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_watch_session
from app.core.config import settings
from app.database.db import get_db
from app.database.models import User, UserContent, UserTrendWatchSession
from app.schemas.dashboard import (
    DashboardEmergingTopicsResponse,
    DashboardOverviewResponse,
    DashboardRefreshResponse,
)
from app.schemas.notifications import NotificationItem
from app.services.dashboard import build_dashboard_overview, build_dashboard_topic_insights
from app.services.live_trend_notifications import (
    compare_live_trend_snapshot,
    load_public_trend_snapshot,
)
from app.services.live_trend_snapshots import (
    load_trend_item_detail,
    load_youtube_category_snapshot,
)
from app.services.trending_fetcher import RateLimitedError, trigger_trending_refresh
from app.services.trend_history import load_trend_history

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/public/history")
def public_trend_history(
    platform: str = Query(pattern="^(youtube|google)$"),
    region: str = Query(default=settings.youtube_region, pattern="^[a-zA-Z]{2}$"),
    days: int = Query(default=5, ge=1, le=90),
    video_category_id: str | None = Query(default=None, pattern=r"^\d{1,3}$"),
    item_key: str | None = Query(default=None, pattern=r"^[0-9a-f]{40}$"),
    db: Session = Depends(get_db),
):
    try:
        return load_trend_history(db, region=region.upper(), platform=platform,
                                  days=days, category_id=video_category_id, item_key=item_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/public/trends")
def public_dashboard_trends(
    region: str = Query(default=settings.youtube_region, min_length=2, max_length=2),
    trend_limit: int = Query(default=50, ge=1, le=50),
    db: Session = Depends(get_db),
):
    return load_public_trend_snapshot(db, region=region.upper(), limit=trend_limit)


@router.get("/public/youtube/categories")
def public_youtube_category_snapshots(
    region: str = Query(default=settings.youtube_region, min_length=2, max_length=2),
    video_category_id: str | None = Query(default=None, max_length=32),
    trend_limit: int = Query(default=50, ge=1, le=50),
    db: Session = Depends(get_db),
):
    try:
        return load_youtube_category_snapshot(
            db, region=region.upper(), category_id=video_category_id, limit=trend_limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/overview", response_model=DashboardOverviewResponse)
def dashboard_overview(
    region: str = Query(default=settings.youtube_region, min_length=2, max_length=2),
    trend_mode: str = Query(default="live", pattern="^(auto|mock|live)$"),
    trend_limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return DashboardOverviewResponse.model_validate(
        build_dashboard_overview(
            db=db,
            current_user=current_user,
            region=region.upper(),
            trend_mode=trend_mode,
            trend_limit=trend_limit,
        )
    )


@router.get("/summary")
def dashboard_summary(
    region: str = Query(default=settings.youtube_region, min_length=2, max_length=2),
    trend_mode: str = Query(default="live", pattern="^(auto|mock|live)$"),
    trend_limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lightweight live dashboard summary for frontend cards."""
    from app.services.simple_cache import get as cache_get, set as cache_set

    effective_mode = "live" if trend_mode == "live" else trend_mode

    cache_key = f"dashboard_summary:{current_user.user_id}:{region}:{effective_mode}:{trend_limit}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    # Build a lightweight summary for dashboard cards so the dashboard does not wait on heavy dataset profiling.
    from app.services.dashboard import build_dashboard_summary

    summary = build_dashboard_summary(
        db=db,
        current_user=current_user,
        region=region.upper(),
        trend_mode=effective_mode,
        trend_limit=trend_limit,
    )

    # Compatibility field only. Platform rankings are returned separately below.
    top_trends = summary.get("top_trends", [])

    # Recent analyses: latest 3 UserContent entries for user
    recent_analyses = []
    try:
        rows = (
            db.query(UserContent)
            .filter(UserContent.user_id == current_user.user_id)
            .order_by(UserContent.created_at.desc())
            .limit(3)
            .all()
        )
        for r in rows:
            recent_analyses.append({
                "content_id": r.content_id,
                "title": r.title,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "video_url": r.video_url,
            })
    except Exception:
        recent_analyses = []

    quick_recommendations = summary.get("quick_recommendations", [])
    recommended_duration = summary.get("recommended_duration")

    result = {
        "top_trends": top_trends,
        "quick_recommendations": quick_recommendations,
        "recommended_duration": recommended_duration,
        "recent_analyses": recent_analyses,
        # include a minimal set of overview fields to avoid front-end breaking
        "metrics": summary.get("metrics", {}),
        "platform_summaries": summary.get("platform_summaries", []),
        "source_distribution": summary.get("source_distribution", []),
        "youtube_trends": summary.get("youtube_trends", {}),
        "google_trends": summary.get("google_trends", {}),
        "tiktok_trends": summary.get("tiktok_trends", {}),
        "generated_at": datetime.utcnow().isoformat(),
    }

    # Cache for 60 seconds
    cache_set(cache_key, result, ttl_seconds=60)
    return result


@router.get("/live-trends/snapshot")
def dashboard_live_trends_snapshot(
    region: str = Query(default=settings.youtube_region, min_length=2, max_length=2),
    trend_limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    watch_session: UserTrendWatchSession = Depends(get_current_watch_session),
    db: Session = Depends(get_db),
):
    result = compare_live_trend_snapshot(
        db=db,
        user=current_user,
        watch_session=watch_session,
        region=region.upper(),
        limit=trend_limit,
    )
    return {
        **result,
        "new_notifications": [
            NotificationItem.model_validate(item).model_dump(mode="json")
            for item in result.get("new_notifications", [])
        ],
    }


@router.get("/live-trends/youtube/categories")
def dashboard_youtube_category_snapshots(
    region: str = Query(default=settings.youtube_region, min_length=2, max_length=2),
    video_category_id: str | None = Query(default=None, max_length=32),
    trend_limit: int = Query(default=50, ge=1, le=50),
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return load_youtube_category_snapshot(
            db,
            region=region.upper(),
            category_id=video_category_id,
            limit=trend_limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/live-trends/items/{trend_key}")
def dashboard_live_trend_item_detail(
    trend_key: str = Path(pattern=r"^[0-9a-f]{40}$"),
    platform: str = Query(pattern="^(youtube|google|tiktok)$"),
    ranking_scope: str = Query(default="global", min_length=1, max_length=64),
    category_id: str | None = Query(default=None, max_length=32),
    history_limit: int = Query(default=12, ge=1, le=24),
    region: str = Query(default=settings.youtube_region, min_length=2, max_length=2),
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return load_trend_item_detail(
            db,
            region=region.upper(),
            trend_key=trend_key,
            platform=platform,
            ranking_scope=ranking_scope,
            category_id=category_id,
            history_limit=history_limit,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/refresh", response_model=DashboardRefreshResponse)
def dashboard_refresh(
    current_user: User = Depends(get_current_user),
):
    from app.services.simple_cache import invalidate_prefix as cache_invalidate_prefix
    try:
        result = trigger_trending_refresh(user_id=current_user.user_id)
        cache_invalidate_prefix(f"dashboard_summary:{current_user.user_id}:")
        return result
    except RateLimitedError as exc:
        raise HTTPException(status_code=429, detail=str(exc))


@router.get("/emerging-topics", response_model=DashboardEmergingTopicsResponse)
def dashboard_emerging_topics(
    region: str = Query(default=settings.youtube_region, min_length=2, max_length=2),
    trend_mode: str = Query(default="live", pattern="^(auto|mock|live)$"),
    trend_limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return DashboardEmergingTopicsResponse.model_validate(
        build_dashboard_topic_insights(
            db=db,
            current_user=current_user,
            region=region.upper(),
            trend_mode=trend_mode,
            trend_limit=trend_limit,
        )
    )
