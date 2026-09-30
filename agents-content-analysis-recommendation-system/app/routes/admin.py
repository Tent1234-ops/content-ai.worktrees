from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.database.db import get_db
from app.database.models import User
from app.schemas.analysis_settings import AnalysisParameters
from app.services.analysis_settings import get_analysis_settings, save_analysis_settings
from app.services.trend_settings import TrendScheduleParameters, trend_schedule, save_trend_schedule
from app.services.usage_statistics import usage_statistics
from app.services.dataset_readiness import dataset_readiness, dataset_quality
from app.services.source_health import source_health
from app.services.reference_statistics import (
    ReferenceStatisticsParameters, statistics_overview, statistics_settings,
    save_statistics_settings, video_statistics_history, refresh_reference_statistics,
)
from app.schemas.admin_report import (
    AdminClusterRunListResponse,
    AdminClusterRunDetailResponse,
    AdminDatasetCreate,
    AdminDatasetItem,
    AdminDatasetListResponse,
    AdminDatasetUpdate,
    AdminOverviewReportResponse,
    AdminSystemLogItem,
    AdminSystemLogListResponse,
)
from app.schemas.admin_config import (
    AdminConfigResponse,
    AdminConfigUpdate,
    AdminConfigValidationResponse,
    AdminStatisticsResponse,
    BulkConfigResetResponse,
)
from pydantic import BaseModel
from app.database.models import SystemLog


class SourceUpdate(BaseModel):
    enabled: bool | None = None
    region: str | None = None
from app.schemas.auth import UserResponse
from app.services.admin_report import (
    build_admin_overview_report,
    create_admin_dataset,
    get_admin_cluster_run_detail,
    list_admin_cluster_runs,
    list_admin_datasets,
    list_admin_logs,
    update_admin_dataset,
    delete_admin_dataset,
    restore_admin_dataset,
)
from app.services.admin_settings import (
    get_admin_config,
    save_admin_config,
    reset_admin_config,
    validate_config,
    get_admin_statistics,
    export_config_backup,
    apply_config_from_backup,
    get_admin_audit_log,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/reference-statistics")
def admin_reference_statistics(offset: int = Query(default=0, ge=0),
                               limit: int = Query(default=20, ge=1, le=100),
                               _user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    return statistics_overview(db, offset=offset, limit=limit)


@router.get("/reference-statistics/settings")
def read_reference_statistics_settings(_user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    return statistics_settings(db)


@router.put("/reference-statistics/settings")
def update_reference_statistics_settings(values: ReferenceStatisticsParameters,
        user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    return save_statistics_settings(db, values, user_id=user.user_id)


@router.post("/reference-statistics/refresh", status_code=202)
def start_reference_statistics_refresh(_user: User = Depends(require_roles("admin"))):
    from app.services.jobs import enqueue
    return {"job_id": enqueue(refresh_reference_statistics, actor="admin", force=True), "status": "queued"}


@router.get("/datasets/{dataset_id}/statistics")
def read_dataset_statistics(dataset_id: int, _user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    try:
        return video_statistics_history(db, dataset_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/usage-statistics")
def admin_usage_statistics(
    year: int = Query(ge=2000, le=9999),
    month: int | None = Query(default=None, ge=1, le=12),
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    try:
        return usage_statistics(db, user_id=None, year=year, month=month)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/trend-settings")
def read_trend_settings(
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    return trend_schedule(db)


@router.put("/trend-settings")
def update_trend_settings(
    parameters: TrendScheduleParameters,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    return save_trend_schedule(db, parameters, user_id=current_user.user_id)


@router.get("/me")
def admin_profile(current_user: User = Depends(require_roles("admin"))):
    return {
        "message": "Admin access granted",
        "user": UserResponse.model_validate(current_user),
    }


@router.get("/datasets/readiness")
def admin_dataset_readiness(
    category: str | None = Query(default=None),
    role: str = Query(default="all", pattern="^(all|classification|evaluation|reference|current_trend|trend_archive|needs_attention)$"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    _current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    return dataset_readiness(db, category=category, role=role, offset=offset, limit=limit)


@router.get("/datasets", response_model=AdminDatasetListResponse)
def admin_datasets(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    source: str | None = Query(default=None),
    category: str | None = Query(default=None),
    search: str | None = Query(default=None),
    trashed: bool = Query(default=False),
    _current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    total, items = list_admin_datasets(
        db,
        limit=limit,
        offset=offset,
        source=source,
        category=category,
        search=search,
        trashed=trashed,
    )
    return AdminDatasetListResponse(
        total=total,
        items=[_dataset_response(item) for item in items],
    )


@router.post("/datasets", response_model=AdminDatasetItem)
def admin_dataset_create(
    payload: AdminDatasetCreate,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    try:
        item = create_admin_dataset(db, payload=payload, user_id=current_user.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _dataset_response(item)


@router.put("/datasets/{dataset_id}", response_model=AdminDatasetItem)
def admin_dataset_update(
    dataset_id: int,
    payload: AdminDatasetUpdate,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    try:
        item = update_admin_dataset(
            db,
            dataset_id=dataset_id,
            payload=payload,
            user_id=current_user.user_id,
            reviewer=current_user.username,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return _dataset_response(item)


def _dataset_response(item):
    result = AdminDatasetItem.model_validate(item, from_attributes=True)
    result.quality = dataset_quality(item)
    return result


@router.get("/sources/health")
def admin_source_health(_user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    return source_health(db)


@router.post("/datasets/{dataset_id}/restore", response_model=AdminDatasetItem)
def admin_dataset_restore(dataset_id: int, confirmation_id: int = Query(ge=1),
                          user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    try:
        item = restore_admin_dataset(db, dataset_id=dataset_id, user_id=user.user_id,
                                     confirmation_id=confirmation_id)
    except (ValueError, TypeError) as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Dataset is not in trash")
    return _dataset_response(item)


@router.delete("/datasets/{dataset_id}")
def admin_dataset_delete(
    dataset_id: int,
    confirmation_id: int = Query(ge=1),
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    try:
        deleted = delete_admin_dataset(db, dataset_id=dataset_id,
                                       user_id=current_user.user_id, confirmation_id=confirmation_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return {"deleted": True, "dataset_id": dataset_id, "archived": True}


@router.get("/clusters/runs", response_model=AdminClusterRunListResponse)
def admin_cluster_runs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    algorithm: str | None = Query(default=None),
    _current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    total, items = list_admin_cluster_runs(db, limit=limit, offset=offset, algorithm=algorithm)
    return AdminClusterRunListResponse(total=total, items=items)


@router.get("/clusters/runs/{run_id}", response_model=AdminClusterRunDetailResponse)
def admin_cluster_run_detail(
    run_id: int,
    _current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    item = get_admin_cluster_run_detail(db, run_id=run_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Cluster run not found")
    return AdminClusterRunDetailResponse.model_validate(item)


@router.get("/logs", response_model=AdminSystemLogListResponse)
def admin_logs(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    action: str | None = Query(default=None),
    _current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    total, items = list_admin_logs(db, limit=limit, offset=offset, status=status, action=action)
    return AdminSystemLogListResponse(
        total=total,
        items=[AdminSystemLogItem.model_validate(item, from_attributes=True) for item in items],
    )


@router.get("/reports/overview", response_model=AdminOverviewReportResponse)
def admin_reports_overview(
    _current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    try:
        report = build_admin_overview_report(db)
        return AdminOverviewReportResponse.model_validate(report)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error building admin report: {str(exc)}"
        )


# ============================================================================
# ADMIN CONFIGURATION MANAGEMENT ENDPOINTS
# ============================================================================

@router.get("/analysis-settings", tags=["admin-settings"])
def read_analysis_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    return get_analysis_settings(db, admin=True)


@router.put("/analysis-settings", tags=["admin-settings"])
def update_analysis_settings(
    parameters: AnalysisParameters,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    try:
        return save_analysis_settings(db, parameters, user_id=current_user.user_id)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/settings", response_model=AdminConfigResponse, tags=["admin-settings"])
def get_admin_settings(
    _current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """
    Get current admin configuration settings.
    
    Returns all system-wide configuration parameters used by the recommendation engine.
    """
    try:
        config = get_admin_config(db)
        return config
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving admin settings: {str(exc)}"
        )


@router.put("/settings", response_model=AdminConfigResponse, tags=["admin-settings"])
def update_admin_settings(
    config_update: AdminConfigUpdate,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """
    Update admin configuration settings.
    
    Allows partial updates - only fields that are provided will be updated.
    
    Parameters:
    - max_keywords_display (1-50): Maximum keywords shown in recommendations
    - hook_analysis_duration (10-300): Duration in seconds for hook analysis
    - analysis_time_range_days (1-365): Days back to consider for analysis
    - notification_batch_size (1-200): Max notifications per batch
    - youtube_region (2-char): YouTube trending region (TH, US, GB, etc.)
    - google_region (2-char): Google Trends region
    - enable_youtube_trending: Toggle YouTube trending data collection
    - enable_google_trends: Toggle Google Trends data collection
    - auto_scan_interval_hours (1-24): Hours between automatic scans
    """
    try:
        # Validate configuration
        validation = validate_config(config_update)
        if not validation["is_valid"]:
            raise HTTPException(
                status_code=400,
                detail=f"Configuration validation failed: {', '.join(validation['errors'])}"
            )
        
        # Save configuration
        config = save_admin_config(
            db,
            config_update,
            user_id=current_user.user_id,
        )
        return config
    except HTTPException:
        raise
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error updating admin settings: {str(exc)}"
        )


@router.post("/settings/validate", response_model=AdminConfigValidationResponse, tags=["admin-settings"])
def validate_admin_settings(
    config_update: AdminConfigUpdate,
    _current_user: User = Depends(require_roles("admin")),
):
    """
    Validate admin configuration without saving.
    
    Useful for previewing changes before committing them.
    """
    try:
        validation = validate_config(config_update)
        
        return AdminConfigValidationResponse(
            is_valid=validation["is_valid"],
            message="Configuration is valid" if validation["is_valid"] 
                    else f"Validation errors: {', '.join(validation['errors'])}",
            config=None
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error validating admin settings: {str(exc)}"
        )


@router.post("/settings/reset", response_model=AdminConfigResponse, tags=["admin-settings"])
def reset_admin_settings_to_default(
    confirm: bool = Query(False, description="Set to true to confirm reset"),
    _current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """
    Reset admin configuration to default values.
    
    Parameters:
    - confirm: Must be True to actually perform the reset
    
    Default values:
    - max_keywords_display: 10
    - hook_analysis_duration: 60 seconds
    - analysis_time_range_days: 90
    - notification_batch_size: 50
    - youtube_region: TH
    - google_region: TH
    - enable_youtube_trending: True
    - enable_google_trends: True
    - auto_scan_interval_hours: 6
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Reset not confirmed. Set confirm=true to proceed."
        )
    
    try:
        config = reset_admin_config(db)
        return config
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error resetting admin settings: {str(exc)}"
        )


@router.get("/statistics", response_model=AdminStatisticsResponse, tags=["admin-settings"])
def get_admin_dashboard_statistics(
    _current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """
    Get comprehensive admin dashboard statistics.
    
    Returns:
    - User statistics (total, active, inactive)
    - Analysis statistics (total count, per-user average)
    - Notification statistics (total, unread)
    - Trending topic statistics (followed domains and keywords)
    - Data source status and last scan times
    """
    try:
        stats = get_admin_statistics(db)
        
        return AdminStatisticsResponse(
            total_users=stats["total_users"],
            active_users=stats["active_users"],
            total_analyses=stats["total_analyses"],
            total_saved_ideas=stats.get("total_saved_ideas", 0),
            analyses_by_category=stats["analyses_by_category"],
            most_used_categories=stats["most_used_categories"],
            avg_analyses_per_user=stats["avg_analyses_per_user"],
            trend_data_sources_active=stats["trend_data_sources_active"],
            last_trend_scan=stats.get("last_trend_scan"),
            last_config_update=stats.get("last_config_update"),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving admin statistics: {str(exc)}"
        )


@router.post("/settings/backup", tags=["admin-settings"])
def backup_admin_configuration(
    _current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """
    Export current admin configuration as a backup.
    
    Returns a JSON object containing:
    - Current configuration settings
    - System statistics at backup time
    - Backup timestamp
    
    Useful before making significant changes or for disaster recovery.
    """
    try:
        backup = export_config_backup(db)
        return {
            "status": "success",
            "message": "Configuration backup created",
            "backup": backup
        }
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error creating backup: {str(exc)}"
        )


@router.post("/settings/restore", response_model=AdminConfigResponse, tags=["admin-settings"])
def restore_admin_configuration_from_backup(
    backup_data: dict,
    confirm: bool = Query(False, description="Set to true to confirm restore"),
    _current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """
    Restore admin configuration from a backup.
    
    Parameters:
    - backup_data: The backup JSON object (from /admin/settings/backup)
    - confirm: Must be True to actually perform the restore
    
    This will overwrite the current configuration with the backed-up values.
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Restore not confirmed. Set confirm=true to proceed."
        )
    
    try:
        config = apply_config_from_backup(db, backup_data)
        return config
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error restoring configuration: {str(exc)}"
        )


@router.post("/settings/audit-log", tags=["admin-settings"])
def get_settings_audit_log(
    limit: int = Query(50, ge=1, le=200, description="Maximum log entries to return"),
    _current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """
    Get audit log of admin configuration changes.
    
    Returns a log of who changed what settings and when.
    (Can be extended to log actual changes to system_configs table)
    """
    try:
        audit_data = get_admin_audit_log(db, limit=limit)
        return {
            "status": "success",
            "message": "Audit log retrieved",
            "total_entries": audit_data["total_entries"],
            "entries": audit_data["entries"],
        }
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving audit log: {str(exc)}"
        )


@router.post("/health", tags=["admin-settings"])
def check_admin_system_health(
    _current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """
    Check overall system health and configuration status.
    
    Validates:
    - Database connection
    - Configuration validity
    - Critical settings values
    - Data source connectivity
    """
    try:
        config = get_admin_config(db)
        stats = get_admin_statistics(db)
        
        # Health checks
        health_checks = {
            "database": "ok" if config.config_id else "error",
            "configuration_valid": "ok" if all([
                1 <= config.max_keywords_display <= 50,
                10 <= config.hook_analysis_duration <= 300,
                1 <= config.analysis_time_range_days <= 365,
            ]) else "warning",
            "users_registered": "ok" if stats["total_users"] > 0 else "warning",
            "system_active": "ok" if stats["active_users"] > 0 else "warning",
        }
        
        overall_status = "ok" if all(v == "ok" for v in health_checks.values()) else "warning"
        
        return {
            "status": overall_status,
            "timestamp": __import__('datetime').datetime.utcnow().isoformat(),
            "health_checks": health_checks,
            "configuration_summary": {
                "max_keywords": config.max_keywords_display,
                "hook_duration_sec": config.hook_analysis_duration,
                "analysis_range_days": config.analysis_time_range_days,
            },
            "statistics_summary": {
                "total_users": stats["total_users"],
                "total_analyses": stats["total_analyses"],
                "active_notifications": stats["total_notifications"],
            }
        }
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error checking system health: {str(exc)}"
        )


# ---------------------------------------------------------------------------
# Admin: Manage data sources (youtube / google / tiktok)
# ---------------------------------------------------------------------------
@router.get("/sources", tags=["admin-settings"])
def get_admin_sources(
        _current_user: User = Depends(require_roles("admin")),
        db: Session = Depends(get_db),
):
        """
        Get current data source configuration and recent scan times.

        Returns per-source: enabled (bool), region (string), last_scan (datetime|null)
        """
        try:
            config = get_admin_config(db)

            def _last_scan_for(source_key: str):
                row = (
                    db.query(SystemLog.timestamp)
                    .filter(SystemLog.action.like(f"%{source_key}_trends_sync%"))
                    .order_by(SystemLog.timestamp.desc())
                    .first()
                )
                return row[0] if row else None

            sources = {
                "youtube": {
                    "enabled": bool(config.enable_youtube_trending),
                    "region": config.youtube_region,
                    "last_scan": _last_scan_for("youtube"),
                },
                "google": {
                    "enabled": bool(config.enable_google_trends),
                    "region": config.google_region,
                    "last_scan": _last_scan_for("google"),
                },
                "tiktok": {
                    "enabled": bool(getattr(config, "enable_tiktok_trending", False)),
                    "region": getattr(config, "tiktok_region", None),
                    "last_scan": _last_scan_for("tiktok"),
                },
                "auto_scan_interval_hours": config.auto_scan_interval_hours,
            }

            return {"status": "ok", "sources": sources}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Error retrieving sources: {str(exc)}")


# ---------------------------------------------------------------------------
# Admin: Lexicon management (brands, models)
# ---------------------------------------------------------------------------
@router.get("/lexicon", tags=["admin-settings"])
def get_lexicon(
            _current_user: User = Depends(require_roles("admin")),
):
            from app.services.lexicon import load_lexicon

            try:
                return {"status": "ok", "lexicon": load_lexicon()}
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Error loading lexicon: {str(exc)}")


class LexiconUpdate(BaseModel):
            brands: list[str] | None = None
            models: list[str] | None = None


@router.put("/lexicon", tags=["admin-settings"])
def update_lexicon(
            payload: LexiconUpdate,
            _current_user: User = Depends(require_roles("admin")),
):
            from app.services.lexicon import save_lexicon

            try:
                data = {"brands": payload.brands or [], "models": payload.models or []}
                saved = save_lexicon(data)
                return {"status": "ok", "lexicon": saved}
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Error saving lexicon: {str(exc)}")


@router.post("/lexicon/brands", tags=["admin-settings"])
def add_lexicon_brand(
            item: dict,
            _current_user: User = Depends(require_roles("admin")),
):
            from app.services.lexicon import add_brand
            b = item.get("brand") or item.get("name")
            if not b:
                raise HTTPException(status_code=400, detail="brand is required")
            try:
                saved = add_brand(b)
                return {"status": "ok", "lexicon": saved}
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Error adding brand: {str(exc)}")


@router.delete("/lexicon/brands", tags=["admin-settings"])
def remove_lexicon_brand(
            brand: str | None = None,
            _current_user: User = Depends(require_roles("admin")),
):
            from app.services.lexicon import remove_brand
            if not brand:
                raise HTTPException(status_code=400, detail="brand query param required")
            try:
                saved = remove_brand(brand)
                return {"status": "ok", "lexicon": saved}
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Error removing brand: {str(exc)}")


@router.put("/sources/{source_name}", tags=["admin-settings"])
def update_admin_source(
        source_name: str,
        payload: SourceUpdate,
        current_user: User = Depends(require_roles("admin")),
        db: Session = Depends(get_db),
):
        """
        Update a data source configuration.

        source_name: one of 'youtube', 'google', 'tiktok'
        payload: { enabled?: bool, region?: str }

        This updates the admin configuration for the selected source.
        """
        source_key = source_name.lower().strip()
        if source_key not in {"youtube", "google", "tiktok"}:
            raise HTTPException(status_code=400, detail="Unsupported source; must be one of: youtube, google, tiktok")

        update_kwargs = {}
        if payload.enabled is not None:
            if source_key == "youtube":
                update_kwargs["enable_youtube_trending"] = bool(payload.enabled)
            elif source_key == "google":
                update_kwargs["enable_google_trends"] = bool(payload.enabled)
            elif source_key == "tiktok":
                update_kwargs["enable_tiktok_trending"] = bool(payload.enabled)

        if payload.region is not None:
            region = payload.region.strip().upper()
            if len(region) < 2:
                raise HTTPException(status_code=400, detail="region must be a 2-letter code")
            if source_key == "youtube":
                update_kwargs["youtube_region"] = region
            elif source_key == "google":
                update_kwargs["google_region"] = region
            elif source_key == "tiktok":
                update_kwargs["tiktok_region"] = region

        if not update_kwargs:
            raise HTTPException(status_code=400, detail="No updatable fields provided")

        try:
            cfg_update = AdminConfigUpdate(**update_kwargs)
            updated = save_admin_config(
                db,
                cfg_update,
                user_id=current_user.user_id,
            )
            return {"status": "ok", "config": updated}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Error updating source config: {str(exc)}")
