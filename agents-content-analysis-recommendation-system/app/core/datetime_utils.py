from datetime import datetime, timezone


def utc_isoformat(value: datetime | None) -> str | None:
    """Serialize database UTC datetimes with an explicit timezone marker."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
