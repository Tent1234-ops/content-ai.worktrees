from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database.models import DatasetContent


def list_dataset_contents(
    db: Session,
    *,
    source_prefix: str = "youtube",
    limit: int = 20,
    offset: int = 0,
    category: str | None = None,
    search: str | None = None,
):
    query = db.query(DatasetContent).filter(
        DatasetContent.source_platform.like(f"{source_prefix}%"), DatasetContent.deleted_at.is_(None),
    )

    if category:
        query = query.filter(DatasetContent.category == category)

    if search:
        like_value = f"%{search}%"
        query = query.filter(
            (DatasetContent.title.ilike(like_value))
            | (DatasetContent.transcript.ilike(like_value))
        )

    total = query.count()
    items = (
        query.order_by(
            desc(DatasetContent.published_at),
            desc(DatasetContent.trend_score),
            desc(DatasetContent.created_at),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    return total, items
