from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_watch_session
from app.database.db import get_db
from app.database.models import User, UserTrendWatchSession
from app.schemas.notifications import MarkReadRequest, NotificationsResponse
from app.services.notifications import get_notifications, mark_notifications_read

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/", response_model=NotificationsResponse)
def list_notifications(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    watch_session: UserTrendWatchSession = Depends(get_current_watch_session),
    db: Session = Depends(get_db),
):
    result = get_notifications(
        db=db,
        user_id=current_user.user_id,
        watch_session_id=watch_session.watch_session_id,
        unread_only=unread_only,
        limit=limit,
        offset=offset,
    )
    return NotificationsResponse(total=result["total"], items=result["items"])


@router.post("/mark_read")
def mark_read(
    request: MarkReadRequest,
    current_user: User = Depends(get_current_user),
    watch_session: UserTrendWatchSession = Depends(get_current_watch_session),
    db: Session = Depends(get_db),
):
    marked = mark_notifications_read(
        db=db,
        user_id=current_user.user_id,
        watch_session_id=watch_session.watch_session_id,
        ids=request.ids,
    )
    return {"marked": marked}
