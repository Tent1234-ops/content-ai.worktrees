from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.database.db import get_db
from app.database.models import User
from app.schemas.recommendation import (
    ProfileComparisonResponse,
    DatasetProfilesResponse,
    RecommendationAdminReportResponse,
    RecommendationAnalysisResponse,
    RecommendationTextRequest,
)
from app.services.recommendation import (
    build_dataset_profiles,
    build_recommendation_admin_report,
    build_recommendation_from_saved_content,
    build_recommendation_from_text,
    compare_dataset_profiles,
)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("/profiles", response_model=DatasetProfilesResponse)
def get_dataset_profiles(
    source: str = Query(default="youtube", pattern="^(youtube|google|tiktok)$"),
    limit: int = Query(default=150, ge=10, le=500),
    _current_user: User = Depends(require_roles("admin", "user")),
    db: Session = Depends(get_db),
):
    profiles = build_dataset_profiles(db, source_prefix=source, limit=limit)
    return DatasetProfilesResponse(
        source=source,
        total_profiles=len(profiles),
        profiles=profiles,
    )


@router.get("/profiles/compare", response_model=ProfileComparisonResponse)
def compare_profiles(
    left_source: str = Query(default="youtube", pattern="^(youtube|google|tiktok)$"),
    right_source: str = Query(default="google", pattern="^(youtube|google|tiktok)$"),
    limit: int = Query(default=150, ge=10, le=500),
    _current_user: User = Depends(require_roles("admin", "user")),
    db: Session = Depends(get_db),
):
    return ProfileComparisonResponse.model_validate(
        compare_dataset_profiles(
            db,
            left_source=left_source,
            right_source=right_source,
            limit=limit,
        )
    )


@router.post("/from-text", response_model=RecommendationAnalysisResponse)
def recommend_from_text(
    payload: RecommendationTextRequest,
    _current_user: User = Depends(require_roles("admin", "user")),
    db: Session = Depends(get_db),
):
    return RecommendationAnalysisResponse.model_validate(
        build_recommendation_from_text(
            db,
            title=payload.title,
            text=payload.text,
            source_prefix=payload.source,
            profile_limit=payload.profile_limit,
        )
    )


@router.get("/from-content/{content_id}", response_model=RecommendationAnalysisResponse)
def recommend_from_content(
    content_id: int,
    source: str = Query(default="youtube", pattern="^(youtube|google|tiktok)$"),
    profile_limit: int = Query(default=150, ge=10, le=500),
    current_user: User = Depends(require_roles("admin", "user")),
    db: Session = Depends(get_db),
):
    result = build_recommendation_from_saved_content(
        db,
        content_id=content_id,
        source_prefix=source,
        profile_limit=profile_limit,
        user_id=current_user.user_id,
        allow_admin=(current_user.role == "admin"),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Content not found or access denied")
    return RecommendationAnalysisResponse.model_validate(result)


@router.get("/admin/report", response_model=RecommendationAdminReportResponse)
def recommendation_admin_report(
    profile_limit: int = Query(default=150, ge=10, le=500),
    _current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    return RecommendationAdminReportResponse.model_validate(
        build_recommendation_admin_report(db, profile_limit=profile_limit)
    )
