from typing import List

from pydantic import BaseModel, Field


class NLPRequest(BaseModel):
    text: str = Field(..., min_length=1)
    max_keywords: int = Field(default=10, ge=1, le=30)


class NLPSaveRequest(NLPRequest):
    title: str = Field(..., min_length=1, max_length=255)


class KeywordScore(BaseModel):
    keyword: str
    score: float
    frequency: int


class TermCount(BaseModel):
    term: str
    count: int


class FeatureAttributes(BaseModel):
    character_count: int
    token_count: int
    filtered_token_count: int
    unique_token_count: int
    top_terms: List[TermCount]


class NLPResponse(BaseModel):
    normalized_text: str
    tokens: List[str]
    filtered_tokens: List[str]
    keyword_candidates: List[KeywordScore]
    top_keywords: List[KeywordScore]
    feature_attributes: FeatureAttributes


class NLPSaveResponse(BaseModel):
    content_id: int
    saved_keywords: int
    result: NLPResponse
