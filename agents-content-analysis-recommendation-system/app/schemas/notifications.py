from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict, field_serializer

from app.core.datetime_utils import utc_isoformat


class NotificationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    notification_id: int
    user_id: int
    watch_session_id: int
    type: str
    trend_key: str
    platform: str
    title: str
    category: str
    detected_at: datetime
    payload: str | None = None
    is_read: bool
    created_at: datetime

    @field_serializer("detected_at", "created_at", when_used="json")
    def serialize_utc_datetime(self, value: datetime) -> str:
        return utc_isoformat(value) or ""


class NotificationsResponse(BaseModel):
    total: int
    items: List[NotificationItem]


class MarkReadRequest(BaseModel):
    ids: list[int]
