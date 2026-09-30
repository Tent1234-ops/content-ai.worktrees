from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.database.db import get_db
from app.database.models import User
from app.schemas.datasets import DatasetContentItem, DatasetListResponse
from app.services.datasets import list_dataset_contents

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("/youtube", response_model=DatasetListResponse)
def get_youtube_datasets(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    category: str | None = Query(default=None),
    search: str | None = Query(default=None, min_length=1),
    _current_user: User = Depends(require_roles("admin", "user")),
    db: Session = Depends(get_db),
):
    total, items = list_dataset_contents(
        db,
        source_prefix="youtube",
        limit=limit,
        offset=offset,
        category=category,
        search=search,
    )
    return DatasetListResponse(
        source="youtube",
        total=total,
        limit=limit,
        offset=offset,
        items=[DatasetContentItem.model_validate(item) for item in items],
    )


@router.get("/google", response_model=DatasetListResponse)
def get_google_datasets(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    category: str | None = Query(default=None),
    search: str | None = Query(default=None, min_length=1),
    _current_user: User = Depends(require_roles("admin", "user")),
    db: Session = Depends(get_db),
):
    total, items = list_dataset_contents(
        db,
        source_prefix="google",
        limit=limit,
        offset=offset,
        category=category,
        search=search,
    )
    return DatasetListResponse(
        source="google",
        total=total,
        limit=limit,
        offset=offset,
        items=[DatasetContentItem.model_validate(item) for item in items],
    )
