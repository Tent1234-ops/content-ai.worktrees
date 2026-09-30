"""Saved analysis counts, bucketed by calendar date in Thailand."""
from calendar import monthrange
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.database.models import AnalysisResult, UserContent

BANGKOK_OFFSET = timedelta(hours=7)


def usage_statistics(db: Session, *, user_id: int | None, year: int,
                     month: int | None = None, now: datetime | None = None) -> dict:
    current_year = ((now or datetime.utcnow()) + BANGKOK_OFFSET).year
    if not 2000 <= year <= current_year or (month is not None and not 1 <= month <= 12):
        raise ValueError("Invalid statistics period")
    start = datetime(year, month or 1, 1)
    end = (datetime(year + 1, 1, 1) if month is None or month == 12
           else datetime(year, month + 1, 1))
    rows = db.query(
        AnalysisResult.created_at, AnalysisResult.taxonomy_leaf_key,
        AnalysisResult.category_level_3, AnalysisResult.classification_is_unknown,
    ).join(UserContent, AnalysisResult.content_id == UserContent.content_id).filter(
        AnalysisResult.created_at >= start - BANGKOK_OFFSET,
        AnalysisResult.created_at < end - BANGKOK_OFFSET,
    )
    if user_id is not None:
        rows = rows.filter(UserContent.user_id == user_id)
    counts, categories = Counter(), Counter()
    for created_at, leaf, label, unknown in rows.yield_per(1000):
        local = created_at + BANGKOK_OFFSET
        counts[local.day if month else local.month] += 1
        categories["unknown" if unknown else (leaf or label or "unknown")] += 1
    size = monthrange(year, month)[1] if month else 12
    return {
        "scope": "personal" if user_id is not None else "all_users",
        "time_zone": "Asia/Bangkok", "year": year, "month": month,
        "total": sum(counts.values()),
        "series": [{"index": i, "count": counts[i]} for i in range(1, size + 1)],
        "categories": [{"category": key, "count": count}
                       for key, count in sorted(categories.items(), key=lambda x: (-x[1], x[0]))],
    }
