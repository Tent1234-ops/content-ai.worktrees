"""Historical topic-group counts, not a trained predictor or causal estimate."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

from app.core.datetime_utils import utc_isoformat
from app.services.actionable_recommendations import MINIMUM_CHANNELS, MINIMUM_CLIPS
from app.services.outcome_dataset import _weighted_median
from app.services.recommendation_evidence import fingerprint
from app.services.view_metrics import YOUTUBE_PLAY_START_VIEW_V2, YOUTUBE_QUALIFIED_VIEW_V1

SCHEMA_VERSION = "historical-group-response-v1"
POLICY = {
    "version": "general-sample-topic-group-v1",
    "sampling_frame": "general_protocol_v1",
    "benchmark": "channel_balanced_median_of_all_eligible_cell_members",
    "passing_rule": "views_strictly_greater_than_benchmark",
    "percentage": "100 * passing_video_count / topic_video_count",
    "minimum_topic_videos": MINIMUM_CLIPS,
    "minimum_topic_channels": MINIMUM_CHANNELS,
    "maximum_observation_age_hours": 24,
    "cell_fields": ["category", "format", "age_group", "view_metric_version"],
}
AGE_BOUNDS = {
    "age_0_7d": (0, 7), "age_7_30d": (7, 30), "age_30_90d": (30, 90),
    "age_90_365d": (90, 365), "age_365d_plus": (365, float("inf")),
}


def _date(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (ValueError, TypeError, AttributeError):
        return None


def _eligible(record: dict, category: str, cutoff: datetime) -> str | None:
    if record.get("taxonomy_leaf_key") != category or record.get("data_split") != "train":
        return "category_or_protected_split"
    if (record.get("sampling_frame") != POLICY["sampling_frame"] or
            record.get("collection_strategy") == "recommendation_high_performance"):
        return "sampling_not_confirmed_general"
    if (not re.fullmatch(r"[A-Za-z0-9_-]{11}", str(record.get("video_id") or "")) or
            not str(record.get("channel_id") or "").strip() or
            record.get("source_record_id") != record.get("video_id")):
        return "invalid_source_identity"
    if not record.get("comparison_eligible") or record.get("topic_status") not in {"detected", "not_detected"}:
        return "unassessable_record"
    if record.get("format_group") not in {"short_form", "long_form"} or not record.get("format_source"):
        return "unconfirmed_format"
    observation = record.get("latest_observation") or {}
    views = observation.get("views")
    published, observed = _date(record.get("published_at")), _date(observation.get("observed_at"))
    if (observation.get("status") not in {"complete", "partial"} or
            not isinstance(views, int) or isinstance(views, bool) or views < 0 or
            observation.get("video_id") != record.get("video_id") or
            not isinstance(observation.get("observation_id"), int) or
            observation["observation_id"] <= 0 or not published or not observed):
        return "invalid_observation"
    if not 0 <= (cutoff - observed).total_seconds() <= POLICY["maximum_observation_age_hours"] * 3600:
        return "observation_outside_cutoff"
    bounds = AGE_BOUNDS.get(record.get("age_group"))
    if not bounds or not bounds[0] <= (observed - published).total_seconds() / 86400 < bounds[1]:
        return "invalid_age_group"
    if (observation.get("view_metric_version") != record.get("view_metric_version") or
            record.get("view_metric_version") not in {YOUTUBE_PLAY_START_VIEW_V2, YOUTUBE_QUALIFIED_VIEW_V1}):
        return "incompatible_view_metric"
    if record["topic_status"] == "detected" and not record.get("occurrences"):
        return "missing_topic_evidence"
    return None


def summarize_group_responses(records: list[dict], *, category: str, as_of: datetime) -> dict:
    """Use the complete pre-performance-filter cohort; never merge context cells."""
    cutoff = as_of.replace(tzinfo=timezone.utc) if as_of.tzinfo is None else as_of
    output = {"schema_version": SCHEMA_VERSION, "policy": dict(POLICY),
              "as_of": utc_isoformat(cutoff), "status": "insufficient_evidence", "groups": [],
              "exclusions": {}, "causal_claim": False, "is_prediction": False}
    exclusions, grouped, seen = Counter(), defaultdict(list), set()
    for record in sorted(records, key=lambda row: int(row.get("dataset_id") or 0)):
        reason = _eligible(record, category, cutoff)
        if reason:
            exclusions[reason] += 1
            continue
        video_id = record["video_id"]
        if video_id in seen:
            exclusions["duplicate_video"] += 1
            continue
        seen.add(video_id)
        grouped[(category, record["format_group"], record["age_group"], record["view_metric_version"])].append(record)
    for cell, benchmark in sorted(grouped.items()):
        members = [row for row in benchmark if row["topic_status"] == "detected"]
        channels = {row["channel_id"] for row in members}
        if len(members) < MINIMUM_CLIPS or len(channels) < MINIMUM_CHANNELS:
            exclusions["insufficient_topic_support"] += len(members)
            continue
        # Reuse the existing channel-balanced median definition, not Outcome labels.
        threshold = _weighted_median([
            {"source_channel_id": row["channel_id"], "source_youtube_id": row["video_id"],
             "observation": row["latest_observation"]} for row in benchmark
        ])
        passing = [row["video_id"] for row in members if row["latest_observation"]["views"] > threshold]
        times = [_date(row["latest_observation"]["observed_at"]) for row in benchmark]
        output["groups"].append({
            "category": cell[0], "format": cell[1], "age_group": cell[2], "view_metric_version": cell[3],
            "sample_size": len(members), "passing_count": len(passing), "channel_count": len(channels),
            "percentage": round(100 * len(passing) / len(members), 2),
            "threshold_views": threshold, "benchmark_sample_size": len(benchmark),
            "benchmark_channel_count": len({row["channel_id"] for row in benchmark}),
            "video_ids": sorted(row["video_id"] for row in members), "passing_video_ids": sorted(passing),
            "benchmark_video_ids": sorted(row["video_id"] for row in benchmark),
            "observed_from": utc_isoformat(min(times)), "observed_until": utc_isoformat(max(times)),
        })
    output["exclusions"] = dict(sorted(exclusions.items()))
    if output["groups"]:
        output["status"] = "available"
    output["data_fingerprint"] = fingerprint(output)
    return output
