from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.database.db import get_db
from app.database.models import User, UserTrendWatchSession
from app.services.trend_watch_sessions import get_active_trend_watch_session

bearer_scheme = HTTPBearer(auto_error=False)


def _decode_credentials(credentials: HTTPAuthorizationCredentials | None) -> dict:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing access token")
    try:
        return decode_access_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    payload = _decode_credentials(credentials)
    subject = payload.get("sub")
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")

    user = db.query(User).filter(User.user_id == int(subject)).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive")
    session_key = str(payload.get("sid") or "")
    if not session_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login session is missing")
    watch_session = get_active_trend_watch_session(
        db,
        user_id=user.user_id,
        session_key=session_key,
    )
    if watch_session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login session has ended")
    return user


def get_current_watch_session(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    header_session_key: str | None = Header(default=None, alias="X-Trend-Session-Key"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserTrendWatchSession:
    payload = _decode_credentials(credentials)
    session_key = str(payload.get("sid") or "")
    if header_session_key and header_session_key != session_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login session mismatch")
    watch_session = get_active_trend_watch_session(
        db,
        user_id=current_user.user_id,
        session_key=session_key,
    )
    if watch_session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login session has ended")
    return watch_session


def require_roles(*allowed_roles: str):
    role_set = set(allowed_roles)

    def _role_guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in role_set:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return _role_guard
