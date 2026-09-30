from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.db import get_db
from app.database.models import User
from app.schemas.contents import (
    UserContentDetailResponse,
    UserContentHistoryResponse,
    ClipRevisionPlanRequest,
    ClipRevisionPlanResponse,
)
from app.services.contents import get_user_content_detail, list_user_contents
from app.services.usage_statistics import usage_statistics
from app.services.clip_revision_plans import get_revision_plan, save_revision_plan

router = APIRouter(prefix="/contents", tags=["contents"])


@router.get("/{content_id}/revision-plan", response_model=ClipRevisionPlanResponse)
def revision_plan(content_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_revision_plan(db, user_id=current_user.user_id, content_id=content_id)


@router.put("/{content_id}/revision-plan", response_model=ClipRevisionPlanResponse)
def update_revision_plan(content_id: int, payload: ClipRevisionPlanRequest,
                         current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return save_revision_plan(db, user_id=current_user.user_id, content_id=content_id, payload=payload)


@router.get("/my", response_model=UserContentHistoryResponse)
def my_contents(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    total, items = list_user_contents(db, user_id=current_user.user_id, limit=limit, offset=offset)
    return UserContentHistoryResponse(total=total, items=items)


@router.get("/statistics")
def content_statistics(
    year: int = Query(ge=2000, le=9999),
    month: int | None = Query(default=None, ge=1, le=12),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return usage_statistics(db, user_id=current_user.user_id, year=year, month=month)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{content_id}", response_model=UserContentDetailResponse)
def content_detail(
    content_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = get_user_content_detail(db, user_id=current_user.user_id, content_id=content_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Content not found")
    return UserContentDetailResponse.model_validate(item)
