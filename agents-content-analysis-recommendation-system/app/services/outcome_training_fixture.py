"""Deterministic synthetic inputs for exercising Phase 3 without real data claims."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.outcome_dataset import feature_schema, freeze_manifest


FIXTURE_SCHEMA_VERSION = "outcome-phase-3-synthetic-fixture-v1"
ROLE_COUNTS = {"fit": 60, "tuning": 30, "calibration": 36, "independent_test": 30}


def synthetic_data_use_record() -> dict[str, Any]:
    return {
        "schema_version": "outcome-data-use-decision-v1",
        "record_version": FIXTURE_SCHEMA_VERSION,
        "checked_at": "2026-10-08T00:00:00Z",
        "owner": "automated_test_fixture",
        "status": "confirmed",
        "sources": [{"name": "deterministic synthetic fixture", "intended_fields": ["all"]}],
        "intended_uses": ["audit", "training", "serving"],
        "confirmation_evidence": ["No external, personal, or provider-derived records are used."],
        "decision": {
            "audit_allowed": True,
            "real_training_allowed": False,
            "real_serving_allowed": False,
            "synthetic_software_test_allowed": True,
        },
    }


def _transcript(
    category: str, role: str, index: int, positive: bool, topics: list[str],
) -> str:
    if positive:
        topic_count = 3 + (index % max(1, len(topics) - 2))
    else:
        topic_count = index % 3
    selected = topics[: min(topic_count, len(topics))]
    return " ".join([
        "synthetic transcript used only for software validation",
        category, role, f"case-{index}",
        *selected,
        "general review experience and usage",
    ])


def build_synthetic_records(
    protocol: dict[str, Any], *, independent_test_view_offset: int = 0,
) -> list[dict[str, Any]]:
    schema = feature_schema(protocol)
    categories = ("phone", "camera", "laptop")
    per_category = {
        "fit": 20, "tuning": 10, "calibration": 12, "independent_test": 10,
    }
    channels_per_category = {
        "fit": 5, "tuning": 5, "calibration": 6, "independent_test": 5,
    }
    source_split = {
        "fit": "train", "tuning": "train",
        "calibration": "validation", "independent_test": "test",
    }
    records: list[dict[str, Any]] = []
    dataset_id = 1
    observation_id = 1
    for role in ("fit", "tuning", "calibration", "independent_test"):
        for category in categories:
            count = per_category[role]
            channel_count = channels_per_category[role]
            topics = list(schema["canonical_topics"][category])
            for index in range(count):
                positive = index >= count // 2
                transcript = _transcript(category, role, index, positive, topics)
                transcript_sha = hashlib.sha256(transcript.encode("utf-8")).hexdigest()
                views = 3_000 + index if positive else 1_000 + index
                if role == "independent_test":
                    views += independent_test_view_offset
                channel = f"fixture-{role}-{category}-channel-{index % channel_count}"
                video_id = f"fx-{role[:3]}-{category[:3]}-{index:03d}"
                records.append({
                    "dataset_id": dataset_id,
                    "source_youtube_id": video_id,
                    "source_channel_id": channel,
                    "creator_group_key": channel,
                    "source_url": f"https://fixture.invalid/{video_id}",
                    "source_split": source_split[role],
                    "split_protection": "protected" if role in {"calibration", "independent_test"} else "none",
                    "outcome_role": role,
                    "accepted_category": category,
                    "confirmed_format": "long_form",
                    "format_provenance": "synthetic_fixture",
                    "duration_seconds": 240 + (index % 5) * 30,
                    "published_at": "2026-08-01T00:00:00Z",
                    "frozen_age_context": "30_90d",
                    "transcript": transcript,
                    "transcript_sha256": transcript_sha,
                    "transcript_scope": "full_video",
                    "transcript_source": "synthetic_fixture",
                    "transcript_timestamps_available": False,
                    "transcript_segments": [],
                    "metadata_provenance": {
                        "dataset_source": "synthetic_fixture",
                        "dataset_version": FIXTURE_SCHEMA_VERSION,
                        "source_record_id": video_id,
                    },
                    "collection_strategy": "synthetic_balanced_software_path",
                    "sampling_frame": "synthetic_fixture_not_a_real_population",
                    "prior_explicit_roles": [],
                    "observation": {
                        "observation_id": observation_id,
                        "observed_at": "2026-10-01T00:00:00Z",
                        "view_metric_version": "youtube_play_start_view_v2",
                        "views": views,
                        "status": "complete",
                    },
                    "exclusion_reasons": [],
                })
                dataset_id += 1
                observation_id += 1
    return records


def write_synthetic_fixture(
    output_dir: Path, protocol: dict[str, Any], *, independent_test_view_offset: int = 0,
) -> dict[str, Any]:
    if output_dir.exists():
        raise ValueError("Synthetic fixture directory already exists")
    output_dir.mkdir(parents=True)
    data_use = synthetic_data_use_record()
    frozen = freeze_manifest(
        build_synthetic_records(
            protocol, independent_test_view_offset=independent_test_view_offset
        ),
        cutoff=datetime(2026, 10, 8, 0, 0, 0),
        protocol=protocol,
        data_use_record=data_use,
    )
    if frozen.get("status") != "frozen":
        raise RuntimeError(f"Synthetic fixture could not be frozen: {frozen}")
    files = {
        "manifest.json": frozen["manifest"],
        "features.json": frozen["feature_records"],
        "data-use.json": data_use,
        "fixture-metadata.json": {
            "schema_version": FIXTURE_SCHEMA_VERSION,
            "source_kind": "synthetic_fixture",
            "real_data": False,
            "production_eligible": False,
            "independent_test_outcomes_written": False,
            "role_counts": ROLE_COUNTS,
            "purpose": "software_path_validation_only",
        },
    }
    for name, value in files.items():
        (output_dir / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return {
        "source_kind": "synthetic_fixture",
        "manifest_path": output_dir / "manifest.json",
        "features_path": output_dir / "features.json",
        "data_use_path": output_dir / "data-use.json",
        "manifest_sha256": frozen["manifest"]["manifest_sha256"],
    }
