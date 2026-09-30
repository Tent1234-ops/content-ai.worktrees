from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class AdminDatasetItem(BaseModel):
    deleted_at: Optional[datetime] = None
    quality: dict = Field(default_factory=dict)
    dataset_id: int
    title: str
    video_url: Optional[str] = None
    transcript: Optional[str] = None
    category: Optional[str] = None
    source_platform: str
    dataset_source: str
    dataset_version: str
    collection_run_id: Optional[int] = None
    source_record_id: Optional[str] = None
    source_youtube_id: Optional[str] = None
    source_creator: Optional[str] = None
    source_channel_id: Optional[str] = None
    source_category: Optional[str] = None
    source_subcategory: Optional[str] = None
    collection_query: Optional[str] = None
    source_release_url: Optional[str] = None
    source_archive_sha256: Optional[str] = None
    source_annotation_path: Optional[str] = None
    source_annotation_sha256: Optional[str] = None
    import_batch_id: Optional[str] = None
    taxonomy_version: str
    taxonomy_leaf_key: Optional[str] = None
    category_level_1: Optional[str] = None
    category_level_2: Optional[str] = None
    category_level_3: Optional[str] = None
    language: str
    verification_status: str
    label_source: str
    license_name: str
    license_url: Optional[str] = None
    data_split: str
    split_strategy: Optional[str] = None
    creator_group_key: Optional[str] = None
    transcript_sha256: Optional[str] = None
    transcript_segment_count: int
    transcript_start_seconds: Optional[float] = None
    transcript_end_seconds: Optional[float] = None
    transcript_window_seconds: Optional[int] = None
    transcript_source: Optional[str] = None
    caption_type: Optional[str] = None
    transcript_quality: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None
    statistics_captured_at: Optional[datetime] = None
    view_metric_version: str
    license_verified_at: Optional[datetime] = None
    is_training_eligible: bool
    is_active: bool
    trend_score: float
    views: int
    likes: int
    comments: int
    duration_seconds: Optional[int] = None
    published_at: Optional[datetime] = None
    created_at: datetime


class AdminDatasetCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    video_url: Optional[str] = None
    transcript: Optional[str] = None
    category: Optional[str] = None
    source_platform: str = Field(default="youtube_admin", min_length=1, max_length=50)
    dataset_source: str = Field(default="admin", min_length=1, max_length=100)
    dataset_version: str = Field(default="manual-v1", min_length=1, max_length=100)
    source_record_id: Optional[str] = Field(default=None, max_length=255)
    source_youtube_id: Optional[str] = Field(default=None, max_length=32)
    source_creator: Optional[str] = Field(default=None, max_length=255)
    source_category: Optional[str] = Field(default=None, max_length=100)
    source_subcategory: Optional[str] = Field(default=None, max_length=100)
    source_release_url: Optional[str] = Field(default=None, max_length=1024)
    source_archive_sha256: Optional[str] = Field(default=None, min_length=64, max_length=64)
    source_annotation_path: Optional[str] = Field(default=None, max_length=1024)
    source_annotation_sha256: Optional[str] = Field(default=None, min_length=64, max_length=64)
    import_batch_id: Optional[str] = Field(default=None, min_length=64, max_length=64)
    taxonomy_version: str = Field(default="legacy-v1", min_length=1, max_length=50)
    taxonomy_leaf_key: Optional[str] = Field(default=None, max_length=100)
    category_level_1: Optional[str] = Field(default=None, max_length=150)
    category_level_2: Optional[str] = Field(default=None, max_length=150)
    category_level_3: Optional[str] = Field(default=None, max_length=150)
    language: str = Field(default="und", min_length=2, max_length=20)
    verification_status: Literal["unverified", "source_verified", "human_verified"] = "unverified"
    label_source: str = Field(default="admin", min_length=1, max_length=100)
    license_name: str = Field(default="unknown", min_length=1, max_length=100)
    license_url: Optional[str] = Field(default=None, max_length=1024)
    data_split: Literal["unassigned", "train", "validation", "test"] = "unassigned"
    split_strategy: Optional[str] = Field(default=None, max_length=100)
    creator_group_key: Optional[str] = Field(default=None, min_length=64, max_length=64)
    transcript_sha256: Optional[str] = Field(default=None, min_length=64, max_length=64)
    transcript_segment_count: int = Field(default=0, ge=0)
    transcript_start_seconds: Optional[float] = Field(default=None, ge=0)
    transcript_end_seconds: Optional[float] = Field(default=None, ge=0, le=300)
    transcript_window_seconds: Optional[int] = Field(default=None, ge=1, le=300)
    statistics_captured_at: Optional[datetime] = None
    view_metric_version: Optional[str] = Field(default=None, max_length=64)
    is_training_eligible: bool = False
    is_active: bool = True
    views: int = Field(default=0, ge=0)
    likes: int = Field(default=0, ge=0)
    comments: int = Field(default=0, ge=0)
    trend_score: float = Field(default=0.0, ge=0)
    duration_seconds: Optional[int] = Field(default=None, ge=0)
    published_at: Optional[datetime] = None


class AdminDatasetUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    video_url: Optional[str] = None
    transcript: Optional[str] = None
    category: Optional[str] = None
    source_platform: Optional[str] = Field(default=None, min_length=1, max_length=50)
    dataset_source: Optional[str] = Field(default=None, min_length=1, max_length=100)
    dataset_version: Optional[str] = Field(default=None, min_length=1, max_length=100)
    source_record_id: Optional[str] = Field(default=None, max_length=255)
    source_youtube_id: Optional[str] = Field(default=None, max_length=32)
    source_creator: Optional[str] = Field(default=None, max_length=255)
    source_category: Optional[str] = Field(default=None, max_length=100)
    source_subcategory: Optional[str] = Field(default=None, max_length=100)
    source_release_url: Optional[str] = Field(default=None, max_length=1024)
    source_archive_sha256: Optional[str] = Field(default=None, min_length=64, max_length=64)
    source_annotation_path: Optional[str] = Field(default=None, max_length=1024)
    source_annotation_sha256: Optional[str] = Field(default=None, min_length=64, max_length=64)
    import_batch_id: Optional[str] = Field(default=None, min_length=64, max_length=64)
    taxonomy_version: Optional[str] = Field(default=None, min_length=1, max_length=50)
    taxonomy_leaf_key: Optional[str] = Field(default=None, max_length=100)
    category_level_1: Optional[str] = Field(default=None, max_length=150)
    category_level_2: Optional[str] = Field(default=None, max_length=150)
    category_level_3: Optional[str] = Field(default=None, max_length=150)
    language: Optional[str] = Field(default=None, min_length=2, max_length=20)
    verification_status: Optional[Literal["unverified", "source_verified", "human_verified"]] = None
    label_source: Optional[str] = Field(default=None, min_length=1, max_length=100)
    license_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    license_url: Optional[str] = Field(default=None, max_length=1024)
    data_split: Optional[Literal["unassigned", "train", "validation", "test"]] = None
    split_strategy: Optional[str] = Field(default=None, max_length=100)
    creator_group_key: Optional[str] = Field(default=None, min_length=64, max_length=64)
    transcript_sha256: Optional[str] = Field(default=None, min_length=64, max_length=64)
    transcript_segment_count: Optional[int] = Field(default=None, ge=0)
    transcript_start_seconds: Optional[float] = Field(default=None, ge=0)
    transcript_end_seconds: Optional[float] = Field(default=None, ge=0, le=300)
    transcript_window_seconds: Optional[int] = Field(default=None, ge=1, le=300)
    statistics_captured_at: Optional[datetime] = None
    view_metric_version: Optional[str] = Field(default=None, max_length=64)
    is_training_eligible: Optional[bool] = None
    is_active: Optional[bool] = None
    views: Optional[int] = Field(default=None, ge=0)
    likes: Optional[int] = Field(default=None, ge=0)
    comments: Optional[int] = Field(default=None, ge=0)
    trend_score: Optional[float] = Field(default=None, ge=0)
    duration_seconds: Optional[int] = Field(default=None, ge=0)
    published_at: Optional[datetime] = None


class AdminDatasetListResponse(BaseModel):
    total: int
    items: list[AdminDatasetItem]


class AdminClusterRunItem(BaseModel):
    run_id: int
    algorithm: str
    n_clusters: int
    feature_dimension: int
    inertia: float
    membership_count: int
    created_at: datetime


class AdminClusterRunListResponse(BaseModel):
    total: int
    items: list[AdminClusterRunItem]


class AdminSystemLogItem(BaseModel):
    log_id: int
    action: str
    status: str
    detail: Optional[str] = None
    timestamp: datetime
    user_id: Optional[int] = None


class AdminSystemLogListResponse(BaseModel):
    total: int
    items: list[AdminSystemLogItem]


class AdminSourceTrendItem(BaseModel):
    source_platform: str
    count: int
    avg_trend_score: float


class AdminStatusBreakdownItem(BaseModel):
    status: str
    count: int


class AdminClusterBreakdownItem(BaseModel):
    cluster_id: int
    cluster_name: str
    member_count: int


class AdminClusterMembershipItem(BaseModel):
    membership_id: int
    cluster_id: int
    cluster_name: str
    dataset_id: Optional[int] = None
    content_id: Optional[int] = None
    item_text: str
    top_terms: Optional[str] = None
    created_at: datetime


class AdminClusterRunDetailResponse(BaseModel):
    run_id: int
    algorithm: str
    n_clusters: int
    feature_dimension: int
    inertia: float
    membership_count: int
    created_at: datetime
    cluster_breakdown: list[AdminClusterBreakdownItem]
    recent_memberships: list[AdminClusterMembershipItem]


class AdminOverviewReportResponse(BaseModel):
    dataset_total: int
    cluster_run_total: int
    system_log_total: int
    top_sources: list[AdminSourceTrendItem]
    top_categories: list[dict]
    status_breakdown: list[AdminStatusBreakdownItem]
    recent_actions: list[AdminSystemLogItem]
