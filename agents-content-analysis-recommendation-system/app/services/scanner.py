from typing import Dict

from sqlalchemy.orm import Session


def _disabled_result() -> Dict[str, object]:
    return {
        "status": "disabled",
        "items_processed": 0,
        "notifications_created": 0,
        "reason": "Followed-topic alerts were replaced by login-session live-trend notifications.",
    }


def scan_youtube_trends(
    db: Session,
    *,
    region: str | None = None,
    limit: int = 20,
    mode: str = "auto",
) -> Dict[str, object]:
    return _disabled_result()


def scan_tiktok_trends(
    db: Session,
    *,
    region: str | None = None,
    limit: int = 20,
    mode: str = "auto",
) -> Dict[str, object]:
    return _disabled_result()


def scan_google_trends(
    db: Session,
    *,
    region: str | None = None,
    limit: int = 20,
    mode: str = "auto",
) -> Dict[str, object]:
    return _disabled_result()
