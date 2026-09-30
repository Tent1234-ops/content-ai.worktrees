from typing import Optional

from pydantic import BaseModel, Field


class ClassificationRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    text: str = Field(..., min_length=1)
    source: str = Field(default="youtube", pattern="^(youtube|google)$")
    profile_limit: int = Field(default=200, ge=10, le=500)
    top_k: int = Field(default=5, ge=1, le=10)


class ClassificationCandidate(BaseModel):
    domain: str
    taxonomy_leaf_key: Optional[str] = None
    score: float
    similarity: float
    sample_size: int
    matched_terms: list[str]


class ClassificationResponse(BaseModel):
    domain: str
    confidence: float
    method: str
    rule_domain: str
    source: str
    profile_limit: int
    candidates: list[ClassificationCandidate]
    taxonomy_version: str = "content-taxonomy-v1"
    taxonomy_leaf_key: str = "unknown"
    category_level_1: Optional[str] = None
    category_level_2: Optional[str] = None
    category_level_3: Optional[str] = None
    is_unknown: bool = False
    taxonomy_ready: bool = False
    warning: Optional[str] = None
    raw_taxonomy_leaf_key: Optional[str] = None
    model_id: Optional[int] = None
    model_key: Optional[str] = None
    model_version: Optional[str] = None
    unknown_threshold: Optional[float] = None
    acceptance: dict[str, object] = Field(default_factory=dict)


class TaxonomyNodeItem(BaseModel):
    node_key: str
    display_name: str
    display_name_th: Optional[str] = None
    level: int
    parent_key: Optional[str] = None
    is_leaf: bool
    is_active: bool
    is_trainable: bool
    minimum_sample_count: int


class TaxonomyLeafCoverageItem(BaseModel):
    leaf_key: str
    category_level_1: Optional[str] = None
    category_level_2: Optional[str] = None
    category_level_3: Optional[str] = None
    source_dataset: str
    source_category: Optional[str] = None
    source_subcategories: list[str]
    minimum_sample_count: int
    verified_sample_count: int
    ready: bool


class TaxonomyResponse(BaseModel):
    taxonomy_version: str
    source_dataset: str
    minimum_samples_per_leaf: int
    leaf_count: int
    ready_leaf_count: int
    ready: bool
    unknown_leaf_key: str
    nodes: list[TaxonomyNodeItem]
    leaves: list[TaxonomyLeafCoverageItem]
