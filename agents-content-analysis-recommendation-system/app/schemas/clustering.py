from typing import List

from pydantic import BaseModel, Field


class ClusteringTextItem(BaseModel):
    text: str = Field(..., min_length=1)
    content_id: int | None = None
    dataset_id: int | None = None


class KMeansRequest(BaseModel):
    items: List[ClusteringTextItem] = Field(..., min_length=2)
    n_clusters: int = Field(..., ge=2, le=10)
    max_features: int = Field(default=50, ge=5, le=200)
    max_iterations: int = Field(default=25, ge=5, le=100)
    seed: int = Field(default=42, ge=0, le=999999)


class HDBSCANRequest(BaseModel):
    items: List[ClusteringTextItem] = Field(..., min_length=2)
    max_features: int = Field(default=50, ge=5, le=200)
    min_cluster_size: int = Field(default=2, ge=2, le=50)
    min_samples: int | None = Field(default=None, ge=1, le=50)


class ClusterAssignment(BaseModel):
    item_id: int
    cluster_id: int
    text: str
    top_terms: List[str]


class ClusterSummary(BaseModel):
    cluster_id: int
    label: str
    size: int
    top_terms: List[str]
    member_item_ids: List[int]


class KMeansResponse(BaseModel):
    algorithm: str
    n_clusters: int
    vocabulary: List[str]
    clusters: List[ClusterSummary]
    assignments: List[ClusterAssignment]
    feature_dimension: int
    iterations: int
    inertia: float


class HDBSCANResponse(BaseModel):
    algorithm: str
    n_clusters: int
    vocabulary: List[str]
    clusters: List[ClusterSummary]
    assignments: List[ClusterAssignment]
    feature_dimension: int
    iterations: int
    inertia: float
    noise_count: int


class KMeansSaveResponse(BaseModel):
    run_id: int
    saved_memberships: int
    result: KMeansResponse


class HDBSCANSaveResponse(BaseModel):
    run_id: int
    saved_memberships: int
    result: HDBSCANResponse


class DatasetKMeansRequest(BaseModel):
    source: str = Field(default="youtube", pattern="^(youtube|google|tiktok)$")
    category: str | None = None
    limit: int = Field(default=30, ge=2, le=100)
    offset: int = Field(default=0, ge=0)
    algorithm: str = Field(default="kmeans", pattern="^(kmeans|hdbscan)$")
    n_clusters: int = Field(..., ge=2, le=10)
    max_features: int = Field(default=50, ge=5, le=200)
    max_iterations: int = Field(default=25, ge=5, le=100)
    seed: int = Field(default=42, ge=0, le=999999)
    min_cluster_size: int = Field(default=2, ge=2, le=50)
    min_samples: int | None = Field(default=None, ge=1, le=50)
    save_result: bool = Field(default=True)


class DatasetKMeansResponse(BaseModel):
    source: str
    total_items_used: int
    run_id: int | None = None
    result: KMeansResponse | HDBSCANResponse
