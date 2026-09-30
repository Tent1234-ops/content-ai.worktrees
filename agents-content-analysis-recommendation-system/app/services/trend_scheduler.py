"""Single-owner, restart-safe hourly collections shared by API and external runner."""
import hashlib
import json
import threading
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.database.models import TrendCollectionSlot
from app.services.admin_settings import get_or_create_admin_config
from app.services.persistence import log_system_event
from app.services.trend_settings import trend_schedule

_local_lock = threading.Lock()
_reference_lock = threading.Lock()


@contextmanager
def collector_lock(session_factory, *, scope="trends"):
    with session_factory() as db:
        engine = db.get_bind()
    if engine.dialect.name == "mysql":
        name = "content_ai_" + scope + "_" + hashlib.sha256(
            f"{engine.url.database}:{settings.youtube_region}".encode()).hexdigest()[:32]
        # Named locks belong to this dedicated connection, not short-lived ORM sessions.
        with engine.connect() as connection:
            acquired = connection.execute(text("SELECT GET_LOCK(:name, 0)"), {"name": name}).scalar() == 1
            try:
                yield acquired
            finally:
                if acquired:
                    connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": name})
    else:
        lock = _reference_lock if scope == "references" else _local_lock
        acquired = lock.acquire(blocking=False)
        try:
            yield acquired
        finally:
            if acquired:
                lock.release()


def _worker_status(session_factory, status):
    with session_factory() as db:
        config = get_or_create_admin_config(db)
        config.trend_worker_seen_at = datetime.utcnow()
        config.trend_worker_status = status
        db.commit()


def run_hourly_collection(*, session_factory, now=None, actor="backend",
                          global_fetch, category_fetch) -> dict:
    now = now or datetime.utcnow()
    with session_factory() as db:
        schedule = trend_schedule(db, now=now)
        if not schedule["enabled"]:
            return {"status": "paused", "executed": []}
        if schedule["schedule_mode"] != "hourly_window":
            return {"status": "interval_mode", "executed": []}
        window = schedule["window"]
        if not window["due"]:
            return {"status": "not_due", "executed": []}
        scheduled = datetime.fromisoformat(window["current_slot"].removesuffix("Z"))
        # Persist the claim before making network requests. A second process cannot
        # collect this slot even if the first process crashes or is restarted.
        row = TrendCollectionSlot(region=settings.youtube_region, scheduled_for=scheduled,
                                  actor=actor, status="running", started_at=now)
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return {"status": "already_claimed", "executed": []}
        slot_id = row.id

    executed, results = [], {}
    for kind, fetch in (("global", global_fetch), ("youtube_categories", category_fetch)):
        with session_factory() as db:
            current = trend_schedule(db, now=now)
        if not current["enabled"] or current["schedule_mode"] != "hourly_window":
            results[kind] = {"status": "cancelled"}
            continue
        try:
            result = fetch()
            executed.append(kind)
            # Store only a safe summary, never provider URLs, API keys or huge payloads.
            results[kind] = {"status": result.get("status", "failed"),
                             "run_id": result.get("run_id"),
                             "total_items": result.get("total_items", 0)}
        except Exception as exc:
            results[kind] = {"status": "failed", "error_type": type(exc).__name__}
    states = [r["status"] for r in results.values()]
    status = "completed" if all(s == "completed" for s in states) else (
        "partial" if any(s in {"completed", "partial"} for s in states) else "failed")
    with session_factory() as db:
        row = db.get(TrendCollectionSlot, slot_id)
        row.status, row.completed_at = status, datetime.utcnow()
        row.result_json = json.dumps(results)
        log_system_event(db=db, user_id=None, action="trend_scheduled_collection",
                         status="success" if status == "completed" else "failed",
                         detail=json.dumps({"slot_id": slot_id, "scheduled_for": scheduled.isoformat() + "Z",
                                            "actor": actor, "status": status, "results": results}))
        db.commit()
    return {"status": status, "slot_id": slot_id, "executed": executed, "results": results}


def collect_due(*, session_factory, now=None, actor="backend", global_fetch, category_fetch,
                interval_runner=None, reference_fetch=None) -> dict:
    try:
        with collector_lock(session_factory) as acquired:
            if not acquired:
                result = {"status": "busy", "executed": []}
            else:
                with session_factory() as db:
                    mode = trend_schedule(db, now=now)["schedule_mode"]
                if mode == "interval" and actor == "backend" and interval_runner:
                    result = {"status": "interval_mode", "executed": interval_runner()}
                else:
                    result = run_hourly_collection(session_factory=session_factory, now=now, actor=actor,
                                                  global_fetch=global_fetch, category_fetch=category_fetch)
                if reference_fetch:
                    result["reference_statistics"] = reference_fetch()
        if actor == "task_scheduler":
            _worker_status(session_factory, result["status"])
        return result
    except Exception:
        if actor == "task_scheduler":
            _worker_status(session_factory, "failed")
        raise
