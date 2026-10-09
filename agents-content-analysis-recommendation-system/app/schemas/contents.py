from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class UserContentHistoryItem(BaseModel):
    content_id: int
    title: str
    created_at: datetime
    video_url: Optional[str] = None
    transcript_preview: Optional[str] = None
    domain: Optional[str] = None
    recommended_duration: Optional[int] = None
    recommended_keywords: list[str]
    hook_keywords: list[str]
    outcome_assessment_status: str | None = None


class UserContentHistoryResponse(BaseModel):
    total: int
    items: list[UserContentHistoryItem]


class UserContentDetailResponse(BaseModel):
    content_id: int
    analysis_id: int | None = None
    recommendation_fingerprint: str | None = None
    outcome_assessment_fingerprint: str | None = None
    title: str
    created_at: datetime
    video_url: Optional[str] = None
    transcript: Optional[str] = None
    raw_transcript: Optional[str] = None
    cleaned_transcript: Optional[str] = None
    analysis: dict[str, Any]
    nlp_result: dict[str, Any]
    recommendation: dict[str, Any]
    outcome_assessment: dict[str, Any]
    revision_comparison: dict[str, Any] | None = None


class OutcomeScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analysis_id: int = Field(gt=0)
    assessment_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_topic_ids: list[str] = Field(min_length=1, max_length=3)


class OutcomeScenarioResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    schema_version: str
    status: str
    reason_codes: list[str]
    hypothetical: bool
    unit: str
    probability_before: float | None = None
    probability_after: float | None = None
    delta_percentage_points: float | None = None


class ClipRevisionPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analysis_id: int = Field(gt=0)
    recommendation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_revision: int = Field(ge=0)
    selected_advice_ids: list[str] = Field(max_length=3)
    notes: str = Field(default="", max_length=4000)


class ClipRevisionPlanResponse(BaseModel):
    content_id: int
    analysis_id: int
    recommendation_fingerprint: str
    revision: int
    selected_advice_ids: list[str]
    notes: str
    status: str = "planning"
    saved_at: str | None = None
