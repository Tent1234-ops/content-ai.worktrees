from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.database.db import get_db
from app.database.models import User
from app.schemas.follows import FollowTopicRequest, FollowedTopicItem, FollowedTopicsResponse, FollowPreferences
from app.services.follows import (follow_topic, unfollow_topic, list_followed_topics,
                                  follow_preferences, save_follow_preferences)

router = APIRouter(prefix="/follows", tags=["follows"])


@router.get('/preferences')
def preferences(current_user: User = Depends(require_roles('user', 'admin')),
                db: Session = Depends(get_db)):
    return follow_preferences(db, user_id=current_user.user_id)


@router.put('/preferences')
def update_preferences(request: FollowPreferences,
                       current_user: User = Depends(require_roles('user', 'admin')),
                       db: Session = Depends(get_db)):
    return save_follow_preferences(db, user_id=current_user.user_id, mode=request.notification_mode)


@router.post("/topic", response_model=FollowedTopicItem)
def follow_topic_endpoint(
    request: FollowTopicRequest,
    current_user: User = Depends(require_roles("user", "admin")),
    db: Session = Depends(get_db),
):
    try:
        ft = follow_topic(db=db, user_id=current_user.user_id, match_type=request.match_type,
                          value=request.value, platform=request.platform)
        return ft
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/topic/{id}")
def unfollow_topic_endpoint(
    id: int,
    current_user: User = Depends(require_roles("user", "admin")),
    db: Session = Depends(get_db),
):
    deleted = unfollow_topic(db=db, user_id=current_user.user_id, id=id)
    return {"deleted": deleted}


@router.get("/topics", response_model=FollowedTopicsResponse)
def list_topics(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(require_roles("user", "admin")),
    db: Session = Depends(get_db),
):
    res = list_followed_topics(db=db, user_id=current_user.user_id, limit=limit, offset=offset)
    return FollowedTopicsResponse(total=res["total"], items=res["items"])
