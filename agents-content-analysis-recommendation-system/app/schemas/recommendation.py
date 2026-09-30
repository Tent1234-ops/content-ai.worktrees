from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.classification import ClassificationResponse


class RecommendationKeywordExample(BaseModel):
    dataset_id: int
    source_record_id: str = ""
    title: str
    video_url: str = ""
    published_at: Optional[str] = None
    statistics_captured_at: Optional[str] = None
    source_channel_id: str = ""
    data_split: str = ""
    platform: str = "youtube"
    frequency: int = 0
    matched_terms: list[str] = Field(default_factory=list)
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    average_views_per_day: float = 0.0
    engagement_rate: float = 0.0
    performance_weight: float = 0.0
    occurrences: list[dict[str, object]] = Field(default_factory=list)


class RecommendationKeywordItem(BaseModel):
    keyword: str
    score: float
    support_count: int = 0
    sample_size: int = 0
    support_ratio: float = 0.0
    total_frequency: int = 0
    matched_terms: list[str] = Field(default_factory=list)
    supporting_dataset_row_ids: list[int] = Field(default_factory=list)
    supporting_examples: list[RecommendationKeywordExample] = Field(
        default_factory=list
    )
    score_components: dict[str, float] = Field(default_factory=dict)
    supporting_records: list[RecommendationKeywordExample] = Field(default_factory=list)
    channel_count: int = 0
    evidence_topic_id: Optional[str] = None


class RecommendationDimensionItem(BaseModel):
    name: str
    score: float
    user_status: str
    evidence_topic_id: Optional[str] = None


class DurationRecommendation(BaseModel):
    recommended_seconds: Optional[int] = None
    recommended_range: str
    sample_size: int
    source: str
    evidence_status: str = "insufficient_evidence"
    minimum_sample_size: int = 10
    target_sample_size: int = 15
    cohort: str = "upload_compatible_under_5m"
    median_seconds: Optional[int] = None
    percentile_low: int = 25
    percentile_high: int = 75
    percentile_low_seconds: Optional[int] = None
    percentile_high_seconds: Optional[int] = None


class DatasetProfileResponseItem(BaseModel):
    domain: str
    sample_size: int
    eligible_pool_size: int = 0
    reference_period: dict[str, Optional[str]] = Field(default_factory=dict)
    reference_records: list[dict[str, object]] = Field(default_factory=list)
    view_metric_version: str = ""
    view_metric_cohort_size: int = 0
    performance_eligible_pool_size: int = 0
    excluded_incompatible_view_metric_rows: int = 0
    selection_rule: str = "none"
    source: str = "youtube"
    source_platform_counts: dict[str, int] = Field(default_factory=dict)
    top_keywords: list[RecommendationKeywordItem]
    top_dimensions: list[RecommendationKeywordItem]
    hook_keywords: list[RecommendationKeywordItem]
    recommended_duration: DurationRecommendation
    duration_samples: list[int] = Field(default_factory=list)
    duration_metadata_coverage_size: int = 0
    duration_eligible_pool_size: int = 0
    duration_dataset_row_ids: list[int] = Field(default_factory=list)
    duration_source_record_ids: list[str] = Field(default_factory=list)
    duration_exemplar_titles: list[str] = Field(default_factory=list)
    duration_selection_rule: str = "none"
    exemplar_titles: list[str]


class DatasetProfilesResponse(BaseModel):
    source: str
    total_profiles: int
    profiles: list[DatasetProfileResponseItem]


class RecommendationTextRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    text: str = Field(..., min_length=1)
    source: str = Field(default="youtube", pattern="^(youtube|google|tiktok)$")
    profile_limit: int = Field(default=100, ge=10, le=500)


class RecommendationAnalysisResponse(BaseModel):
    domain: str
    status: Optional[str] = None
    classification: Optional[ClassificationResponse] = None
    user_keywords: list[str]
    missing_keywords: list[RecommendationKeywordItem]
    hook_keywords: list[RecommendationKeywordItem]
    missing_dimensions: list[RecommendationDimensionItem]
    recommended_duration: DurationRecommendation
    dataset_profile: DatasetProfileResponseItem
    evidence: dict[str, object] = Field(default_factory=dict)
    current_trend_ideas: dict[str, object] = Field(default_factory=dict)
    evidence_bundle: dict[str, object] = Field(default_factory=dict)
    actionable_recommendations: dict[str, object] = Field(default_factory=dict)


class ProfileComparisonItem(BaseModel):
    domain: str
    left_sample_size: int
    right_sample_size: int
    left_top_keywords: list[RecommendationKeywordItem]
    right_top_keywords: list[RecommendationKeywordItem]
    left_duration: DurationRecommendation
    right_duration: DurationRecommendation


class ProfileComparisonResponse(BaseModel):
    left_source: str
    right_source: str
    comparisons: list[ProfileComparisonItem]


class SourceActivityItem(BaseModel):
    source_platform: str
    count: int


class RecommendationAdminDatasetHealth(BaseModel):
    total_dataset_contents: int
    youtube_dataset_contents: int
    google_dataset_contents: int
    tiktok_dataset_contents: int = 0
    duration_coverage_count: int
    duration_coverage_ratio: float


class RecommendationAdminProfileHealth(BaseModel):
    youtube_profiles: int
    google_profiles: int
    tiktok_profiles: int = 0
    youtube_domains: list[str]
    google_domains: list[str]
    tiktok_domains: list[str] = Field(default_factory=list)


class RecommendationAdminReportResponse(BaseModel):
    dataset_health: RecommendationAdminDatasetHealth
    profile_health: RecommendationAdminProfileHealth
    recent_source_activity: list[SourceActivityItem]
    youtube_profiles: list[DatasetProfileResponseItem]
    google_profiles: list[DatasetProfileResponseItem]
    tiktok_profiles: list[DatasetProfileResponseItem] = Field(default_factory=list)
