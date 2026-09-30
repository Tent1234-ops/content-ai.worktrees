from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class DatasetContentItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    views: int
    likes: int
    comments: int
    trend_score: float
    duration_seconds: Optional[int] = None
    published_at: Optional[datetime] = None
    created_at: datetime


class DatasetListResponse(BaseModel):
    source: str
    total: int
    limit: int
    offset: int
    items: list[DatasetContentItem]
