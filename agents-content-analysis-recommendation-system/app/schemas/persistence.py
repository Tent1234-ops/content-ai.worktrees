from pydantic import BaseModel


class TrendSyncResponse(BaseModel):
    created: int
    updated: int
    notifications: int = 0
    mode: str
    region: str
    total_fetched: int
