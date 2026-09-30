"""
Simple in-memory TTL cache for lightweight dashboard caching.
Not suitable for multi-process deployments. Use Redis for production.
"""
from datetime import datetime, timedelta
from typing import Any, Dict, Tuple

_store: Dict[str, Tuple[datetime, Any]] = {}


def get(key: str):
    entry = _store.get(key)
    if not entry:
        return None
    expires_at, value = entry
    if datetime.utcnow() >= expires_at:
        try:
            del _store[key]
        except KeyError:
            pass
        return None
    return value


def set(key: str, value: Any, ttl_seconds: int = 60):
    expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
    _store[key] = (expires_at, value)


def invalidate(key: str):
    try:
        del _store[key]
    except KeyError:
        pass


def invalidate_prefix(prefix: str):
    keys_to_remove = [key for key in _store.keys() if key.startswith(prefix)]
    for key in keys_to_remove:
        del _store[key]


def clear():
    _store.clear()
