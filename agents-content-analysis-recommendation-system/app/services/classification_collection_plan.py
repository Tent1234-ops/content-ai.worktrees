"""Read-only collection planning; counts are not proof of model quality."""
from __future__ import annotations

import re
from collections import defaultdict

from sqlalchemy.orm import Session

from app.database.models import DatasetContent
from app.services.classification_acceptance import MIN_UNKNOWN_CHANNELS, MIN_UNKNOWN_TEST, MIN_UNKNOWN_VALIDATION
from app.services.classification_training import PHASE22_MINIMUM_OUT_OF_SCOPE_SAMPLES
from app.services.dataset_contract import SPLIT_STRATEGY, channel_dataset_split


def build_collection_plan(report: dict, *, enforce_phase22_gate: bool = True) -> dict:
    phase = report["phase22"]
    known = {r["leaf_key"]: r for r in report["by_leaf"]}
    rows = []
    for row in phase["by_leaf"]:
        minimum = row["minimum_sample_count"] if enforce_phase22_gate else known[row["leaf_key"]]["minimum_required"]
        channels = row["minimum_unique_channels"] if enforce_phase22_gate else 0
        rows.append({"leaf_key": row["leaf_key"], "split": "all", "current": row["sample_count"],
                     "minimum": minimum, "missing": max(0, minimum - row["sample_count"]),
                     "channels": row["unique_channels"], "minimum_channels": channels,
                     "missing_channels": max(0, channels - row["unique_channels"])})
    unknown = report["unknown_support"]
    test_minimum = max(MIN_UNKNOWN_TEST, PHASE22_MINIMUM_OUT_OF_SCOPE_SAMPLES) if enforce_phase22_gate else MIN_UNKNOWN_TEST
    for split, minimum in (("validation", MIN_UNKNOWN_VALIDATION), ("test", test_minimum)):
        count = unknown["split_counts"].get(split, 0)
        channels = unknown["channel_counts"].get(split, 0)
        rows.append({"leaf_key": "unknown", "split": split, "current": count, "minimum": minimum,
                     "missing": max(0, minimum - count), "channels": channels,
                     "minimum_channels": MIN_UNKNOWN_CHANNELS,
                     "missing_channels": max(0, MIN_UNKNOWN_CHANNELS - channels)})
    for row in rows:
        row["additional_minimum"] = max(row["missing"], row["missing_channels"])
    return {
        "version": "scope-collection-v1", "enforce_phase22_gate": enforce_phase22_gate,
        "rows": rows, "additional_minimum": sum(r["additional_minimum"] for r in rows),
        "collection_ready": bool(report["ready"]) and all(r["missing"] == 0 and r["missing_channels"] == 0 for r in rows),
        "activation_requires_evaluation": True,
        "unknown_train_reserved_count": unknown["split_counts"].get("train", 0),
        "unknown_total_minimum": MIN_UNKNOWN_VALIDATION + test_minimum,
        "diagnostic_unknown_minimum": MIN_UNKNOWN_VALIDATION + MIN_UNKNOWN_TEST,
        "fresh_test_recommendation_per_known_label": 10,
        "fresh_test_independence": "requires_provenance_review_not_inferred_from_counts",
        "split_strategy": SPLIT_STRATEGY,
    }


def preview_collection_channels(db: Session, channel_ids: list[str]) -> dict:
    ids = list(dict.fromkeys(str(value).strip() for value in channel_ids))
    if not 1 <= len(channel_ids) <= 50 or any(not re.fullmatch(r"UC[A-Za-z0-9_-]{22}", value) for value in ids):
        raise ValueError("Provide 1-50 YouTube channel IDs in UC... format (24 characters), not handles or video URLs")
    existing = defaultdict(list)
    # Archived rows still reserve a channel; preview must never reassign it.
    for row in db.query(DatasetContent.source_channel_id, DatasetContent.data_split).filter(
            DatasetContent.source_channel_id.in_(ids)).all():
        existing[row.source_channel_id].append(row.data_split)
    result = []
    for channel_id in ids:
        split, _ = channel_dataset_split(channel_id)
        previous = sorted({str(value) for value in existing[channel_id] if value})
        result.append({"channel_id": channel_id, "assigned_split": split,
                       "existing_dataset_count": len(existing[channel_id]), "existing_splits": previous,
                       "split_conflict": any(value != split for value in previous),
                       "unknown_usage": "reserved_not_used" if split == "train" else split,
                       "independence_confirmed": False})
    return {"split_strategy": SPLIT_STRATEGY, "items": result, "database_changed": False}
