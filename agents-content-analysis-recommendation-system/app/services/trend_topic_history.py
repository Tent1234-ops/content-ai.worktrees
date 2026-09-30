"""Read-only, single-version series. Missing collection or processing is never zero."""
import json
from collections import Counter
from datetime import datetime, timedelta

from app.core.datetime_utils import utc_isoformat
from app.database.models import (
    TrendTopicConfig, TrendTopicCount, TrendTopicDefinition, TrendTopicEvidence,
    TrendTopicJob, TrendTopicObservation, TrendTopicVersion,
)
from app.services.trend_topic_store import utc


def load_topic_history(db, *, region="TH", scope="global", days=5, version_id=None, now=None):
    if not 1 <= days <= 90:
        raise ValueError("Use a period of 1-90 days")
    if version_id is None:
        config = db.get(TrendTopicConfig, 1)
        version_id = config.active_version_id if config else None
    version = db.get(TrendTopicVersion, version_id) if version_id else None
    if version is None:
        return {"status": "unavailable", "version_id": version_id, "points": []}
    end = utc(now or datetime.utcnow())
    rows = db.query(TrendTopicObservation, TrendTopicJob).outerjoin(TrendTopicJob,
        (TrendTopicJob.observation_id == TrendTopicObservation.observation_id) &
        (TrendTopicJob.version_id == version_id)).filter(
        TrendTopicObservation.region == region, TrendTopicObservation.platform == "youtube",
        TrendTopicObservation.ranking_scope == scope,
        TrendTopicObservation.observed_at >= end - timedelta(days=days),
        TrendTopicObservation.observed_at <= end).order_by(
            TrendTopicObservation.observed_at, TrendTopicObservation.observation_id).all()
    topics = [{"topic_id": row.topic_id, "label": row.label} for row in db.query(TrendTopicDefinition)
              .filter_by(version_id=version_id).order_by(TrendTopicDefinition.topic_id)]
    blocked = Counter((job.status if job else "not_queued") for source, job in rows
                      if source.status == "observed" and (not job or job.status != "completed"))
    response = {"version_id": version_id, "extractor_version": version.extractor_version,
        "alias_version": version.alias_version, "platform": "youtube", "region": region,
        "ranking_scope": scope, "topics": topics, "points": [],
        "count_unit": "distinct_video_id_in_this_ranking_scope",
        "coverage": {"observations": len(rows), "processing": dict(blocked)},
        "status": "recalculation_required" if blocked else "ready" if rows else "no_observations"}
    if blocked:
        return response
    jobs = [job.job_id for _, job in rows if job]
    counts = {}
    # Bounded chunks also support long periods on SQLite's parameter limit.
    for offset in range(0, len(jobs), 500):
        for count in db.query(TrendTopicCount).filter(TrendTopicCount.job_id.in_(jobs[offset:offset+500])):
            counts.setdefault(count.job_id, {})[count.topic_id] = count.video_count
    previous = None
    for source, job in rows:
        summary = json.loads(job.result_json) if job and job.result_json else {}
        observed = source.status == "observed" and summary.get("quality") == "complete"
        values = counts.get(job.job_id, {}) if observed else None
        if observed and set(values) != {topic["topic_id"] for topic in topics}:
            return dict(response, status="incomplete_results", points=[])
        response["points"].append({"observed_at": utc_isoformat(source.observed_at),
            "observation_id": source.observation_id, "source_run_id": source.source_run_id,
            "job_id": job.job_id if job else None,
            "status": "observed" if observed else summary.get("quality", source.status),
            "counts": values, "eligible_videos": summary.get("eligible_videos") if observed else None,
            "gap_seconds_before": (source.observed_at - previous).total_seconds() if previous else None})
        previous = source.observed_at
    # Actual sample timestamps only: consumers must not forward-fill these intervals.
    response["missing_data_policy"] = "null_for_failed_or_incomplete; no_interpolation_or_synthetic_buckets"
    return response


def load_job_evidence(db, job_id):
    job = db.get(TrendTopicJob, job_id)
    if job is None:
        return None
    source = db.get(TrendTopicObservation, job.observation_id)
    return {"job_id": job_id, "version_id": job.version_id, "status": job.status,
        "source_run_id": source.source_run_id, "observed_at": utc_isoformat(source.observed_at),
        "region": source.region, "platform": source.platform, "ranking_scope": source.ranking_scope,
        "input_sha256": source.input_sha256, "source_kind": source.source_kind,
        "error_code": job.error_code, "summary": json.loads(job.result_json or "{}"),
        "evidence": [{"evidence_id": row.evidence_id, "video_id": row.video_id, "title": row.title,
            "video_url": row.video_url, "rank": row.rank, "status": row.status,
            "matches": json.loads(row.matches_json)} for row in db.query(TrendTopicEvidence)
            .filter_by(job_id=job_id).order_by(TrendTopicEvidence.rank)]}
