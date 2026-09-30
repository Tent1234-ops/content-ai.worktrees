"""Read stored collection outcomes, without probing providers or exposing keys."""
from datetime import datetime, timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.datetime_utils import utc_isoformat
from app.database.models import TrendHistoryAttempt


def source_health(db: Session, *, now: datetime | None = None) -> dict:
    now = now or datetime.utcnow()
    scopes = [("youtube", "global"), ("google", "global")] + [
        ("youtube", f"category:{key}") for key in settings.youtube_trend_category_ids]
    items = []
    for platform, scope in scopes:
        query = db.query(TrendHistoryAttempt).filter(
            TrendHistoryAttempt.region == settings.youtube_region,
            TrendHistoryAttempt.platform == platform,
            TrendHistoryAttempt.ranking_scope == scope,
            TrendHistoryAttempt.observed_at <= now)
        latest = query.order_by(TrendHistoryAttempt.observed_at.desc(), TrendHistoryAttempt.id.desc()).first()
        success = query.filter(TrendHistoryAttempt.status == "observed").order_by(
            TrendHistoryAttempt.observed_at.desc(), TrendHistoryAttempt.id.desc()).first()
        counts = dict(query.filter(TrendHistoryAttempt.observed_at >= now - timedelta(hours=24)).with_entities(
            TrendHistoryAttempt.status, func.count(TrendHistoryAttempt.id)).group_by(TrendHistoryAttempt.status).all())
        status = "no_data" if latest is None else (
            "failed" if latest.status == "failed" else
            "excluded_mock" if latest.status == "excluded_mock" else
            "stale" if now - latest.observed_at > timedelta(hours=24) else
            "empty" if latest.sample_count == 0 else "observed")
        items.append({"platform": platform, "scope": scope, "status": status,
                      "last_attempt_at": utc_isoformat(latest.observed_at) if latest else None,
                      "last_success_at": utc_isoformat(success.observed_at) if success else None,
                      "last_run_id": latest.run_id if latest else None,
                      "sample_count": latest.sample_count if latest else None,
                      "failed_24h": counts.get("failed", 0), "observed_24h": counts.get("observed", 0)})
    return {"checked_at": utc_isoformat(now), "region": settings.youtube_region,
            "stale_after_hours": 24, "items": items}
