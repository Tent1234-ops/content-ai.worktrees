"""Explicit-manifest statistics collection for Outcome Prediction Phase 2."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from math import ceil
from typing import Any

from sqlalchemy import func

from app.database.db import SessionLocal
from app.database.models import (
    DatasetContent,
    ReferenceStatisticsConfig,
    ReferenceStatisticsRun,
    ReferenceVideoStatistic,
)
from app.services.dataset_eligibility import reference_source_matches
from app.services.outcome_dataset import verify_collection_manifest
from app.services.outcome_prediction_readiness import data_use_gate
from app.services.persistence import log_system_event
from app.services.reference_statistics import _count, _fetch
from app.services.trend_scheduler import collector_lock
from app.services.view_metrics import view_metric_version_for
from app.services.youtube_cc_dataset import YouTubeQuotaExceededError


def _used_today(db, now: datetime) -> int:
    midnight = (
        now + timedelta(hours=7)
    ).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=7)
    return int(db.query(func.coalesce(func.sum(ReferenceStatisticsRun.requests_used), 0)).filter(
        ReferenceStatisticsRun.started_at >= midnight,
        ReferenceStatisticsRun.started_at < midnight + timedelta(days=1),
    ).scalar())


def _idempotency_key(manifest_sha256: str, requested_at: datetime) -> str:
    # One explicit manifest collection per UTC hour unless the caller supplies a
    # different key through a newly frozen manifest.
    hour = requested_at.replace(minute=0, second=0, microsecond=0).isoformat()
    return hashlib.sha256(f"{manifest_sha256}:{hour}".encode()).hexdigest()


def _validated_rows(db, manifest: dict[str, Any]) -> tuple[list[DatasetContent], list[dict[str, Any]]]:
    requested = manifest.get("records") or []
    ids = [int(item["dataset_id"]) for item in requested]
    rows = db.query(DatasetContent).filter(
        DatasetContent.dataset_id.in_(ids),
        DatasetContent.deleted_at.is_(None),
        DatasetContent.is_active.is_(True),
    ).all() if ids else []
    by_id = {int(row.dataset_id): row for row in rows}
    accepted, rejected = [], []
    for item in requested:
        dataset_id = int(item["dataset_id"])
        row = by_id.get(dataset_id)
        reasons = []
        if row is None:
            reasons.append("dataset_row_missing")
        else:
            if str(row.source_youtube_id or "") != str(item.get("source_youtube_id") or ""):
                reasons.append("video_id_changed")
            if str(row.data_split or "") != str(item.get("source_split") or ""):
                reasons.append("source_split_changed")
            if not reference_source_matches(row):
                reasons.append("source_identity_invalid")
        if reasons:
            rejected.append({"dataset_id": dataset_id, "reason_codes": reasons})
        else:
            accepted.append(row)
    accepted.sort(key=lambda row: int(row.dataset_id))
    return accepted, rejected


def plan_outcome_statistics_collection(
    db,
    *,
    manifest: dict[str, Any],
    data_use_record: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    if not verify_collection_manifest(manifest):
        return {"status": "blocked", "reason_codes": ["collection_manifest_invalid"],
                "requests_planned": 0, "batches": []}
    rights = data_use_gate(data_use_record, "training")
    rows, rejected = _validated_rows(db, manifest)
    config = db.get(ReferenceStatisticsConfig, 1)
    daily_budget = int(config.daily_request_budget) if config else 100
    used = _used_today(db, now)
    remaining = max(0, daily_budget - used)
    batches = [rows[index:index + 50] for index in range(0, len(rows), 50)]
    serializable = [[str(row.source_youtube_id) for row in batch] for batch in batches]
    reasons = list(rights["reason_codes"])
    if len(batches) > remaining:
        reasons.append("daily_request_budget_insufficient")
    return {
        "status": "ready" if rights["allowed"] and not rejected and len(batches) <= remaining else "blocked",
        "reason_codes": sorted(set(reasons)),
        "manifest_sha256": manifest["manifest_sha256"],
        "candidate_count": len(rows), "rejected": rejected,
        "requests_planned": len(batches), "requests_used_today": used,
        "daily_request_budget": daily_budget, "requests_remaining": remaining,
        "batches": serializable,
        "dry_run": True, "database_writes": 0, "api_calls": 0,
    }


def collect_outcome_statistics(
    *,
    manifest: dict[str, Any],
    data_use_record: dict[str, Any],
    session_factory=SessionLocal,
    now: datetime | None = None,
    actor: str = "outcome_dataset",
    dry_run: bool = True,
    approved: bool = False,
    fetch=None,
    max_attempts: int = 2,
) -> dict[str, Any]:
    now = now or datetime.utcnow()
    if dry_run:
        with session_factory() as db:
            return plan_outcome_statistics_collection(
                db, manifest=manifest, data_use_record=data_use_record, now=now
            )
    if not approved:
        return {"status": "blocked", "reason_codes": ["explicit_live_approval_required"]}
    if max_attempts not in {1, 2, 3}:
        raise ValueError("max_attempts must be between 1 and 3")

    with collector_lock(session_factory, scope="references") as acquired:
        if not acquired:
            return {"status": "busy", "reason_codes": ["collector_lock_busy"]}
        with session_factory() as db:
            plan = plan_outcome_statistics_collection(
                db, manifest=manifest, data_use_record=data_use_record, now=now
            )
            if plan["status"] != "ready":
                return plan
            key = _idempotency_key(manifest["manifest_sha256"], now)
            existing = db.query(ReferenceStatisticsRun).filter(
                ReferenceStatisticsRun.idempotency_key == key
            ).first()
            if existing:
                return {"status": "already_collected", "run_id": existing.run_id,
                        "idempotency_key": key, "requests_used": 0}

            rows, _ = _validated_rows(db, manifest)
            run = ReferenceStatisticsRun(
                status="running", actor=actor[:32],
                purpose="outcome_statistics_collection",
                manifest_sha256=manifest["manifest_sha256"],
                idempotency_key=key,
                split_protection="manifest_declared",
                started_at=now, candidate_count=len(rows),
            )
            db.add(run)
            db.commit()
            provider = fetch or _fetch
            successful = failed = incomplete = 0
            for offset in range(0, len(rows), 50):
                batch = rows[offset:offset + 50]
                items: dict[str, Any] = {}
                error = None
                for attempt in range(max_attempts):
                    config = db.get(ReferenceStatisticsConfig, 1)
                    budget = int(config.daily_request_budget) if config else 100
                    if _used_today(db, now) >= budget:
                        error = "daily_budget"
                        break
                    run.requests_used += 1
                    db.commit()
                    try:
                        payload = provider([str(row.source_youtube_id) for row in batch])
                        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
                            raise ValueError("Invalid videos.list payload")
                        items = {
                            str(item["id"]): item for item in payload["items"]
                            if isinstance(item, dict) and item.get("id")
                        }
                        error = None
                        break
                    except YouTubeQuotaExceededError:
                        error = "provider_quota"
                        if config:
                            config.blocked_until = now + timedelta(hours=24)
                            db.commit()
                        break
                    except Exception:
                        error = "provider_error"
                        if attempt + 1 >= max_attempts:
                            break

                observed = now
                for row in batch:
                    item = items.get(str(row.source_youtube_id))
                    stats = (item or {}).get("statistics", {})
                    if not isinstance(stats, dict):
                        stats = {}
                    values = {
                        field: _count(stats.get(provider_key))
                        for field, provider_key in (
                            ("views", "viewCount"), ("likes", "likeCount"),
                            ("comments", "commentCount"),
                        )
                    }
                    state = "failed" if error else "unavailable" if item is None else (
                        "complete" if all(value is not None for value in values.values()) else "partial"
                    )
                    db.add(ReferenceVideoStatistic(
                        run_id=run.run_id, dataset_id=row.dataset_id,
                        video_id=str(row.source_youtube_id),
                        source_url=f"https://www.youtube.com/watch?v={row.source_youtube_id}",
                        observed_at=observed, status=state,
                        error_code=error or ("not_returned" if item is None else None),
                        view_metric_version=view_metric_version_for("youtube", observed),
                        **values,
                    ))
                    if state in {"complete", "partial"}:
                        successful += 1
                        incomplete += int(state == "partial")
                    else:
                        failed += 1
                db.commit()
                if error in {"provider_quota", "daily_budget"}:
                    run.error_code = error
                    break

            run.status = (
                "partial" if successful and (failed or incomplete or run.error_code)
                else "completed" if successful and not failed and not incomplete
                else "failed"
            )
            run.completed_at = now
            log_system_event(
                db, user_id=None, action="outcome_statistics_collection",
                status="success" if run.status == "completed" else "warning" if run.status == "partial" else "failed",
                detail=(f"run_id={run.run_id}; manifest={manifest['manifest_sha256']}; "
                        f"requests={run.requests_used}; observed={successful}; failed={failed}"),
            )
            db.commit()
            return {
                "status": run.status, "run_id": run.run_id,
                "manifest_sha256": run.manifest_sha256,
                "idempotency_key": key, "candidate_count": len(rows),
                "requests_used": run.requests_used, "observed": successful,
                "failed": failed, "error_code": run.error_code,
            }
