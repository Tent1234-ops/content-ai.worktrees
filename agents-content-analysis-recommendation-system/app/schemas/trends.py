from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


TrendMode = Literal["auto", "mock", "live"]


class YouTubeTrendItem(BaseModel):
    title: str
    channel_title: str
    description: Optional[str] = None
    category: Optional[str] = None
    published_at: Optional[datetime] = None
    video_url: str
    thumbnail_url: Optional[str] = None
    views: int = 0
    likes: int = 0
    comments: int = 0
    views_available: bool = True
    likes_available: bool = True
    comments_available: bool = True
    trend_score: float = 0.0
    duration_seconds: Optional[int] = None
    source: str = "youtube"


class YouTubeTrendingResponse(BaseModel):
    mode: str
    region: str
    total: int
    items: list[YouTubeTrendItem]


class YouTubeCategoryItem(BaseModel):
    category_id: str
    title: str
    assignable: bool = True


class YouTubeCategoriesResponse(BaseModel):
    mode: str
    region: str
    total: int
    items: list[YouTubeCategoryItem]


class GoogleTrendItem(BaseModel):
    title: str
    query: Optional[str] = None
    category: Optional[str] = None
    published_at: Optional[datetime] = None
    video_url: str
    thumbnail_url: Optional[str] = None
    views: int = 0
    likes: int = 0
    comments: int = 0
    views_available: bool = False
    likes_available: bool = False
    comments_available: bool = False
    trend_score: float = 0.0
    search_volume: Optional[int] = None
    duration_seconds: Optional[int] = None
    source: str = "google_trends"
    traffic_text: Optional[str] = None


class GoogleTrendingResponse(BaseModel):
    mode: str
    region: str
    total: int
    items: list[GoogleTrendItem]


class TikTokTrendItem(BaseModel):
    title: str
    creator: Optional[str] = None
    category: Optional[str] = None
    published_at: Optional[datetime] = None
    video_url: str
    thumbnail_url: Optional[str] = None
    views: int = 0
    likes: int = 0
    comments: int = 0
    views_available: bool = True
    likes_available: bool = True
    comments_available: bool = True
    trend_score: float = 0.0
    duration_seconds: Optional[int] = None
    source: str = "tiktok"


class TikTokTrendingResponse(BaseModel):
    mode: str
    region: str
    total: int
    items: list[TikTokTrendItem]
