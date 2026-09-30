from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class AdminConfigBase(BaseModel):
    """Base configuration model for admin settings"""
    max_keywords_display: int = Field(
        default=10, 
        ge=1, 
        le=50,
        description="Maximum number of keywords to display in recommendations"
    )
    hook_analysis_duration: int = Field(
        default=60,
        ge=10,
        le=300,
        description="Duration in seconds for hook keyword analysis (first N seconds of video)"
    )
    analysis_time_range_days: int = Field(
        default=90,
        ge=1,
        le=365,
        description="Number of days to consider for trend analysis"
    )
    notification_batch_size: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of notifications to send in one batch"
    )
    youtube_region: str = Field(
        default="TH",
        min_length=2,
        max_length=2,
        description="YouTube trending region code (e.g., TH, US, GB)"
    )
    google_region: str = Field(
        default="TH",
        min_length=2,
        max_length=2,
        description="Google Trends region code (e.g., TH, US, GB)"
    )
    tiktok_region: str = Field(
        default="TH",
        min_length=2,
        max_length=2,
        description="TikTok trend region code (e.g., TH, US, GB)"
    )
    enable_youtube_trending: bool = Field(
        default=True,
        description="Enable YouTube trending data collection"
    )
    enable_google_trends: bool = Field(
        default=True,
        description="Enable Google Trends data collection"
    )
    enable_tiktok_trending: bool = Field(
        default=True,
        description="Enable TikTok trending data collection"
    )
    auto_scan_interval_hours: int = Field(
        default=6,
        ge=1,
        le=24,
        description="Interval in hours to automatically scan for trends"
    )


class AdminConfigCreate(AdminConfigBase):
    """Request model for creating admin configuration"""
    pass


class AdminConfigUpdate(AdminConfigBase):
    """Request model for updating admin configuration"""
    # All fields from base, inherited as optional updates
    max_keywords_display: Optional[int] = None
    hook_analysis_duration: Optional[int] = None
    analysis_time_range_days: Optional[int] = None
    notification_batch_size: Optional[int] = None
    youtube_region: Optional[str] = None
    google_region: Optional[str] = None
    tiktok_region: Optional[str] = None
    enable_youtube_trending: Optional[bool] = None
    enable_google_trends: Optional[bool] = None
    enable_tiktok_trending: Optional[bool] = None
    auto_scan_interval_hours: Optional[int] = None


class AdminConfigResponse(BaseModel):
    """Response model for admin configuration"""
    config_id: int
    max_keywords_display: int
    hook_analysis_duration: int
    analysis_time_range_days: int
    notification_batch_size: int
    youtube_region: str
    google_region: str
    tiktok_region: str
    enable_youtube_trending: bool
    enable_google_trends: bool
    enable_tiktok_trending: bool
    auto_scan_interval_hours: int
    created_at: datetime
    updated_at: datetime = None

    class Config:
        from_attributes = True


class AdminConfigValidationResponse(BaseModel):
    """Response after config validation"""
    is_valid: bool
    message: str
    config: Optional[AdminConfigResponse] = None


class AdminStatisticsResponse(BaseModel):
    """Admin panel statistics"""
    total_users: int
    active_users: int
    total_analyses: int
    total_saved_ideas: int
    analyses_by_category: dict
    most_used_categories: list
    avg_analyses_per_user: float
    trend_data_sources_active: list
    last_trend_scan: Optional[datetime] = None
    last_config_update: Optional[datetime] = None


class BulkConfigResetResponse(BaseModel):
    """Response for bulk config reset"""
    reset_count: int
    message: str
    timestamp: datetime
