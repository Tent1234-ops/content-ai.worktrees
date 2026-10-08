"""Deterministic Outcome Prediction dataset contracts for Phase 2.

This module freezes inputs and prepares features/labels.  It does not train a
model, activate anything, or silently open independent-test outcomes.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.database.models import DatasetContent, ReferenceVideoStatistic
from app.services.actionable_recommendations import _aliases
from app.services.dataset_eligibility import (
    production_transcript_conditions,
    reference_source_matches,
)
from app.services.outcome_prediction_readiness import (
    SUCCESSFUL_OBSERVATION_STATUSES,
    SUPPORTED_YOUTUBE_METRICS,
    TARGET_LEAVES,
    _age_bucket,
    _confirmed_format,
    _latest_observation,
    data_use_gate,
    scan_prior_artifact_use,
    sha256_json,
    validate_protocol,
)
from app.services.recommendation_catalog import template_catalog
from app.services.recommendation_evidence import locate_terms, valid_segments


MANIFEST_SCHEMA_VERSION = "outcome-dataset-manifest-v1"
FEATURE_SCHEMA_VERSION = "outcome-features-v1"
BENCHMARK_SCHEMA_VERSION = "outcome-benchmarks-v1"
LABEL_SCHEMA_VERSION = "outcome-labels-v1"
COLLECTION_MANIFEST_SCHEMA_VERSION = "outcome-statistics-collection-manifest-v1"
SPLIT_METHOD_VERSION = "channel-protected-hash-v1"
SAMPLING_FRAMES = {"general_protocol_v1", "high_response_protocol_v1"}
MODEL_INPUT_FIELDS = {
    "canonical_topic_presence",
    "accepted_category",
    "confirmed_format",
    "duration_seconds",
    "frozen_age_context",
}
FORBIDDEN_FEATURE_TOKENS = {
    "views", "likes", "comments", "growth", "trend_rank",
    "high_performance", "channel_id", "video_id", "url", "title",
    "classifier_confidence",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False, default=str,
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _as_utc(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | str | None) -> str | None:
    parsed = _as_utc(value)
    return parsed.isoformat().replace("+00:00", "Z") if parsed else None


def _metadata(row: DatasetContent) -> dict[str, Any]:
    try:
        value = json.loads(row.raw_metadata_json or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _sampling_frame(metadata: dict[str, Any]) -> str | None:
    value = str(metadata.get("outcome_sampling_frame") or "").strip()
    return value if value in SAMPLING_FRAMES else None


def _role_for(row: DatasetContent, protocol: dict[str, Any]) -> str | None:
    if row.data_split == "validation":
        return "calibration"
    if row.data_split == "test":
        return "independent_test"
    if row.data_split != "train":
        return None
    seed = int((protocol.get("model_policy") or {}).get("random_seed", 261008))
    group = str(row.source_channel_id or row.creator_group_key or "")
    slot = int(hashlib.sha256(f"{seed}:{group}".encode()).hexdigest()[:8], 16) % 4
    return "tuning" if slot == 0 else "fit"


def _prior_roles(row: DatasetContent, prior_use: dict[str, Any]) -> list[str]:
    roles = set((prior_use.get("by_dataset_id") or {}).get(str(row.dataset_id), []))
    roles.update((prior_use.get("by_video_id") or {}).get(str(row.source_youtube_id), []))
    return sorted(roles)


def _identity_issues(records: list[dict[str, Any]]) -> None:
    """Mutate issue lists only; never repair or rewrite source split metadata."""
    role_groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    sample_groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        for key in ("source_channel_id", "creator_group_key"):
            value = record.get(key)
            if value:
                role_groups[f"{key}:{value}"].append(record)
        for key in ("source_youtube_id", "transcript_sha256"):
            value = record.get(key)
            if value:
                sample_groups[f"{key}:{value}"].append(record)

    for members in role_groups.values():
        roles = {item.get("outcome_role") for item in members if item.get("outcome_role")}
        if len(roles) > 1:
            for item in members:
                item["exclusion_reasons"].append("identity_crosses_outcome_partitions")

    for members in sample_groups.values():
        if len(members) < 2:
            continue
        roles = {item.get("outcome_role") for item in members if item.get("outcome_role")}
        reason = "identity_crosses_outcome_partitions" if len(roles) > 1 else "duplicate_video_or_transcript"
        keep = min(members, key=lambda item: int(item["dataset_id"]))
        for item in members:
            if reason == "identity_crosses_outcome_partitions" or item is not keep:
                item["exclusion_reasons"].append(reason)

    for record in records:
        record["exclusion_reasons"] = sorted(set(record["exclusion_reasons"]))


def database_source_records(
    db: Session,
    *,
    cutoff: datetime,
    protocol: dict[str, Any],
    repo_root,
) -> list[dict[str, Any]]:
    """Read source rows once and select one real observation per Video ID."""
    cutoff_naive = _as_utc(cutoff).replace(tzinfo=None)
    rows = db.query(DatasetContent).filter(
        DatasetContent.deleted_at.is_(None),
        DatasetContent.is_active.is_(True),
        DatasetContent.taxonomy_leaf_key.in_(TARGET_LEAVES),
    ).order_by(DatasetContent.dataset_id).all()
    dataset_ids = [int(row.dataset_id) for row in rows]
    observations = []
    if dataset_ids:
        observations = db.query(ReferenceVideoStatistic).filter(
            ReferenceVideoStatistic.dataset_id.in_(dataset_ids),
        ).order_by(
            ReferenceVideoStatistic.dataset_id,
            ReferenceVideoStatistic.observed_at,
            ReferenceVideoStatistic.observation_id,
        ).all()
    by_dataset: defaultdict[int, list[ReferenceVideoStatistic]] = defaultdict(list)
    for observation in observations:
        by_dataset[int(observation.dataset_id)].append(observation)

    production_ids = {
        int(value[0]) for value in db.query(DatasetContent.dataset_id).filter(
            *production_transcript_conditions(train_only=False, require_training=False)
        ).all()
    }
    prior_use = scan_prior_artifact_use(repo_root)
    max_age = int((protocol.get("cutoff_policy") or {}).get(
        "latest_successful_observation_max_age_hours", 24
    ))
    records: list[dict[str, Any]] = []
    for row in rows:
        metadata = _metadata(row)
        content_format, format_source = _confirmed_format(row)
        latest, observation_reasons = _latest_observation(
            by_dataset[int(row.dataset_id)], row, cutoff_naive, max_age
        )
        age_bucket, age_days = _age_bucket(
            row.published_at, latest.observed_at if latest else None
        )
        transcript = str(row.transcript or "")
        calculated_hash = hashlib.sha256(transcript.encode("utf-8")).hexdigest()
        role = _role_for(row, protocol)
        prior_roles = _prior_roles(row, prior_use)
        sampling_frame = _sampling_frame(metadata)
        issues: list[str] = []
        if int(row.dataset_id) not in production_ids:
            issues.append("production_contract_not_met")
        if not reference_source_matches(row):
            issues.append("source_identity_invalid")
        if row.transcript_scope != "full_video":
            issues.append("transcript_not_full_video")
        if not transcript:
            issues.append("transcript_missing")
        if calculated_hash != str(row.transcript_sha256 or ""):
            issues.append("transcript_hash_mismatch")
        if content_format == "unknown":
            issues.append("confirmed_format_missing")
        if age_bucket in {"unknown", "invalid"}:
            issues.append("invalid_age_context")
        if latest and latest.view_metric_version not in SUPPORTED_YOUTUBE_METRICS:
            issues.append("unsupported_view_metric_version")
        issues.extend(observation_reasons)
        if not sampling_frame:
            issues.append("sampling_frame_not_confirmed")
        if role is None:
            issues.append("unsupported_source_split")
        if row.collection_strategy == "recommendation_high_performance" and role in {
            "calibration", "independent_test"
        }:
            issues.append("outcome_selected_holdout_forbidden")
        if role == "independent_test":
            fresh = metadata.get("outcome_holdout_status") == "fresh_confirmed"
            reviewed = metadata.get("outcome_prior_use_reviewed") is True
            if not fresh or not reviewed or prior_roles:
                issues.append("fresh_outcome_test_not_demonstrated")

        record = {
            "dataset_id": int(row.dataset_id),
            "source_youtube_id": str(row.source_youtube_id or ""),
            "source_channel_id": str(row.source_channel_id or ""),
            "creator_group_key": str(row.creator_group_key or ""),
            "source_url": str(row.video_url or row.source_release_url or ""),
            "source_split": str(row.data_split or ""),
            "split_protection": "protected" if row.data_split in {"validation", "test"} else "none",
            "outcome_role": role,
            "accepted_category": str(row.taxonomy_leaf_key or ""),
            "confirmed_format": content_format,
            "format_provenance": format_source,
            "duration_seconds": row.duration_seconds,
            "published_at": _iso(row.published_at),
            "frozen_age_context": age_bucket,
            "age_days_at_observation": round(age_days, 8) if age_days is not None else None,
            "transcript": transcript,
            "transcript_sha256": str(row.transcript_sha256 or ""),
            "transcript_scope": str(row.transcript_scope or ""),
            "transcript_source": str(row.transcript_source or ""),
            "transcript_timestamps_available": bool(row.transcript_timestamps_available),
            "transcript_segments": valid_segments(metadata.get("transcript_segments")),
            "metadata_provenance": {
                "dataset_source": row.dataset_source,
                "dataset_version": row.dataset_version,
                "source_record_id": row.source_record_id,
                "source_archive_sha256": row.source_archive_sha256,
                "source_annotation_sha256": row.source_annotation_sha256,
                "reviewed_at": _iso(row.reviewed_at),
                "license_name": row.license_name,
                "license_url": row.license_url,
            },
            "collection_strategy": row.collection_strategy,
            "sampling_frame": sampling_frame,
            "prior_explicit_roles": prior_roles,
            "observation": ({
                "observation_id": int(latest.observation_id),
                "observed_at": _iso(latest.observed_at),
                "view_metric_version": latest.view_metric_version,
                "views": int(latest.views),
                "status": latest.status,
            } if latest else None),
            "exclusion_reasons": sorted(set(issues)),
        }
        records.append(record)
    _identity_issues(records)
    return records


def feature_schema(protocol: dict[str, Any]) -> dict[str, Any]:
    catalog = template_catalog()
    topics = {
        category: [item["key"] for item in catalog["categories"].get(category, [])]
        for category in TARGET_LEAVES
    }
    schema = {
        "schema_version": FEATURE_SCHEMA_VERSION,
        "feature_policy_version": (protocol.get("feature_policy") or {}).get("version"),
        "catalog_version": catalog.get("version"),
        "catalog_sha256": _sha256(catalog),
        "model_input_fields": sorted(MODEL_INPUT_FIELDS),
        "canonical_topics": topics,
        "binary_topic_presence": True,
        "forbidden_tokens": sorted(FORBIDDEN_FEATURE_TOKENS),
        "unassessable_action": "exclude_not_all_false",
    }
    schema["feature_schema_sha256"] = _sha256(schema)
    return schema


def validate_feature_vector(model_input: dict[str, Any]) -> None:
    keys = set(model_input)
    if keys != MODEL_INPUT_FIELDS:
        raise ValueError(f"Feature fields do not match whitelist: {sorted(keys)}")

    def inspect(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = str(key).casefold()
                if any(token in normalized for token in FORBIDDEN_FEATURE_TOKENS):
                    raise ValueError(f"Forbidden feature at {path}.{key}")
                inspect(child, f"{path}.{key}")
        elif isinstance(value, (list, tuple)):
            for index, child in enumerate(value):
                inspect(child, f"{path}[{index}]")
    inspect(model_input, "model_input")


def build_feature_record(record: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    reasons = []
    transcript = str(record.get("transcript") or "")
    transcript_hash = hashlib.sha256(transcript.encode("utf-8")).hexdigest()
    if record.get("transcript_scope") != "full_video":
        reasons.append("transcript_not_full_video")
    if not transcript:
        reasons.append("transcript_missing")
    if transcript_hash != record.get("transcript_sha256"):
        reasons.append("transcript_hash_mismatch")
    if record.get("accepted_category") not in TARGET_LEAVES:
        reasons.append("unsupported_category")
    if record.get("confirmed_format") not in {"short_form", "long_form"}:
        reasons.append("confirmed_format_missing")
    if record.get("frozen_age_context") in {None, "unknown", "invalid"}:
        reasons.append("age_context_missing")
    duration = record.get("duration_seconds")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration <= 0:
        reasons.append("duration_invalid")
    if reasons:
        return {
            "schema_version": FEATURE_SCHEMA_VERSION,
            "status": "unusable",
            "reason_codes": sorted(set(reasons)),
            "source_transcript_sha256": record.get("transcript_sha256"),
        }

    catalog = template_catalog()
    category = record["accepted_category"]
    topic_presence: dict[str, bool] = {}
    evidence: dict[str, dict[str, Any]] = {}
    segments = record.get("transcript_segments") or []
    for template in catalog["categories"].get(category, []):
        aliases = _aliases(template, category)
        occurrences = locate_terms(transcript, aliases, segments=segments)
        topic_presence[template["key"]] = bool(occurrences)
        evidence[template["key"]] = {
            "status": "detected" if occurrences else "not_detected",
            "occurrences": occurrences[:3],
        }
    model_input = {
        "canonical_topic_presence": topic_presence,
        "accepted_category": category,
        "confirmed_format": record["confirmed_format"],
        "duration_seconds": float(duration),
        "frozen_age_context": record["frozen_age_context"],
    }
    validate_feature_vector(model_input)
    schema = feature_schema(protocol)
    result = {
        "schema_version": FEATURE_SCHEMA_VERSION,
        "status": "usable",
        "reason_codes": [],
        "source_transcript_sha256": record["transcript_sha256"],
        "feature_schema_sha256": schema["feature_schema_sha256"],
        "model_input": model_input,
        "evidence": evidence,
    }
    result["feature_sha256"] = _sha256({
        "schema": result["feature_schema_sha256"],
        "transcript": result["source_transcript_sha256"],
        "model_input": model_input,
        "evidence": evidence,
    })
    return result


def _record_core(record: dict[str, Any]) -> dict[str, Any]:
    observation = record.get("observation") or {}
    return {
        "dataset_id": int(record["dataset_id"]),
        "source_youtube_id": record["source_youtube_id"],
        "source_channel_id": record["source_channel_id"],
        "creator_group_key": record["creator_group_key"],
        "source_url": record["source_url"],
        "source_split": record["source_split"],
        "split_protection": record["split_protection"],
        "outcome_role": record["outcome_role"],
        "accepted_category": record["accepted_category"],
        "confirmed_format": record["confirmed_format"],
        "format_provenance": record.get("format_provenance"),
        "duration_seconds": record["duration_seconds"],
        "published_at": record["published_at"],
        "frozen_age_context": record["frozen_age_context"],
        "transcript_sha256": record["transcript_sha256"],
        "transcript_scope": record["transcript_scope"],
        "transcript_source": record["transcript_source"],
        "metadata_provenance": record["metadata_provenance"],
        "collection_strategy": record.get("collection_strategy"),
        "sampling_frame": record.get("sampling_frame"),
        "prior_explicit_roles": record.get("prior_explicit_roles", []),
        "observation": {
            "observation_id": observation.get("observation_id"),
            "observed_at": observation.get("observed_at"),
            "view_metric_version": observation.get("view_metric_version"),
            "status": observation.get("status"),
            "views": observation.get("views"),
        },
    }


def freeze_manifest(
    records: Iterable[dict[str, Any]],
    *,
    cutoff: datetime,
    protocol: dict[str, Any],
    data_use_record: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_protocol(protocol)
    if not validation["valid"]:
        return {"status": "blocked", "reason_codes": validation["errors"], "manifest": None}
    rights = data_use_gate(data_use_record, "training")
    source = [dict(item, exclusion_reasons=list(item.get("exclusion_reasons") or [])) for item in records]
    _identity_issues(source)
    excluded = [
        {"dataset_id": item.get("dataset_id"), "source_youtube_id": item.get("source_youtube_id"),
         "source_split": item.get("source_split"), "outcome_role": item.get("outcome_role"),
         "reason_codes": sorted(set(item.get("exclusion_reasons") or []))}
        for item in source if item.get("exclusion_reasons")
    ]
    if not rights["allowed"]:
        return {
            "status": "blocked_data_use", "reason_codes": rights["reason_codes"],
            "manifest": None, "excluded": excluded,
        }
    eligible = [item for item in source if not item.get("exclusion_reasons")]
    if not eligible:
        return {"status": "no_eligible_records", "reason_codes": [], "manifest": None, "excluded": excluded}

    feature_records = []
    public_records = []
    for item in sorted(eligible, key=lambda value: (value["outcome_role"], int(value["dataset_id"]))):
        feature = build_feature_record(item, protocol)
        if feature["status"] != "usable":
            excluded.append({
                "dataset_id": item["dataset_id"], "source_youtube_id": item["source_youtube_id"],
                "source_split": item["source_split"], "outcome_role": item["outcome_role"],
                "reason_codes": feature["reason_codes"],
            })
            continue
        core = _record_core(item)
        record_sha = _sha256(core)
        public = dict(core)
        if item["outcome_role"] == "independent_test":
            public["observation"] = {
                key: value for key, value in core["observation"].items() if key != "views"
            }
            public["outcome_access"] = "sealed_until_phase_6_evaluation"
        else:
            public["outcome_access"] = "development"
        public["source_record_sha256"] = record_sha
        public["feature_sha256"] = feature["feature_sha256"]
        public_records.append(public)
        feature_records.append({
            "dataset_id": item["dataset_id"], "outcome_role": item["outcome_role"],
            **feature,
        })

    manifest_core = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "target_version": (protocol.get("target") or {}).get("version"),
        "protocol_sha256": validation["protocol_sha256"],
        "feature_schema_sha256": feature_schema(protocol)["feature_schema_sha256"],
        "split_method_version": SPLIT_METHOD_VERSION,
        "cutoff_utc": _iso(cutoff),
        "sampling_frame": (protocol.get("sampling") or {}).get("frame"),
        "records": public_records,
    }
    manifest = dict(manifest_core)
    manifest["manifest_sha256"] = _sha256(manifest_core)
    return {
        "status": "frozen" if public_records else "no_eligible_records",
        "reason_codes": [], "manifest": manifest,
        "feature_records": feature_records, "excluded": excluded,
    }


def verify_manifest(manifest: dict[str, Any]) -> bool:
    declared = manifest.get("manifest_sha256")
    core = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    return manifest.get("schema_version") == MANIFEST_SCHEMA_VERSION and declared == _sha256(core)


def _cell(record: dict[str, Any]) -> tuple[str, str, str, str]:
    observation = record.get("observation") or {}
    return (
        str(record.get("accepted_category") or ""),
        str(record.get("confirmed_format") or ""),
        str(record.get("frozen_age_context") or ""),
        str(observation.get("view_metric_version") or ""),
    )


def _weighted_median(records: list[dict[str, Any]]) -> int:
    channel_counts = Counter(str(item["source_channel_id"]) for item in records)
    weighted = sorted(
        ((int(item["observation"]["views"]), str(item["source_youtube_id"]),
          1.0 / channel_counts[str(item["source_channel_id"])]) for item in records),
        key=lambda value: (value[0], value[1]),
    )
    target = sum(value[2] for value in weighted) * 0.5
    cumulative = 0.0
    for views, _video_id, weight in weighted:
        cumulative += weight
        if cumulative + 1e-12 >= target:
            return views
    return weighted[-1][0]


def fit_benchmarks(records: Iterable[dict[str, Any]], protocol: dict[str, Any]) -> dict[str, Any]:
    fit = [item for item in records if item.get("outcome_role") == "fit" and
           (item.get("observation") or {}).get("views") is not None]
    grouped: defaultdict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in fit:
        grouped[_cell(item)].append(item)
    cells = []
    support = protocol.get("context_support") or {}
    minimum_videos = int(support.get("minimum_fit_videos", 20))
    minimum_channels = int(support.get("minimum_fit_channels", 5))
    minimum_per_label = int(support.get("minimum_fit_videos_per_label", 5))
    for key, members in sorted(grouped.items()):
        threshold = _weighted_median(members)
        labels = Counter(int(int(item["observation"]["views"]) > threshold) for item in members)
        source = sorted(str(item["source_youtube_id"]) for item in members)
        channel_count = len({item["source_channel_id"] for item in members})
        reasons = []
        if len(members) < minimum_videos:
            reasons.append("minimum_fit_videos_not_met")
        if channel_count < minimum_channels:
            reasons.append("minimum_fit_channels_not_met")
        if labels[0] < minimum_per_label or labels[1] < minimum_per_label:
            reasons.append("minimum_fit_videos_per_label_not_met")
        cell = {
            "cell": list(key), "threshold_views": threshold,
            "fit_video_count": len(members),
            "fit_channel_count": channel_count,
            "fit_label_counts": {"0": labels[0], "1": labels[1]},
            "fit_source_ids_sha256": _sha256(source),
            "support_requirements": {
                "minimum_fit_videos": minimum_videos,
                "minimum_fit_channels": minimum_channels,
                "minimum_fit_videos_per_label": minimum_per_label,
            },
            "reason_codes": reasons,
            "status": "supported" if not reasons else "insufficient_support",
        }
        cell["benchmark_sha256"] = _sha256(cell)
        cells.append(cell)
    result = {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "protocol_sha256": validate_protocol(protocol)["protocol_sha256"],
        "fit_partition_only": True,
        "cells": cells,
    }
    result["benchmarks_sha256"] = _sha256(result)
    return result


def label_records(
    records: Iterable[dict[str, Any]],
    benchmarks: dict[str, Any],
    *,
    unlock_independent_test: bool = False,
) -> dict[str, Any]:
    by_cell = {tuple(item["cell"]): item for item in benchmarks.get("cells", [])}
    labels, exclusions = [], []
    for item in records:
        role = item.get("outcome_role")
        if role == "independent_test" and not unlock_independent_test:
            exclusions.append({"dataset_id": item.get("dataset_id"), "reason": "independent_test_sealed"})
            continue
        observation = item.get("observation") or {}
        if observation.get("views") is None:
            exclusions.append({"dataset_id": item.get("dataset_id"), "reason": "outcome_missing"})
            continue
        benchmark = by_cell.get(_cell(item))
        if not benchmark or benchmark.get("status") != "supported":
            exclusions.append({"dataset_id": item.get("dataset_id"), "reason": "unsupported_fit_cell"})
            continue
        views = int(observation["views"])
        labels.append({
            "dataset_id": item["dataset_id"], "outcome_role": role,
            "cell": benchmark["cell"], "benchmark_sha256": benchmark["benchmark_sha256"],
            "label": int(views > int(benchmark["threshold_views"])),
            "tie": views == int(benchmark["threshold_views"]),
        })
    result = {
        "schema_version": LABEL_SCHEMA_VERSION,
        "benchmarks_sha256": benchmarks.get("benchmarks_sha256"),
        "independent_test_unlocked": bool(unlock_independent_test),
        "labels": labels, "exclusions": exclusions,
    }
    result["labels_sha256"] = _sha256(result)
    return result


def cv_fold_labels(
    records: Iterable[dict[str, Any]],
    protocol: dict[str, Any],
    *,
    heldout_channel_ids: set[str],
) -> dict[str, Any]:
    rows = list(records)
    fit_rows = [dict(item, outcome_role="fit") for item in rows
                if item.get("source_channel_id") not in heldout_channel_ids]
    heldout = [dict(item, outcome_role="cv_heldout") for item in rows
               if item.get("source_channel_id") in heldout_channel_ids]
    benchmarks = fit_benchmarks(fit_rows, protocol)
    labels = label_records(heldout, benchmarks)
    return {
        "fit_channel_ids": sorted({item["source_channel_id"] for item in fit_rows}),
        "heldout_channel_ids": sorted(heldout_channel_ids),
        "benchmarks": benchmarks, "heldout_labels": labels,
    }


def coverage_report(records: Iterable[dict[str, Any]], protocol: dict[str, Any]) -> dict[str, Any]:
    rows = list(records)
    partitions = {}
    minimums = (protocol.get("split_policy") or {}).get("minimums", {})
    for role in ("fit", "tuning", "calibration", "independent_test"):
        members = [item for item in rows if item.get("outcome_role") == role and
                   not item.get("exclusion_reasons")]
        videos = len({item.get("source_youtube_id") for item in members})
        channels = len({item.get("source_channel_id") for item in members})
        required = minimums.get(role, {})
        partitions[role] = {
            "independent_videos": videos, "channels": channels,
            "required_videos": int(required.get("videos", 0)),
            "required_channels": int(required.get("channels", 0)),
            "missing_videos": max(0, int(required.get("videos", 0)) - videos),
            "missing_channels": max(0, int(required.get("channels", 0)) - channels),
            "by_category": dict(sorted(Counter(item.get("accepted_category") for item in members).items())),
            "by_format": dict(sorted(Counter(item.get("confirmed_format") for item in members).items())),
            "by_age": dict(sorted(Counter(item.get("frozen_age_context") for item in members).items())),
        }
    exclusions = Counter(
        reason for item in rows for reason in item.get("exclusion_reasons", [])
    )
    exclusions_by_category: defaultdict[str, Counter] = defaultdict(Counter)
    for item in rows:
        for reason in item.get("exclusion_reasons", []):
            exclusions_by_category[str(item.get("accepted_category") or "missing")][reason] += 1
    source_cells = Counter(
        (
            str(item.get("accepted_category") or "missing"),
            str(item.get("confirmed_format") or "unknown"),
            str(item.get("frozen_age_context") or "unknown"),
            str((item.get("observation") or {}).get("view_metric_version") or "missing"),
        )
        for item in rows
    )
    minimum_per_category = (protocol.get("split_policy") or {}).get(
        "minimum_test_per_qualified_category", {}
    )
    return {
        "partitions": partitions,
        "exclusion_reason_counts": dict(sorted(exclusions.items())),
        "exclusion_reasons_by_category": {
            category: dict(sorted(counts.items()))
            for category, counts in sorted(exclusions_by_category.items())
        },
        "source_rows_by_category": dict(sorted(Counter(
            item.get("accepted_category") for item in rows
        ).items())),
        "source_context_cells": [
            {"category": key[0], "confirmed_format": key[1], "age_context": key[2],
             "view_metric_version": key[3], "videos": count}
            for key, count in sorted(source_cells.items())
        ],
        "independent_test_minimum_per_qualified_category": minimum_per_category,
        "partition_label_counts": {
            role: {"status": "not_computed_before_frozen_fit_benchmark"}
            for role in ("fit", "tuning", "calibration", "independent_test")
        },
        "independent_video_count": len({item.get("source_youtube_id") for item in rows}),
        "channel_count": len({item.get("source_channel_id") for item in rows if item.get("source_channel_id")}),
        "test_outcome_associations_disclosed": False,
    }


def build_collection_manifest(
    records: Iterable[dict[str, Any]], *, cutoff: datetime, protocol_sha256: str,
) -> dict[str, Any]:
    selected = []
    for item in sorted(records, key=lambda value: int(value["dataset_id"])):
        selected.append({
            "dataset_id": int(item["dataset_id"]),
            "source_youtube_id": item["source_youtube_id"],
            "source_url": item["source_url"],
            "source_split": item["source_split"],
            "split_protection": item["split_protection"],
            "intended_outcome_role": item.get("outcome_role"),
        })
    core = {
        "schema_version": COLLECTION_MANIFEST_SCHEMA_VERSION,
        "protocol_sha256": protocol_sha256,
        "cutoff_utc": _iso(cutoff),
        "purpose": "outcome_statistics_collection",
        "records": selected,
    }
    result = dict(core)
    result["manifest_sha256"] = _sha256(core)
    return result


def verify_collection_manifest(manifest: dict[str, Any]) -> bool:
    declared = manifest.get("manifest_sha256")
    core = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    return (
        manifest.get("schema_version") == COLLECTION_MANIFEST_SCHEMA_VERSION
        and manifest.get("purpose") == "outcome_statistics_collection"
        and declared == _sha256(core)
    )


def phase2_readiness_report(
    db: Session,
    *,
    cutoff: datetime,
    protocol: dict[str, Any],
    data_use_record: dict[str, Any],
    repo_root,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    records = database_source_records(
        db, cutoff=cutoff, protocol=protocol, repo_root=repo_root
    )
    rights = data_use_gate(data_use_record, "training")
    coverage = coverage_report(records, protocol)
    eligible = [item for item in records if not item["exclusion_reasons"]]
    result = {
        "schema_version": "outcome-phase-2-readiness-v1",
        "captured_at": _iso(datetime.now(timezone.utc)),
        "cutoff_utc": _iso(cutoff),
        "protocol_sha256": validate_protocol(protocol)["protocol_sha256"],
        "status": "blocked_data_use" if not rights["allowed"] else (
            "ready_to_freeze" if eligible else "blocked_data"
        ),
        "data_use_gate": rights,
        "active_source_rows": len(records),
        "independent_video_ids": len({item["source_youtube_id"] for item in records}),
        "channels": len({item["source_channel_id"] for item in records if item["source_channel_id"]}),
        "structurally_eligible_rows": len(eligible),
        "training_allowed_rows": len(eligible) if rights["allowed"] else 0,
        "coverage": coverage,
        "manifest_created": False,
        "independent_test_labels_opened": False,
        "note": "A blocked readiness report is not a frozen training dataset.",
    }
    result["report_sha256"] = sha256_json(result)
    exclusions = [{
        "dataset_id": item["dataset_id"],
        "source_youtube_id": item["source_youtube_id"],
        "category": item["accepted_category"],
        "source_split": item["source_split"],
        "intended_outcome_role": item["outcome_role"],
        "split_protection": item["split_protection"],
        "reason_codes": item["exclusion_reasons"],
    } for item in records if item["exclusion_reasons"]]
    return result, exclusions, feature_schema(protocol)
