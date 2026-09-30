from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.database.db import get_db
from app.database.models import User
from app.schemas.clustering import (
    DatasetKMeansRequest,
    DatasetKMeansResponse,
    HDBSCANRequest,
    HDBSCANResponse,
    HDBSCANSaveResponse,
    KMeansRequest,
    KMeansResponse,
    KMeansSaveResponse,
)
from app.services.clustering import cluster_texts_hdbscan, cluster_texts_kmeans
from app.services.datasets import list_dataset_contents
from app.services.persistence import save_cluster_result

router = APIRouter(prefix="/clustering", tags=["clustering"])


@router.post("/kmeans", response_model=KMeansResponse)
def run_kmeans(
    payload: KMeansRequest,
    _current_user: User = Depends(require_roles("admin", "user")),
):
    texts = [item.text for item in payload.items]
    try:
        result = cluster_texts_kmeans(
            texts=texts,
            n_clusters=payload.n_clusters,
            max_features=payload.max_features,
            max_iterations=payload.max_iterations,
            seed=payload.seed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return KMeansResponse.model_validate(result)


@router.post("/hdbscan", response_model=HDBSCANResponse)
def run_hdbscan(
    payload: HDBSCANRequest,
    _current_user: User = Depends(require_roles("admin", "user")),
):
    texts = [item.text for item in payload.items]
    try:
        result = cluster_texts_hdbscan(
            texts=texts,
            max_features=payload.max_features,
            min_cluster_size=payload.min_cluster_size,
            min_samples=payload.min_samples,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return HDBSCANResponse.model_validate(result)


@router.post("/kmeans/save", response_model=KMeansSaveResponse)
def run_kmeans_and_save(
    payload: KMeansRequest,
    current_user: User = Depends(require_roles("admin", "user")),
    db: Session = Depends(get_db),
):
    texts = [item.text for item in payload.items]
    try:
        result = cluster_texts_kmeans(
            texts=texts,
            n_clusters=payload.n_clusters,
            max_features=payload.max_features,
            max_iterations=payload.max_iterations,
            seed=payload.seed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    saved = save_cluster_result(
        db,
        user=current_user,
        clustering_result=result,
        items=[item.model_dump() for item in payload.items],
    )
    return KMeansSaveResponse(
        run_id=saved["run_id"],
        saved_memberships=saved["saved_memberships"],
        result=KMeansResponse.model_validate(result),
    )


@router.post("/hdbscan/save", response_model=HDBSCANSaveResponse)
def run_hdbscan_and_save(
    payload: HDBSCANRequest,
    current_user: User = Depends(require_roles("admin", "user")),
    db: Session = Depends(get_db),
):
    texts = [item.text for item in payload.items]
    try:
        result = cluster_texts_hdbscan(
            texts=texts,
            max_features=payload.max_features,
            min_cluster_size=payload.min_cluster_size,
            min_samples=payload.min_samples,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    saved = save_cluster_result(
        db,
        user=current_user,
        clustering_result=result,
        items=[item.model_dump() for item in payload.items],
    )
    return HDBSCANSaveResponse(
        run_id=saved["run_id"],
        saved_memberships=saved["saved_memberships"],
        result=HDBSCANResponse.model_validate(result),
    )


@router.post("/from-dataset", response_model=DatasetKMeansResponse)
def run_kmeans_from_dataset(
    payload: DatasetKMeansRequest,
    current_user: User = Depends(require_roles("admin", "user")),
    db: Session = Depends(get_db),
):
    total, rows = list_dataset_contents(
        db,
        source_prefix=payload.source,
        limit=payload.limit,
        offset=payload.offset,
        category=payload.category,
        search=None,
    )
    items = []
    for row in rows:
        text = " ".join(part for part in [row.title, row.transcript, row.category] if part).strip()
        if not text:
            continue
        items.append({"dataset_id": row.dataset_id, "text": text})

    try:
        if payload.algorithm == "hdbscan":
            result = cluster_texts_hdbscan(
                texts=[item["text"] for item in items],
                max_features=payload.max_features,
                min_cluster_size=payload.min_cluster_size,
                min_samples=payload.min_samples,
            )
        else:
            if len(items) < payload.n_clusters:
                raise HTTPException(
                    status_code=400,
                    detail="Not enough dataset items to run KMeans with the requested number of clusters",
                )
            result = cluster_texts_kmeans(
                texts=[item["text"] for item in items],
                n_clusters=payload.n_clusters,
                max_features=payload.max_features,
                max_iterations=payload.max_iterations,
                seed=payload.seed,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    run_id = None
    if payload.save_result:
        saved = save_cluster_result(
            db,
            user=current_user,
            clustering_result=result,
            items=items,
        )
        run_id = saved["run_id"]

    return DatasetKMeansResponse(
        source=payload.source,
        total_items_used=len(items),
        run_id=run_id,
        result=(
            HDBSCANResponse.model_validate(result)
            if payload.algorithm == "hdbscan"
            else KMeansResponse.model_validate(result)
        ),
    )
