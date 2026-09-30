"""Immutable topic registries and durable source observations; no NLP or HTTP here."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from app.database.models import (
    TrendHistoryAttempt, TrendTopic, TrendTopicAlias, TrendTopicConfig,
    TrendTopicDefinition, TrendTopicJob, TrendTopicObservation, TrendTopicVersion,
)

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "data/trend_topics/catalog.v1.json"
RULE_VERSION = "approved-title-topics-v1"


def packed(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@contextmanager
def insert_savepoint(db):
    connection = db.connection()
    # sqlite3 legacy mode does not BEGIN on SELECT/SAVEPOINT. Without this,
    # releasing the first savepoint could commit despite an outer rollback.
    if connection.dialect.name == "sqlite" and not connection.connection.driver_connection.in_transaction:
        connection.exec_driver_sql("BEGIN")
    with db.begin_nested():
        yield


def utc(value) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def _build_manifest() -> dict:
    return {"extractor_version": RULE_VERSION, "input_fields": ["title"],
        "count_unit": "distinct_video_id_per_observed_ranking_scope",
        "discovery_candidates_included": False,
        "libraries": {name: version(name) for name in ("pythainlp", "scikit-learn")},
        "code_sha256": {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                        for name in ("trend_topics.py", "trend_topic_processing.py", "trend_topic_store.py")}}


_RUNNING_MANIFEST = _build_manifest()


def runtime_manifest() -> dict:
    # An old Python process must not label its in-memory code as a newly edited build.
    if _build_manifest() != _RUNNING_MANIFEST:
        raise ValueError("ExtractorBuildMismatch")
    return json.loads(packed(_RUNNING_MANIFEST))


def validate_catalog(catalog: dict) -> None:
    if not isinstance(catalog.get("version"), str) or not 1 <= len(catalog["version"]) <= 100:
        raise ValueError("An alias version is required")
    ids, aliases = set(), set()
    if not isinstance(catalog.get("topics"), list) or not catalog["topics"]:
        raise ValueError("An approved catalog must contain topics")
    for topic in catalog["topics"]:
        key = topic.get("id", "")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", key) or key in ids:
            raise ValueError("Stable topic IDs must be unique lowercase identifiers")
        ids.add(key)
        if not isinstance(topic.get("label"), str) or not 1 <= len(topic["label"].strip()) <= 255:
            raise ValueError("Invalid topic label")
        if not isinstance(topic.get("kind", "object"), str) or len(topic.get("kind", "object")) > 64:
            raise ValueError("Invalid topic kind")
        if not topic.get("aliases"):
            raise ValueError("An approved topic must have aliases")
        for alias in topic["aliases"]:
            text = alias.get("text", "")
            if not isinstance(text, str) or not 1 <= len(text.strip()) <= 255:
                raise ValueError("Invalid alias text")
            normalized = " ".join(unicodedata.normalize("NFKC", text).casefold().split())
            if normalized in aliases:
                raise ValueError("Duplicate or ambiguous alias")
            aliases.add(normalized)
            for field in ("context_any", "exclude_any"):
                values = alias.get(field, [])
                if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
                    raise ValueError("Context rules must be nonempty strings")
    for pair in catalog.get("never_merge", []):
        if len(pair) != 2 or len(set(pair)) != 2 or not set(pair) <= ids:
            raise ValueError("Invalid never-merge pair")


def register_version(db, catalog: dict | None = None) -> TrendTopicVersion:
    catalog = catalog if catalog is not None else json.loads(CATALOG.read_text(encoding="utf-8"))
    validate_catalog(catalog)
    manifest = runtime_manifest()
    version_id = sha(packed({"catalog": catalog, "method": manifest}))
    existing = db.get(TrendTopicVersion, version_id)
    if existing:
        return existing
    try:
        with insert_savepoint(db):
            row = TrendTopicVersion(version_id=version_id, extractor_version=RULE_VERSION,
                alias_version=catalog["version"], catalog_json=packed(catalog), manifest_json=packed(manifest))
            db.add(row)
            db.flush()
            for topic in catalog["topics"]:
                if db.get(TrendTopic, topic["id"]) is None:
                    db.add(TrendTopic(topic_id=topic["id"]))
                    db.flush()
                db.add(TrendTopicDefinition(version_id=version_id, topic_id=topic["id"],
                    label=topic["label"], kind=topic.get("kind", "object")))
                for alias in topic["aliases"]:
                    normalized = " ".join(unicodedata.normalize("NFKC", alias["text"]).casefold().split())
                    db.add(TrendTopicAlias(version_id=version_id, topic_id=topic["id"],
                        alias_hash=sha(normalized), text=alias["text"], rules_json=packed(alias)))
            db.flush()
        return row
    except IntegrityError:
        existing = db.get(TrendTopicVersion, version_id)
        if existing is None:
            raise
        return existing


def active_version(db) -> TrendTopicVersion:
    config = db.get(TrendTopicConfig, 1)
    if config:
        return db.get(TrendTopicVersion, config.active_version_id)
    row = register_version(db)
    try:
        with insert_savepoint(db):
            db.add(TrendTopicConfig(config_id=1, active_version_id=row.version_id))
            db.flush()
    except IntegrityError:
        pass
    return db.get(TrendTopicVersion, db.get(TrendTopicConfig, 1).active_version_id)


def enqueue_observation(db, observation: TrendTopicObservation, version_id: str) -> bool:
    if observation.status != "observed":
        return False
    exists = db.query(TrendTopicJob).filter_by(
        observation_id=observation.observation_id, version_id=version_id).first()
    if exists:
        # Reactivating an older catalog must resume jobs cancelled on switching,
        # while completed evidence stays immutable and failed work stays visible.
        if exists.status == "superseded":
            return bool(db.query(TrendTopicJob).filter_by(job_id=exists.job_id, status="superseded").update({
                "status": "pending", "available_at": datetime.utcnow(), "claim_token": None,
                "lease_until": None}, synchronize_session=False))
        return False
    try:
        with insert_savepoint(db):
            db.add(TrendTopicJob(observation_id=observation.observation_id, version_id=version_id))
            db.flush()
        return True
    except IntegrityError:
        return False


def activate_version(db, version_id: str) -> int:
    row = db.get(TrendTopicVersion, version_id)
    if row is None or json.loads(row.manifest_json) != runtime_manifest():
        raise ValueError("Version is unavailable or requires a different extractor build")
    config = db.get(TrendTopicConfig, 1)
    if config is None:
        db.add(TrendTopicConfig(config_id=1, active_version_id=version_id))
    else:
        config.active_version_id = version_id
    db.flush()
    # A changed build cannot finish old-rule jobs. Preserve their audit records,
    # but fence them off instead of repeatedly running incompatible queued work.
    db.query(TrendTopicJob).filter(TrendTopicJob.version_id != version_id,
        TrendTopicJob.status.in_(["pending", "processing"])).update({
            "status": "superseded", "claim_token": None, "lease_until": None}, synchronize_session=False)
    # Enqueue the whole retained period, never copy old-version counts.
    return sum(enqueue_observation(db, row, version_id)
               for row in observation_batches(db.query(TrendTopicObservation).filter_by(status="observed")))


def observation_batches(query):
    # MySQL cannot issue writes while a yield_per/unbuffered result is open.
    after = 0
    while True:
        rows = query.filter(TrendTopicObservation.observation_id > after).order_by(
            TrendTopicObservation.observation_id).limit(200).all()
        if not rows:
            return
        yield from rows
        after = rows[-1].observation_id


def store_observation(db, *, run_id: int, region: str, scope: str, observed_at,
                      items: list, status="observed", source_kind="snapshot", version_id=None):
    identity = dict(source_run_id=run_id, region=region, platform="youtube", ranking_scope=scope)
    row = db.query(TrendTopicObservation).filter_by(**identity).first()
    if row is None:
        payload = packed(items)
        try:
            with insert_savepoint(db):
                row = TrendTopicObservation(**identity, observed_at=utc(observed_at),
                    source_kind=source_kind, status=status, payload_json=payload, input_sha256=sha(payload))
                db.add(row)
                db.flush()
        except IntegrityError:
            row = db.query(TrendTopicObservation).filter_by(**identity).one()
    # Replays never overwrite the original title, rank, timestamp or source status.
    if row.status == "observed":
        enqueue_observation(db, row, version_id or active_version(db).version_id)
    return row


def capture_snapshot_topics(db, run, samples) -> None:
    by_scope = {scope: sample for platform, scope, sample in samples if platform == "youtube"}
    db.flush()
    attempts = db.query(TrendHistoryAttempt).filter_by(run_id=run.run_id, platform="youtube").all()
    for attempt in attempts:
        sample = by_scope.get(attempt.ranking_scope)
        status = attempt.status if attempt.status != "observed" or sample is not None else "missing_source"
        store_observation(db, run_id=run.run_id, region=run.region, scope=attempt.ranking_scope,
            observed_at=run.completed_at, items=sample["items"] if sample else [], status=status)


def backfill_topic_observations(db, *, region="TH", days=90, now=None, version_id=None) -> dict:
    from app.services.trend_topic_preparation import inspect_topic_sources
    _, _, observations = inspect_topic_sources(db, region=region, days=days, now=now)
    before = db.query(TrendTopicObservation).count()
    selected = version_id or active_version(db).version_id
    for sample in observations:
        if sample["platform"] == "youtube":
            store_observation(db, run_id=sample["run_id"], region=region, scope=sample["ranking_scope"],
                observed_at=sample["observed_at"], items=sample["items"], source_kind=sample["source"],
                version_id=selected)
    from datetime import timedelta
    end = utc(now or datetime.utcnow())
    attempts = db.query(TrendHistoryAttempt).filter(
        TrendHistoryAttempt.region == region, TrendHistoryAttempt.platform == "youtube",
        TrendHistoryAttempt.observed_at >= end - timedelta(days=days),
        TrendHistoryAttempt.observed_at <= end).all()
    for attempt in attempts:
        store_observation(db, run_id=attempt.run_id, region=region, scope=attempt.ranking_scope,
            observed_at=attempt.observed_at, items=[], source_kind="attempt",
            status="missing_source" if attempt.status == "observed" else attempt.status,
            version_id=selected)
    # Sources already preserved here may outlive the original archive retention.
    for observation in observation_batches(db.query(TrendTopicObservation).filter(
        TrendTopicObservation.region == region, TrendTopicObservation.observed_at >= end - timedelta(days=days),
        TrendTopicObservation.observed_at <= end)):
        enqueue_observation(db, observation, selected)
    db.flush()
    return {"new_observations": db.query(TrendTopicObservation).count() - before, "version_id": selected}
