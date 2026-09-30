from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class DatasetReviewRunItem(BaseModel):
    collection_run_id: int
    dataset_version: str
    status: str
    started_at: datetime
    total: int
    pending: int
    approved: int
    rejected: int
    progress: dict[str, Any]
    last_resumed_at: datetime | None = None
    failure_message: str | None = None


class DatasetReviewCandidateItem(BaseModel):
    collection_run_id: int
    dataset_version: str
    source_youtube_id: str
    candidate_sha256: str
    title: str
    video_url: str
    channel_title: str
    youtube_license_code: str
    license_name: str
    public_captions_available: bool
    proposed_leaf_key: str
    transcript_language: str
    caption_type: str
    transcript_acquisition_method: str
    transcript_scope: str
    transcript_timestamps_available: bool
    view_metric_version: str
    duration_seconds: int
    transcript: str
    transcript_preview: str
    evidence_terms: list[str]
    automated_checks: dict[str, bool]
    dataset_usage: dict[str, bool]
    views: int
    likes: int
    comments: int
    collection_strategy: str
    average_views_per_day: float
    engagement_rate: float
    performance_rank_within_leaf: int
    review_status: Literal["pending", "approved", "rejected"]
    reviewed_leaf_key: str | None = None
    transcript_quality: str | None = None
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None
    dataset_id: int | None = None


class DatasetReviewQueueResponse(BaseModel):
    total: int
    limit: int
    offset: int
    summary: dict[str, int]
    runs: list[DatasetReviewRunItem]
    taxonomy: list[dict[str, Any]]
    items: list[DatasetReviewCandidateItem]


class DatasetReviewDecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    reviewed_leaf_key: str | None = Field(default=None, max_length=100)
    transcript_quality: Literal["good", "acceptable"] | None = None
    notes: str | None = Field(default=None, max_length=2000)
    expected_candidate_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    require_pending: bool = False


class DatasetReviewDecisionResponse(BaseModel):
    status: str
    decision: Literal["approve", "reject"]
    source_youtube_id: str
    collection_run_id: int
    dataset_id: int | None = None
    review_event_id: int | None = None
    run_status: str
    coverage: dict[str, Any]


class NotebookLMTranscriptCandidateRequest(BaseModel):
    video_url: str = Field(min_length=11, max_length=2048)
    transcript: str = Field(min_length=80, max_length=2_000_000)
    proposed_leaf_key: str = Field(min_length=1, max_length=100)
    transcript_language: Literal["th", "en"] = "th"
    caption_type: Literal["manual", "auto_generated", "unspecified"] = (
        "unspecified"
    )
    collection_strategy: Literal[
        "classification_diverse",
        "recommendation_high_performance",
    ] = "classification_diverse"
    collection_run_id: int | None = Field(default=None, ge=1)
    dataset_version: str = Field(
        default="youtube-public-research-th-v1",
        min_length=1,
        max_length=100,
    )


class NotebookLMTranscriptCandidateResponse(BaseModel):
    status: Literal["candidate_created"]
    collection_run_id: int
    candidate_count: int
    candidate_artifact_sha256: str
    candidate: DatasetReviewCandidateItem
