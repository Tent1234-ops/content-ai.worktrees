"""Lease-based background counting of approved topics, with transactional evidence."""
from __future__ import annotations

import json
import logging
import threading
import uuid
from collections import Counter
from datetime import datetime, timedelta
from functools import lru_cache

from sqlalchemy import and_, or_

from app.database.models import (
    SystemLog, TrendTopicCount, TrendTopicEvidence, TrendTopicJob,
    TrendTopicObservation, TrendTopicVersion,
)
from app.services.trend_topic_store import packed, runtime_manifest, sha

LEASE_SECONDS = 300
MAX_ATTEMPTS = 3
_stop = threading.Event()
_thread = None
logger = logging.getLogger(__name__)


@lru_cache(maxsize=4)
def _extractor(catalog_json):
    from app.services.trend_topics import TitleTopicExtractor
    return TitleTopicExtractor(json.loads(catalog_json))


def count_observation(payload_json: str, catalog_json: str) -> tuple[list, list, dict]:
    from app.services.trend_topic_preparation import _video_id
    extractor = _extractor(catalog_json)
    items = json.loads(payload_json)
    evidence, counts, seen, ranks = [], Counter(), set(), set()
    invalid = duplicates = 0
    for item in sorted(items, key=lambda item: item.get("rank") if type(item.get("rank")) is int else 999):
        video_id = _video_id(item.get("video_url"))
        # Phase 1 can resolve a missing URL only through an unambiguous retained URL.
        if not video_id and item.get("identity_source") == "unambiguous_retained_url_lookup":
            import re
            candidate = item.get("video_id", "")
            video_id = candidate if isinstance(candidate, str) and re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate) else None
        title, rank = item.get("title"), item.get("rank")
        if not video_id or not isinstance(title, str) or not title.strip() or type(rank) is not int or not 1 <= rank <= 50:
            invalid += 1
            continue
        if video_id in seen:
            duplicates += 1
            continue
        if rank in ranks:
            invalid += 1
            continue
        seen.add(video_id)
        ranks.add(rank)
        matches = extractor.known_topics(title)
        for topic in matches:
            for span in topic["evidence"]:
                for part in [span, *span.get("context_evidence", [])]:
                    if title[part["start"]:part["end"]] != part["text"]:
                        raise ValueError("Evidence does not match the preserved title")
            counts[topic["topic_id"]] += 1
        evidence.append({"video_id": video_id, "title": title,
            "video_url": f"https://www.youtube.com/watch?v={video_id}", "rank": rank,
            "status": "matched" if matches else "unknown", "matches_json": packed(matches)})
    result = {"source_rows": len(items), "eligible_videos": len(evidence),
        "invalid_rows": invalid, "duplicate_rows": duplicates,
        "unknown_videos": sum(row["status"] == "unknown" for row in evidence),
        "quality": "complete" if invalid == 0 else "insufficient_source"}
    totals = [{"topic_id": topic["id"], "video_count": counts[topic["id"]],
               "eligible_videos": len(evidence)} for topic in extractor.catalog["topics"]]
    return evidence, totals, result


def _due(now):
    return or_(and_(TrendTopicJob.status == "pending", TrendTopicJob.available_at <= now),
               and_(TrendTopicJob.status == "processing", TrendTopicJob.lease_until <= now))


def claim_job(session_factory, *, now=None):
    now = now or datetime.utcnow()
    with session_factory() as db:
        ids = [row[0] for row in db.query(TrendTopicJob.job_id).filter(_due(now))
               .order_by(TrendTopicJob.job_id).limit(20).all()]
        for job_id in ids:
            token = str(uuid.uuid4())
            changed = db.query(TrendTopicJob).filter(TrendTopicJob.job_id == job_id, _due(now)).update({
                TrendTopicJob.status: "processing", TrendTopicJob.claim_token: token,
                TrendTopicJob.lease_until: now + timedelta(seconds=LEASE_SECONDS),
                TrendTopicJob.attempts: TrendTopicJob.attempts + 1,
            }, synchronize_session=False)
            db.commit()
            if changed:
                return job_id, token
    return None


def process_next_job(session_factory, *, now=None) -> dict:
    claim = claim_job(session_factory, now=now)
    if claim is None:
        return {"status": "idle"}
    job_id, token = claim
    try:
        with session_factory() as db:
            job = db.get(TrendTopicJob, job_id)
            source = db.get(TrendTopicObservation, job.observation_id)
            version = db.get(TrendTopicVersion, job.version_id)
            if json.loads(version.manifest_json) != runtime_manifest():
                raise ValueError("ExtractorBuildMismatch")
            if sha(packed({"catalog": json.loads(version.catalog_json),
                           "method": json.loads(version.manifest_json)})) != version.version_id:
                raise ValueError("VersionIntegrityMismatch")
            if sha(source.payload_json) != source.input_sha256 or source.status != "observed":
                raise ValueError("SourceIntegrityMismatch")
            catalog, payload = version.catalog_json, source.payload_json
        evidence, totals, summary = count_observation(payload, catalog)
        with session_factory() as db:
            # Fence expired workers: only the current lease owner may publish.
            changed = db.query(TrendTopicJob).filter_by(job_id=job_id, status="processing", claim_token=token).filter(
                TrendTopicJob.lease_until > (now or datetime.utcnow())).update({
                    "status": "completed", "completed_at": datetime.utcnow(),
                    "result_json": packed(summary), "error_code": None, "lease_until": None,
                    "claim_token": None}, synchronize_session=False)
            if not changed:
                db.rollback()
                return {"status": "lease_lost", "job_id": job_id}
            db.add_all(TrendTopicEvidence(job_id=job_id, **row) for row in evidence)
            db.add_all(TrendTopicCount(job_id=job_id, **row) for row in totals)
            db.commit()
        return {"status": "completed", "job_id": job_id, **summary}
    except Exception as exc:
        with session_factory() as db:
            job = db.get(TrendTopicJob, job_id)
            if job and job.status == "processing" and job.claim_token == token:
                code = str(exc) if str(exc) in {"ExtractorBuildMismatch", "SourceIntegrityMismatch", "VersionIntegrityMismatch"} else type(exc).__name__
                status = "failed" if job.attempts >= MAX_ATTEMPTS or code.endswith("Mismatch") else "pending"
                changed = db.query(TrendTopicJob).filter_by(job_id=job_id, status="processing", claim_token=token).update({
                    "status": status, "error_code": code, "claim_token": None, "lease_until": None,
                    "available_at": datetime.utcnow() + timedelta(seconds=30 * job.attempts)}, synchronize_session=False)
                if changed:
                    db.add(SystemLog(action="trend_topic_processing", status="error",
                        detail=packed({"job_id": job_id, "error_code": code, "attempt": job.attempts})))
                db.commit()
        logger.warning("Topic job %s failed (%s)", job_id, type(exc).__name__)
        return {"status": "error", "job_id": job_id, "error_code": type(exc).__name__}


def drain_topic_jobs(session_factory, *, max_jobs=100) -> dict:
    counts = Counter()
    for _ in range(max_jobs):
        result = process_next_job(session_factory)
        if result["status"] == "idle":
            break
        counts[result["status"]] += 1
    return {"processed": sum(counts.values()), "statuses": dict(counts)}


def start_topic_worker(session_factory):
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()

    def run():
        while not _stop.is_set():
            try:
                result = process_next_job(session_factory)
                if result["status"] != "idle":
                    continue
            except Exception:
                logger.exception("Topic worker could not access its persistent queue")
            _stop.wait(5)

    _thread = threading.Thread(target=run, name="trend-topics", daemon=True)
    _thread.start()


def stop_topic_worker():
    _stop.set()
    if _thread:
        _thread.join(timeout=10)
