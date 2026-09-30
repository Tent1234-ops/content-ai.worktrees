from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_watch_session
from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.database.db import get_db
from app.database.models import User, UserTrendWatchSession
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.services.trend_watch_sessions import end_trend_watch_session, start_trend_watch_session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.options("/login")
def login_options():
    return {"detail": "ok"}


@router.options("/register")
def register_options():
    return {"detail": "ok"}


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    existing_user = (
        db.query(User)
        .filter(or_(User.email == payload.email, User.username == payload.username))
        .first()
    )
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email or username already exists",
        )

    role = "user"
    if payload.role == "admin":
        if not settings.admin_invite_code or payload.admin_invite_code != settings.admin_invite_code:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid admin invite code",
            )
        role = "admin"

    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive")

    watch_session = start_trend_watch_session(
        db,
        user=user,
        region=settings.youtube_region,
    )
    token = create_access_token(
        subject=str(user.user_id),
        role=user.role,
        session_key=watch_session.session_key,
    )
    return TokenResponse(
        access_token=token,
        session_key=watch_session.session_key,
        user=user,
    )


@router.post("/logout")
def logout(
    watch_session: UserTrendWatchSession = Depends(get_current_watch_session),
    db: Session = Depends(get_db),
):
    end_trend_watch_session(db, watch_session=watch_session)
    return {"status": "ok"}


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user
