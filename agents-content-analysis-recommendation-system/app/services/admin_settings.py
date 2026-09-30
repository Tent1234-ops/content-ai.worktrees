"""Admin configuration service for managing system-wide settings"""

from typing import Dict, Optional, List
from datetime import datetime
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database.models import DatasetContent, SystemConfig, User, UserContent, FollowedTopic, Notification, SystemLog
from app.schemas.admin_config import AdminConfigUpdate, AdminConfigResponse
from app.schemas.analysis_settings import AnalysisParameters
from app.services.persistence import log_system_event


# Default configuration values
DEFAULT_CONFIG = {
    "max_keywords_display": 10,
    "hook_analysis_duration": 60,
    "analysis_time_range_days": 90,
    "notification_batch_size": 50,
    "youtube_region": "TH",
    "google_region": "TH",
    "tiktok_region": "TH",
    "enable_youtube_trending": True,
    "enable_google_trends": True,
    "enable_tiktok_trending": True,
    "auto_scan_interval_hours": 6,
    # New defaults
    "asr_model_default": "small",
    "enable_model_toggle": True,
    "job_backend": "inprocess",
    "redis_url": None,
}


def get_or_create_admin_config(db: Session) -> SystemConfig:
    """
    Get admin configuration or create default if not exists.
    Admin config is shared globally (single config_id = None for system-wide)
    """
    config = db.query(SystemConfig).filter(SystemConfig.user_id == None).first()
    
    if config:
        return config
    
    # Create default config
    config = SystemConfig(
        user_id=None,  # System-wide config
        max_keywords=DEFAULT_CONFIG["max_keywords_display"],
        hook_duration=DEFAULT_CONFIG["hook_analysis_duration"],
        process_interval=DEFAULT_CONFIG["analysis_time_range_days"],
        notification_batch_size=DEFAULT_CONFIG["notification_batch_size"],
        youtube_region=DEFAULT_CONFIG["youtube_region"],
        google_region=DEFAULT_CONFIG["google_region"],
        tiktok_region=DEFAULT_CONFIG["tiktok_region"],
        enable_youtube_trending=DEFAULT_CONFIG["enable_youtube_trending"],
        enable_google_trends=DEFAULT_CONFIG["enable_google_trends"],
        enable_tiktok_trending=DEFAULT_CONFIG["enable_tiktok_trending"],
        auto_scan_interval_hours=DEFAULT_CONFIG["auto_scan_interval_hours"],
        # New fields
        asr_model_default=DEFAULT_CONFIG["asr_model_default"],
        enable_model_toggle=DEFAULT_CONFIG["enable_model_toggle"],
        job_backend=DEFAULT_CONFIG["job_backend"],
        redis_url=DEFAULT_CONFIG["redis_url"],
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def get_admin_config(db: Session) -> AdminConfigResponse:
    """
    Retrieve current admin configuration
    """
    config = get_or_create_admin_config(db)
    
    # Map database fields to response schema
    return AdminConfigResponse(
        config_id=config.config_id,
        max_keywords_display=config.max_keywords,
        hook_analysis_duration=config.hook_duration,
        analysis_time_range_days=config.process_interval,
        notification_batch_size=config.notification_batch_size,
        youtube_region=config.youtube_region,
        google_region=config.google_region,
        tiktok_region=config.tiktok_region,
        enable_youtube_trending=config.enable_youtube_trending,
        enable_google_trends=config.enable_google_trends,
        enable_tiktok_trending=config.enable_tiktok_trending,
        auto_scan_interval_hours=config.auto_scan_interval_hours,
        created_at=config.created_at,
        updated_at=getattr(config, 'updated_at', config.created_at),
    )


def save_admin_config(
    db: Session,
    config_update: AdminConfigUpdate,
    *,
    user_id: int | None = None,
) -> AdminConfigResponse:
    """
    Save/update admin configuration.
    Only updates fields that are provided (not None).
    """
    config = get_or_create_admin_config(db)
    
    # Update only provided fields
    update_data = config_update.model_dump(exclude_unset=True)
    if update_data.get("hook_analysis_duration") is not None:
        AnalysisParameters(
            upload_max_duration_seconds=config.upload_max_duration_seconds,
            asr_model=config.asr_model_default,
            hook_duration_seconds=update_data["hook_analysis_duration"],
        )
    
    from app.runtime import set as runtime_set

    for field, value in update_data.items():
        if value is not None:
            # Map schema field names to database field names
            if field == "max_keywords_display":
                config.max_keywords = value
            elif field == "hook_analysis_duration":
                config.hook_duration = value
            elif field == "analysis_time_range_days":
                config.process_interval = value
            elif field == "notification_batch_size":
                config.notification_batch_size = value
            elif field == "youtube_region":
                config.youtube_region = value
            elif field == "google_region":
                config.google_region = value
            elif field == "tiktok_region":
                config.tiktok_region = value
            elif field == "enable_youtube_trending":
                config.enable_youtube_trending = value
            elif field == "enable_google_trends":
                config.enable_google_trends = value
            elif field == "enable_tiktok_trending":
                config.enable_tiktok_trending = value
            elif field == "auto_scan_interval_hours":
                config.auto_scan_interval_hours = value
            elif field == "asr_model_default":
                config.asr_model_default = value
                runtime_set("asr_model", value)
            elif field == "enable_model_toggle":
                config.enable_model_toggle = value
                runtime_set("enable_model_toggle", bool(value))
            elif field == "job_backend":
                config.job_backend = value
                runtime_set("job_backend", value)
            elif field == "redis_url":
                config.redis_url = value
                runtime_set("redis_url", value)
    
    log_system_event(
        db=db,
        user_id=user_id,
        action="admin_settings_update",
        status="success",
        detail=f"updated_fields={list(update_data.keys())}",
    )
    db.commit()
    db.refresh(config)
    
    return AdminConfigResponse(
        config_id=config.config_id,
        max_keywords_display=config.max_keywords,
        hook_analysis_duration=config.hook_duration,
        analysis_time_range_days=config.process_interval,
        notification_batch_size=config.notification_batch_size,
        youtube_region=config.youtube_region,
        google_region=config.google_region,
        tiktok_region=config.tiktok_region,
        enable_youtube_trending=config.enable_youtube_trending,
        enable_google_trends=config.enable_google_trends,
        enable_tiktok_trending=config.enable_tiktok_trending,
        auto_scan_interval_hours=config.auto_scan_interval_hours,
        created_at=config.created_at,
        updated_at=getattr(config, 'updated_at', config.created_at),
    )


def reset_admin_config(db: Session) -> AdminConfigResponse:
    """
    Reset admin configuration to defaults
    """
    config = get_or_create_admin_config(db)
    
    config.max_keywords = DEFAULT_CONFIG["max_keywords_display"]
    config.hook_duration = min(DEFAULT_CONFIG["hook_analysis_duration"], config.upload_max_duration_seconds)
    config.process_interval = DEFAULT_CONFIG["analysis_time_range_days"]
    config.notification_batch_size = DEFAULT_CONFIG["notification_batch_size"]
    config.youtube_region = DEFAULT_CONFIG["youtube_region"]
    config.google_region = DEFAULT_CONFIG["google_region"]
    config.tiktok_region = DEFAULT_CONFIG["tiktok_region"]
    config.enable_youtube_trending = DEFAULT_CONFIG["enable_youtube_trending"]
    config.enable_google_trends = DEFAULT_CONFIG["enable_google_trends"]
    config.enable_tiktok_trending = DEFAULT_CONFIG["enable_tiktok_trending"]
    config.auto_scan_interval_hours = DEFAULT_CONFIG["auto_scan_interval_hours"]
    
    db.commit()
    db.refresh(config)
    log_system_event(
        db=db,
        user_id=None,
        action="admin_settings_reset",
        status="success",
        detail="reset_to_default",
    )
    
    return AdminConfigResponse(
        config_id=config.config_id,
        max_keywords_display=config.max_keywords,
        hook_analysis_duration=config.hook_duration,
        analysis_time_range_days=config.process_interval,
        notification_batch_size=config.notification_batch_size,
        youtube_region=config.youtube_region,
        google_region=config.google_region,
        tiktok_region=config.tiktok_region,
        enable_youtube_trending=config.enable_youtube_trending,
        enable_google_trends=config.enable_google_trends,
        enable_tiktok_trending=config.enable_tiktok_trending,
        auto_scan_interval_hours=config.auto_scan_interval_hours,
        created_at=config.created_at,
        updated_at=getattr(config, 'updated_at', config.created_at),
    )


def validate_config(config_update: AdminConfigUpdate) -> Dict[str, bool]:
    """
    Validate configuration values
    Returns dict with validation result and any error messages
    """
    errors = []
    
    if config_update.max_keywords_display is not None:
        if not (1 <= config_update.max_keywords_display <= 50):
            errors.append("max_keywords_display must be between 1 and 50")
    
    if config_update.hook_analysis_duration is not None:
        if not (10 <= config_update.hook_analysis_duration <= 300):
            errors.append("hook_analysis_duration must be between 10 and 300 seconds")
    
    if config_update.analysis_time_range_days is not None:
        if not (1 <= config_update.analysis_time_range_days <= 365):
            errors.append("analysis_time_range_days must be between 1 and 365")
    
    if config_update.notification_batch_size is not None:
        if not (1 <= config_update.notification_batch_size <= 200):
            errors.append("notification_batch_size must be between 1 and 200")
    
    if config_update.auto_scan_interval_hours is not None:
        if not (1 <= config_update.auto_scan_interval_hours <= 24):
            errors.append("auto_scan_interval_hours must be between 1 and 24")
    
    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
    }


def get_admin_statistics(db: Session) -> Dict:
    """
    Calculate admin dashboard statistics
    """
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    total_analyses = db.query(UserContent).count()
    total_saved_ideas = db.query(UserContent).count()

    # Get most used dataset categories (top 5)
    category_rows = (
        db.query(
            DatasetContent.category,
            func.count(DatasetContent.dataset_id),
        )
        .group_by(DatasetContent.category)
        .order_by(func.count(DatasetContent.dataset_id).desc())
        .limit(5)
        .all()
    )
    most_used = [
        {"category": category or "uncategorized", "count": int(count)}
        for category, count in category_rows
    ]

    # Get analysis counts by category based on dataset category breakdown
    analyses_by_category = {
        item["category"]: item["count"] for item in most_used
    }

    # Get notification stats
    total_notifications = db.query(Notification).count()
    unread_notifications = db.query(Notification).filter(Notification.is_read == False).count()

    # Get followed topics
    followed_domains = db.query(FollowedTopic).filter(
        FollowedTopic.match_type == "domain"
    ).count()
    followed_keywords = db.query(FollowedTopic).filter(
        FollowedTopic.match_type == "keyword"
    ).count()

    latest_trend_log = db.query(SystemLog.timestamp)
    latest_trend_log = latest_trend_log.filter(SystemLog.action.like("%trends_sync%"))
    latest_trend_log = latest_trend_log.order_by(SystemLog.timestamp.desc()).first()
    last_trend_scan = latest_trend_log[0] if latest_trend_log else None

    latest_config_log = db.query(SystemLog.timestamp)
    latest_config_log = latest_config_log.filter(
        or_(
            SystemLog.action.like("%admin_settings%"),
            SystemLog.action.like("%settings%"),
        )
    )
    latest_config_log = latest_config_log.order_by(SystemLog.timestamp.desc()).first()
    last_config_update = latest_config_log[0] if latest_config_log else None

    config = get_or_create_admin_config(db)
    trend_data_sources_active = []
    if config.enable_youtube_trending:
        trend_data_sources_active.append("youtube")
    if config.enable_google_trends:
        trend_data_sources_active.append("google")
    if getattr(config, 'enable_tiktok_trending', False):
        trend_data_sources_active.append("tiktok")

    avg_analyses = round(total_analyses / max(total_users, 1), 2)

    return {
        "total_users": total_users,
        "active_users": active_users,
        "inactive_users": total_users - active_users,
        "total_analyses": total_analyses,
        "total_saved_ideas": total_saved_ideas,
        "avg_analyses_per_user": avg_analyses,
        "total_notifications": total_notifications,
        "unread_notifications": unread_notifications,
        "followed_domains": followed_domains,
        "followed_keywords": followed_keywords,
        "analyses_by_category": analyses_by_category,
        "most_used_categories": most_used,
        "trend_data_sources_active": trend_data_sources_active,
        "last_trend_scan": last_trend_scan,
        "last_config_update": last_config_update,
    }


def get_admin_audit_log(db: Session, limit: int = 50) -> dict:
    """
    Retrieve recent admin-related system log entries.
    """
    rows = (
        db.query(SystemLog)
        .filter(SystemLog.action.like("%admin_settings%") | SystemLog.action.like("%settings%") | SystemLog.action.like("%trends_sync%"))
        .order_by(SystemLog.timestamp.desc())
        .limit(limit)
        .all()
    )
    entries = [
        {
            "log_id": row.log_id,
            "action": row.action,
            "status": row.status,
            "detail": row.detail,
            "timestamp": row.timestamp,
        }
        for row in rows
    ]
    return {
        "total_entries": len(entries),
        "entries": entries,
    }


def export_config_backup(db: Session) -> Dict:
    """
    Export current configuration as backup
    """
    config = get_or_create_admin_config(db)
    stats = get_admin_statistics(db)
    
    backup = {
        "backup_timestamp": datetime.utcnow().isoformat(),
        "configuration": {
            "config_id": config.config_id,
            "max_keywords": config.max_keywords,
            "hook_duration": config.hook_duration,
            "process_interval": config.process_interval,
            "notification_batch_size": config.notification_batch_size,
            "youtube_region": config.youtube_region,
            "google_region": config.google_region,
            "enable_youtube_trending": config.enable_youtube_trending,
            "enable_google_trends": config.enable_google_trends,
            "auto_scan_interval_hours": config.auto_scan_interval_hours,
        },
        "statistics": stats,
    }
    log_system_event(
        db=db,
        user_id=None,
        action="admin_settings_backup",
        status="success",
        detail=f"backup_created_rows={len(backup['configuration'])}",
    )
    return backup


def apply_config_from_backup(db: Session, backup_config: Dict) -> AdminConfigResponse:
    """
    Apply configuration from backup data
    """
    config = get_or_create_admin_config(db)
    
    if "configuration" in backup_config:
        cfg = backup_config["configuration"]
        if "hook_duration" in cfg:
            AnalysisParameters(
                upload_max_duration_seconds=config.upload_max_duration_seconds,
                asr_model=config.asr_model_default,
                hook_duration_seconds=cfg["hook_duration"],
            )
        if "max_keywords" in cfg:
            config.max_keywords = cfg["max_keywords"]
        if "hook_duration" in cfg:
            config.hook_duration = cfg["hook_duration"]
        if "process_interval" in cfg:
            config.process_interval = cfg["process_interval"]
        if "notification_batch_size" in cfg:
            config.notification_batch_size = cfg["notification_batch_size"]
        if "youtube_region" in cfg:
            config.youtube_region = cfg["youtube_region"]
        if "google_region" in cfg:
            config.google_region = cfg["google_region"]
        if "enable_youtube_trending" in cfg:
            config.enable_youtube_trending = cfg["enable_youtube_trending"]
        if "enable_google_trends" in cfg:
            config.enable_google_trends = cfg["enable_google_trends"]
        if "auto_scan_interval_hours" in cfg:
            config.auto_scan_interval_hours = cfg["auto_scan_interval_hours"]
    
    db.commit()
    db.refresh(config)
    log_system_event(
        db=db,
        user_id=None,
        action="admin_settings_restore",
        status="success",
        detail="restored_from_backup",
    )
    return AdminConfigResponse(
        config_id=config.config_id,
        max_keywords_display=config.max_keywords,
        hook_analysis_duration=config.hook_duration,
        analysis_time_range_days=config.process_interval,
        notification_batch_size=config.notification_batch_size,
        youtube_region=config.youtube_region,
        google_region=config.google_region,
        enable_youtube_trending=config.enable_youtube_trending,
        enable_google_trends=config.enable_google_trends,
        auto_scan_interval_hours=config.auto_scan_interval_hours,
        created_at=config.created_at,
        updated_at=getattr(config, 'updated_at', config.created_at),
    )
