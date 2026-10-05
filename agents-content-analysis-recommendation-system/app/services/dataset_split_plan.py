"""Append-only, metadata-selected channel holdouts; never select using predictions."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict

from sqlalchemy import inspect, select

from app.database.models import DatasetContent, DatasetSplitPlan, ModelTrainingRun, SystemLog, User
from app.services.dataset_contract import HOLDOUT_SPLIT_STRATEGY, channel_dataset_split


def plan_digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True,
                                     separators=(",", ":")).encode()).hexdigest()


def load_split_registry(db):
    connection = db.connection() if hasattr(db, "connection") and callable(db.connection) else db
    if not inspect(connection).has_table(DatasetSplitPlan.__tablename__):
        return {"overrides": {}, "plans": []}
    rows = connection.execute(select(DatasetSplitPlan.__table__).order_by(
        DatasetSplitPlan.created_at, DatasetSplitPlan.plan_version)).mappings()
    overrides, plans = {}, []
    for row in rows:
        payload = json.loads(row["payload_json"])
        if (plan_digest(payload) != row["plan_sha256"]
                or payload.get("version") != row["plan_version"]
                or payload.get("strategy") != HOLDOUT_SPLIT_STRATEGY):
            raise ValueError("Dataset split registry checksum/version mismatch")
        for channel, split in payload["overrides"].items():
            channel_dataset_split(channel, overrides={channel: split})
            if channel in overrides and overrides[channel] != split:
                raise ValueError("Conflicting immutable channel holdouts")
            overrides[channel] = split
        plans.append({"version": row["plan_version"], "sha256": row["plan_sha256"]})
    return {"overrides": overrides, "plans": plans}


def _inventory(rows):
    fields = ("dataset_id", "source_channel_id", "source_youtube_id", "transcript_sha256",
              "taxonomy_leaf_key", "data_split", "split_strategy", "creator_group_key",
              "is_active", "is_training_eligible", "is_keyword_recommendation_eligible",
              "is_duration_recommendation_eligible", "deleted_at")
    return [{key: (str(getattr(row, key)) if key == "deleted_at" and getattr(row, key)
                   else getattr(row, key)) for key in fields}
            for row in sorted(rows, key=lambda r: r.dataset_id)]


def propose_scope_holdout_plan(db, *, version):
    from app.services.classification_acceptance import MIN_UNKNOWN_CHANNELS, MIN_UNKNOWN_VALIDATION
    from app.services.classification_training import PHASE22_MINIMUM_OUT_OF_SCOPE_SAMPLES
    from app.services.dataset_eligibility import out_of_scope_evaluation_query, production_transcript_query

    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", version):
        raise ValueError("Invalid split plan version")
    registry = load_split_registry(db)
    if any(p["version"] == version for p in registry["plans"]):
        raise ValueError("Split plan version already exists")
    rows = db.query(DatasetContent).order_by(DatasetContent.dataset_id).all()
    unknown = out_of_scope_evaluation_query(db).all()
    known = [r for r in production_transcript_query(db).all()
             if r.taxonomy_leaf_key in ("phone", "camera", "laptop")]
    groups = defaultdict(list)
    for row in unknown:
        groups[row.source_channel_id].append(row)
    for row in rows:
        if row.source_channel_id not in groups:
            continue
        expected, key = channel_dataset_split(row.source_channel_id, overrides=registry["overrides"])
        if row.data_split != expected or row.creator_group_key != key:
            raise ValueError("Resolve existing channel partition conflicts before planning")
    counts = Counter(r.data_split for r in unknown)
    needed = (max(0, MIN_UNKNOWN_VALIDATION - counts["validation"]),
              max(0, PHASE22_MINIMUM_OUT_OF_SCOPE_SAMPLES - counts["test"]))
    known_counts = Counter(r.source_channel_id for r in known if r.data_split == "train")
    candidates = sorted((c for c, rs in groups.items() if rs[0].data_split == "train"),
                        key=lambda c: hashlib.sha256(("scope-holdout-v1:" + c).encode()).hexdigest())
    # Exact-size dynamic programming preserves the most known training rows.
    # Only channel identities and counts enter selection, never text or scores.
    states = {(0, 0): (0, {})}
    for channel in candidates:
        size = len(groups[channel])
        next_states = dict(states)
        for (v, t), (cost, assignments) in states.items():
            for split, key in (("validation", (v + size, t)), ("test", (v, t + size))):
                if key[0] > needed[0] or key[1] > needed[1]:
                    continue
                candidate = (cost + known_counts[channel], {**assignments, channel: split})
                if key not in next_states or candidate[0] < next_states[key][0]:
                    next_states[key] = candidate
        states = next_states
    if needed not in states:
        raise ValueError("Cannot meet Unknown holdouts without splitting channels or moving existing holdouts")
    overrides = states[needed][1]
    if not overrides:
        raise ValueError("Existing Unknown holdouts already meet the sample targets")
    combined = {**registry["overrides"], **overrides}
    summary = {}
    for label, selected in (("unknown", unknown), *[(k, [r for r in known if r.taxonomy_leaf_key == k])
                                                    for k in ("phone", "camera", "laptop")]):
        summary[label] = dict(Counter(channel_dataset_split(r.source_channel_id, overrides=combined)[0]
                                      for r in selected))
    for split in ("validation", "test"):
        channels = {r.source_channel_id for r in unknown
                    if channel_dataset_split(r.source_channel_id, overrides=combined)[0] == split}
        if len(channels) < MIN_UNKNOWN_CHANNELS:
            raise ValueError("Unknown holdout channel diversity is insufficient")
    before = _inventory(rows)
    changes = [{**record, "new_split": overrides[record["source_channel_id"]]}
               for record in before if record["source_channel_id"] in overrides]
    return {"version": version, "strategy": HOLDOUT_SPLIT_STRATEGY,
            "inventory_sha256": plan_digest(before), "previous_plans": registry["plans"],
            "selection": "metadata_only_exact_unknown_targets_minimize_known_train_removal",
            "predictions_used": False, "fresh_external_test": False,
            "evaluation_note": "Repartitioned benchmark; some known holdouts were trained on by older models. "
                               "All candidates must be trained from scratch. Not a fresh external evaluation.",
            "unknown_targets": {"validation": MIN_UNKNOWN_VALIDATION,
                                "test": PHASE22_MINIMUM_OUT_OF_SCOPE_SAMPLES},
            "overrides": overrides, "changes": changes, "counts_after": summary,
            "unknown_dataset_ids": sorted(r.dataset_id for r in unknown)}


def apply_scope_holdout_plan(db, payload, *, expected_sha256, user_id):
    admin = db.get(User, user_id)
    if admin is None or admin.role != "admin" or not admin.is_active:
        raise ValueError("An active admin must approve the split plan")
    if plan_digest(payload) != expected_sha256:
        raise ValueError("Split plan checksum differs from the approved preview")
    if db.query(ModelTrainingRun).filter(ModelTrainingRun.active_slot == 1).first():
        raise ValueError("Cannot change partitions during training")
    rows = db.query(DatasetContent).order_by(DatasetContent.dataset_id).with_for_update().all()
    if plan_digest(_inventory(rows)) != payload["inventory_sha256"]:
        raise ValueError("Dataset changed; generate and approve a new preview")
    expected = propose_scope_holdout_plan(db, version=payload["version"])
    if expected != payload:
        raise ValueError("Plan differs from the deterministic metadata-only proposal")
    db.add(DatasetSplitPlan(plan_version=payload["version"], plan_sha256=expected_sha256,
                           payload_json=json.dumps(payload, ensure_ascii=True, sort_keys=True), created_by=user_id))
    for row in rows:
        if row.source_channel_id in payload["overrides"]:
            if row.data_split != "train":
                raise ValueError("Existing holdouts must never move")
            row.data_split, row.creator_group_key = channel_dataset_split(
                row.source_channel_id, overrides=payload["overrides"])
            row.split_strategy = HOLDOUT_SPLIT_STRATEGY
    db.flush()
    from app.services.classification_training import prepare_classification_dataset
    report = prepare_classification_dataset(db, required_leaf_keys=("phone", "camera", "laptop")).report
    if not report["ready"] or not report["partition_integrity_passed"]:
        raise ValueError("Proposed partitions do not pass dataset integrity/readiness")
    db.add(SystemLog(user_id=user_id, action="dataset_scope_holdout_plan_applied", status="success",
                     detail=json.dumps({"version": payload["version"], "sha256": expected_sha256,
                                        "counts_after": payload["counts_after"], "models_activated": False})))
    db.commit()
    return report
