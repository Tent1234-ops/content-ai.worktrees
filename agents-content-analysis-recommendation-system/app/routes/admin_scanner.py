from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Literal

from app.api.deps import require_roles
from app.database.db import get_db
from app.database.models import User
from app.services.scanner import scan_google_trends, scan_tiktok_trends, scan_youtube_trends

router = APIRouter(prefix="/admin/scan", tags=["admin"])


@router.post("/youtube")
def admin_scan_youtube(
    limit: int = Query(default=20, ge=1, le=200),
    region: str | None = Query(default=None),
    mode: Literal["auto", "mock", "live"] = "auto",
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    stats = scan_youtube_trends(db=db, region=region, limit=limit, mode=mode)
    return {"status": "disabled", "stats": stats}


@router.post("/tiktok")
def admin_scan_tiktok(
    limit: int = Query(default=20, ge=1, le=200),
    region: str | None = Query(default=None),
    mode: Literal["auto", "mock", "live"] = "auto",
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    stats = scan_tiktok_trends(db=db, region=region, limit=limit, mode=mode)
    return {"status": "disabled", "stats": stats}


@router.post("/google")
def admin_scan_google(
    limit: int = Query(default=20, ge=1, le=200),
    region: str | None = Query(default=None),
    mode: Literal["auto", "mock", "live"] = "auto",
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    stats = scan_google_trends(db=db, region=region, limit=limit, mode=mode)
    return {"status": "disabled", "stats": stats}
