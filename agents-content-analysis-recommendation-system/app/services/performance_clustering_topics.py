"""Resolve exactly the saved, above-benchmark topic cohort; never substitute a whole category."""
from __future__ import annotations

from datetime import datetime, timezone

from app.services.group_response_summary import _eligible
from app.services.outcome_dataset import _weighted_median


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 2**53 - 1


def _utc(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def saved_topic_cohort(bundle: dict, category: str, topic_id: str, group_index: int) -> dict | None:
    """Validate group membership and benchmark using the frozen topic-comparison records.

    Results here remain bound to the originally displayed '16 of 29' calculation.
    Current YouTube counters must not silently change that frozen membership.
    """
    comparison = bundle.get("topic_comparisons") or {}
    if (comparison.get("schema_version") != "topic-comparison-evidence-v1"
            or bundle.get("taxonomy_leaf_key") != category
            or (bundle.get("input") or {}).get("availability") != "available"):
        return None
    topics = [t for t in bundle.get("action_topics", []) if isinstance(t, dict)
              and t.get("topic_id") == topic_id and t.get("source_type") == "transcript"
              and (t.get("user") or {}).get("status") == "not_detected"]
    items = [t for t in comparison.get("items", []) if isinstance(t, dict)
             and t.get("evidence_topic_id") == topic_id]
    if len(topics) != 1 or len(items) != 1:
        return None
    item = items[0]
    summary = item.get("group_response_summary") or {}
    as_of = summary.get("as_of")
    cutoff = _utc(as_of)
    if (summary.get("schema_version") != "historical-group-response-v1"
            or summary.get("status") != "available"
            or summary.get("is_prediction") is not False
            or summary.get("causal_claim") is not False
            or cutoff is None or as_of != comparison.get("as_of")):
        return None
    groups = summary.get("groups")
    if not isinstance(groups, list) or not 0 <= group_index < len(groups):
        return None
    group = groups[group_index]
    if not isinstance(group, dict):
        return None
    cell = (category, group.get("format"), group.get("age_group"), group.get("view_metric_version"))
    threshold = group.get("threshold_views")
    if (group.get("category") != category or
            cell[1] not in {"short_form", "long_form"} or
            cell[2] not in {"age_0_7d", "age_7_30d", "age_30_90d", "age_90_365d", "age_365d_plus"} or
            cell[3] not in {"youtube_play_start_view_v2", "youtube_qualified_view_v1"} or
            not _integer(threshold)):
        return None
    records = item.get("records")
    if not isinstance(records, list):
        return None
    valid = []
    seen = set()
    # Recreate the summary's pre-performance-filter, train/general sampled cell.
    for record in sorted(records, key=lambda row: row.get("dataset_id", 0) if isinstance(row, dict) else 0):
        if not isinstance(record, dict) or _eligible(record, category, cutoff) is not None:
            continue
        video_id = record.get("video_id")
        if video_id in seen:
            continue
        seen.add(video_id)
        record_cell = (category, record.get("format_group"), record.get("age_group"), record.get("view_metric_version"))
        if record_cell == cell:
            valid.append(record)
    benchmark_ids = [row["video_id"] for row in valid]
    members = [row for row in valid if row["topic_status"] == "detected"]
    passing = [row for row in members if row["latest_observation"]["views"] > threshold]
    ids = [row["video_id"] for row in members]
    passing_ids = [row["video_id"] for row in passing]
    if not valid or not members:
        return None
    expected_threshold = _weighted_median([
        {"source_channel_id": row["channel_id"], "source_youtube_id": row["video_id"],
         "observation": row["latest_observation"]} for row in valid
    ])
    def matches(name, expected):
        actual = group.get(name)
        return isinstance(actual, list) and len(actual) == len(expected) and set(actual) == set(expected)
    if (expected_threshold != threshold or
            not matches("benchmark_video_ids", benchmark_ids) or
            not matches("video_ids", ids) or
            not matches("passing_video_ids", passing_ids) or
            group.get("benchmark_sample_size") != len(valid) or
            group.get("sample_size") != len(members) or
            group.get("passing_count") != len(passing) or
            group.get("channel_count") != len({row["channel_id"] for row in members}) or
            group.get("benchmark_channel_count") != len({row["channel_id"] for row in valid})):
        return None
    return {
        "topic_id": topic_id, "topic_title": item.get("title_th") or item.get("canonical_topic") or topic_id,
        "group_index": group_index, "format": cell[1], "age_group": cell[2],
        "view_metric_version": cell[3], "threshold_views": threshold,
        "sample_size": len(members), "passing_count": len(passing),
        "benchmark_sample_size": len(valid), "as_of": as_of,
        "passing_records": sorted(passing, key=lambda row: row["dataset_id"]),
    }
