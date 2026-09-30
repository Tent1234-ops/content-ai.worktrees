from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


YOUTUBE_VIEW_METRIC_CHANGE_AT = datetime(2026, 8, 24, tzinfo=timezone.utc)

YOUTUBE_QUALIFIED_VIEW_V1 = "youtube_qualified_view_v1"
YOUTUBE_PLAY_START_VIEW_V2 = "youtube_play_start_view_v2"
GOOGLE_INTEREST_V1 = "google_interest_v1"
TIKTOK_PUBLIC_VIEW_V1 = "tiktok_public_view_v1"
PROVIDER_NATIVE_V1 = "provider_native_v1"
UNKNOWN_VIEW_METRIC = "unknown_v1"

KNOWN_VIEW_METRIC_VERSIONS = {
    YOUTUBE_QUALIFIED_VIEW_V1,
    YOUTUBE_PLAY_START_VIEW_V2,
    GOOGLE_INTEREST_V1,
    TIKTOK_PUBLIC_VIEW_V1,
    PROVIDER_NATIVE_V1,
    UNKNOWN_VIEW_METRIC,
}


def _as_utc(value: Any) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value).strip()
        if not raw:
            return datetime.now(timezone.utc)
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def platform_family(platform: str | None) -> str:
    value = str(platform or "").strip().lower()
    for family in ("youtube", "google", "tiktok"):
        if value.startswith(family):
            return family
    return value or "provider"


def view_metric_version_for(
    platform: str | None,
    captured_at: Any = None,
) -> str:
    family = platform_family(platform)
    if family == "youtube":
        return (
            YOUTUBE_QUALIFIED_VIEW_V1
            if _as_utc(captured_at) < YOUTUBE_VIEW_METRIC_CHANGE_AT
            else YOUTUBE_PLAY_START_VIEW_V2
        )
    if family == "google":
        return GOOGLE_INTEREST_V1
    if family == "tiktok":
        return TIKTOK_PUBLIC_VIEW_V1
    return PROVIDER_NATIVE_V1


def resolve_view_metric_version(
    platform: str | None,
    captured_at: Any = None,
    explicit_version: Any = None,
) -> str:
    explicit = str(explicit_version or "").strip()
    if explicit in KNOWN_VIEW_METRIC_VERSIONS and explicit != UNKNOWN_VIEW_METRIC:
        return explicit
    return view_metric_version_for(platform, captured_at)


def view_metrics_are_comparable(
    platform: str | None,
    current_version: str | None,
    previous_version: str | None,
) -> bool:
    current = str(current_version or "").strip()
    previous = str(previous_version or "").strip()
    if not current or not previous:
        return False
    if UNKNOWN_VIEW_METRIC in {current, previous}:
        return False
    if platform_family(platform) == "youtube":
        return current == previous
    return current == previous

