from datetime import datetime
from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field


class FollowTopicRequest(BaseModel):
    match_type: Literal['domain', 'keyword', 'category']
    value: str = Field(min_length=1, max_length=255)
    platform: Literal['all', 'youtube', 'google', 'tiktok'] = 'all'


class FollowPreferences(BaseModel):
    notification_mode: Literal['all', 'following', 'off']


class FollowedTopicItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    match_type: str
    platform: str = 'all'
    value: str
    created_at: datetime


class FollowedTopicsResponse(BaseModel):
    total: int
    items: List[FollowedTopicItem]
