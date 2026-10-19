from typing import Any, Literal

from pydantic import BaseModel, Field


class ContentSimilarity(BaseModel):
    status: Literal["ready", "insufficient_evidence", "inconclusive"]
    reason: str | None = None
    low_score: float | None = Field(default=None, ge=0, le=1)
    high_score: float | None = Field(default=None, ge=0, le=1)
    closest_group: Literal["low", "high"] | None = None
    k_used: int = Field(ge=0)
    method: str
    supporting_dataset_ids: dict[str, list[int]]
    feature_count: int | None = None


class PerformanceClusteringResponse(BaseModel):
    schema_version: str
    category: str
    content_id: int
    analysis_id: int | None = None
    as_of: str
    data_basis: str
    reference_count: int = Field(ge=0)
    eligible_count: int = Field(ge=0)
    minimum_views: int = Field(ge=0)
    selection: dict[str, Any] | None = None
    excluded_counts: dict[str, int]
    channel_count: int = Field(ge=0)
    policy: dict[str, Any]
    clustering: dict[str, Any]
    content_similarity: ContentSimilarity
    reference_videos: list[dict[str, Any]]
    recommendations: list[dict[str, Any]]
    high_keywords: list[dict[str, Any]]
    shared_keywords: list[str]
    missing_keywords: list[str]
    limitation: str
    data_fingerprint: str | None = None
    view_metric_version: str | None = None
    format_counts: dict[str, int] = Field(default_factory=dict)
