from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.config import settings
from app.database.db import get_db
from app.database.models import User
from app.schemas.persistence import TrendSyncResponse
from app.schemas.trends import (
    GoogleTrendingResponse,
    TikTokTrendingResponse,
    YouTubeCategoriesResponse,
    YouTubeTrendingResponse,
)
from app.services.trends import get_google_trending, get_tiktok_trending, get_youtube_categories, get_youtube_trending
from app.services.persistence import save_google_trends, save_tiktok_trends, save_youtube_trends
from app.services.simple_cache import invalidate_prefix as cache_invalidate_prefix

router = APIRouter(prefix="/trends", tags=["trends"])


@router.get("/youtube", response_model=YouTubeTrendingResponse)
def youtube_trending(
    limit: int = Query(default=10, ge=1, le=50),
    region: str = Query(default=settings.youtube_region, min_length=2, max_length=2),
    mode: str = Query(default="auto", pattern="^(auto|mock|live)$"),
    video_category_id: str | None = Query(default=None),
    _current_user: User = Depends(require_roles("admin", "user")),
):
    resolved_mode, items = get_youtube_trending(
        region=region.upper(),
        limit=limit,
        mode=mode,
        video_category_id=video_category_id,
    )
    return YouTubeTrendingResponse(
        mode=resolved_mode,
        region=region.upper(),
        total=len(items),
        items=items,
    )


@router.get("/youtube/categories", response_model=YouTubeCategoriesResponse)
def youtube_categories(
    region: str = Query(default=settings.youtube_region, min_length=2, max_length=2),
    mode: str = Query(default="auto", pattern="^(auto|mock|live)$"),
    _current_user: User = Depends(require_roles("admin", "user")),
):
    resolved_mode, items = get_youtube_categories(region=region.upper(), mode=mode)
    return YouTubeCategoriesResponse(
        mode=resolved_mode,
        region=region.upper(),
        total=len(items),
        items=items,
    )


@router.post("/youtube/sync", response_model=TrendSyncResponse)
def youtube_trending_sync(
    limit: int = Query(default=10, ge=1, le=50),
    region: str = Query(default=settings.youtube_region, min_length=2, max_length=2),
    mode: str = Query(default="auto", pattern="^(auto|mock|live)$"),
    video_category_id: str | None = Query(default=None),
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    resolved_mode, items = get_youtube_trending(
        region=region.upper(),
        limit=limit,
        mode=mode,
        video_category_id=video_category_id,
    )
    stats = save_youtube_trends(db=db, items=items, user_id=current_user.user_id, source_mode=resolved_mode)
    cache_invalidate_prefix("dashboard_summary:")
    return TrendSyncResponse(
        created=stats["created"],
        updated=stats["updated"],
        notifications=stats.get("notifications", 0),
        mode=resolved_mode,
        region=region.upper(),
        total_fetched=len(items),
    )


@router.get("/tiktok", response_model=TikTokTrendingResponse)
def tiktok_trending(
    limit: int = Query(default=10, ge=1, le=50),
    region: str = Query(default=settings.youtube_region, min_length=2, max_length=2),
    mode: str = Query(default="auto", pattern="^(auto|mock|live)$"),
    _current_user: User = Depends(require_roles("admin", "user")),
):
    resolved_mode, items = get_tiktok_trending(region=region.upper(), limit=limit, mode=mode)
    return TikTokTrendingResponse(
        mode=resolved_mode,
        region=region.upper(),
        total=len(items),
        items=items,
    )


@router.post("/tiktok/sync", response_model=TrendSyncResponse)
def tiktok_trending_sync(
    limit: int = Query(default=10, ge=1, le=50),
    region: str = Query(default=settings.youtube_region, min_length=2, max_length=2),
    mode: str = Query(default="auto", pattern="^(auto|mock|live)$"),
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    resolved_mode, items = get_tiktok_trending(region=region.upper(), limit=limit, mode=mode)
    stats = save_tiktok_trends(db=db, items=items, user_id=current_user.user_id, source_mode=resolved_mode)
    cache_invalidate_prefix("dashboard_summary:")
    return TrendSyncResponse(
        created=stats["created"],
        updated=stats["updated"],
        notifications=stats.get("notifications", 0),
        mode=resolved_mode,
        region=region.upper(),
        total_fetched=len(items),
    )


@router.get("/google", response_model=GoogleTrendingResponse)
def google_trending(
    limit: int = Query(default=10, ge=1, le=50),
    region: str = Query(default=settings.youtube_region, min_length=2, max_length=2),
    mode: str = Query(default="auto", pattern="^(auto|mock|live)$"),
    _current_user: User = Depends(require_roles("admin", "user")),
):
    resolved_mode, items = get_google_trending(region=region.upper(), limit=limit, mode=mode)
    return GoogleTrendingResponse(
        mode=resolved_mode,
        region=region.upper(),
        total=len(items),
        items=items,
    )


@router.post("/google/sync", response_model=TrendSyncResponse)
def google_trending_sync(
    limit: int = Query(default=10, ge=1, le=50),
    region: str = Query(default=settings.youtube_region, min_length=2, max_length=2),
    mode: str = Query(default="auto", pattern="^(auto|mock|live)$"),
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    resolved_mode, items = get_google_trending(region=region.upper(), limit=limit, mode=mode)
    stats = save_google_trends(db=db, items=items, user_id=current_user.user_id, source_mode=resolved_mode)
    cache_invalidate_prefix("dashboard_summary:")
    return TrendSyncResponse(
        created=stats["created"],
        updated=stats["updated"],
        notifications=stats.get("notifications", 0),
        mode=resolved_mode,
        region=region.upper(),
        total_fetched=len(items),
    )
