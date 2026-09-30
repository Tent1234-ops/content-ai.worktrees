from typing import List, Optional

from pydantic import BaseModel

from app.schemas.trends import GoogleTrendItem, TikTokTrendItem, YouTubeTrendItem


class DashboardMetricSummary(BaseModel):
    total_users: int
    active_users: int
    total_user_contents: int
    total_analysis_results: int
    total_clusters: int
    total_cluster_runs: int
    total_cluster_memberships: int
    total_dataset_contents: int
    total_system_logs: int
    my_contents: int
    my_analysis_results: int


class CategoryDistributionItem(BaseModel):
    category: str
    count: int


class ClusterDistributionItem(BaseModel):
    cluster_name: str
    count: int


class DashboardYouTubeTrends(BaseModel):
    mode: str
    region: str
    total: int
    items: List[YouTubeTrendItem]


class DashboardGoogleTrends(BaseModel):
    mode: str
    region: str
    total: int
    items: List[GoogleTrendItem]


class DashboardTikTokTrends(BaseModel):
    mode: str
    region: str
    total: int
    items: List[TikTokTrendItem]


class DashboardRefreshResponse(BaseModel):
    job_id: str
    status: str
    rate_limited: bool = False
    next_allowed_at: Optional[str] = None


class DashboardTopTrendItem(BaseModel):
    dataset_id: int
    title: str
    category: Optional[str] = None
    source_platform: str
    video_url: Optional[str] = None
    views: int
    likes: int
    comments: int
    trend_score: float
    published_at: Optional[str] = None


class DashboardKeywordItem(BaseModel):
    keyword: str
    count: int


class DashboardSourceItem(BaseModel):
    source_platform: str
    count: int


class DashboardPlatformSummary(BaseModel):
    source: str
    dataset_count: int
    profile_count: int
    domains: List[str]


class DashboardPlatformComparisonItem(BaseModel):
    domain: str
    youtube_sample_size: int
    google_sample_size: int
    youtube_duration: str
    google_duration: str


class DashboardTopicItem(BaseModel):
    keyword: str
    score: float


class DashboardPriorityItem(BaseModel):
    title: str
    category: Optional[str] = None
    source_platform: Optional[str] = None
    video_url: Optional[str] = None
    trend_score: float
    priority_score: float
    novelty_score: float
    views: int
    likes: int
    comments: int
    published_at: Optional[str] = None


class DashboardEmergingTopicsResponse(BaseModel):
    priority_items: List[DashboardPriorityItem]
    emerging_topics: List[DashboardTopicItem]
    youtube_trends: DashboardYouTubeTrends
    google_trends: DashboardGoogleTrends
    tiktok_trends: DashboardTikTokTrends


class DashboardOverviewResponse(BaseModel):
    db_status: str
    db_error: Optional[str] = None
    user_role: str
    metrics: DashboardMetricSummary
    category_distribution: List[CategoryDistributionItem]
    cluster_distribution: List[ClusterDistributionItem]
    top_trends: List[DashboardTopTrendItem]
    top_categories: List[CategoryDistributionItem]
    top_keywords: List[DashboardKeywordItem]
    source_distribution: List[DashboardSourceItem]
    platform_summaries: List[DashboardPlatformSummary]
    platform_comparison: List[DashboardPlatformComparisonItem]
    priority_topics: List[DashboardTopicItem]
    emerging_topics: List[DashboardTopicItem]
    priority_items: List[DashboardPriorityItem]
    youtube_trends: DashboardYouTubeTrends
    google_trends: DashboardGoogleTrends
    tiktok_trends: DashboardTikTokTrends
