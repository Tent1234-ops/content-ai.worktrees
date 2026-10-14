"""Shared abstention and qualified-context policy for evaluation and serving."""
from __future__ import annotations

from typing import Any

TRAINING_SUPPORT_VERSION = "outcome-training-support-v1"
QUALIFIED_SCOPES_VERSION = "outcome-qualified-scopes-v1"
CONTEXT_FIELDS = ("accepted_category", "confirmed_format", "frozen_age_context", "view_metric_version")


def topic_signature(model_input: dict[str, Any]) -> list[str]:
    return sorted(str(key) for key, value in
                  (model_input.get("canonical_topic_presence") or {}).items() if value is True)


def training_support(artifact: dict[str, Any], model_input: dict[str, Any]) -> tuple[dict, list[str]]:
    support = artifact.get("training_support") or {}
    if support.get("version") != TRAINING_SUPPORT_VERSION:
        return {"status": "unsupported"}, ["training_support_artifact_missing"]
    signature = topic_signature(model_input)
    match = next((item for item in support.get("signatures", [])
                  if all(item.get(field) == model_input.get(field) for field in CONTEXT_FIELDS[:3])
                  and item.get("topic_signature") == signature), None)
    if match is None:
        return {"status": "unsupported", "topic_signature": signature,
                "policy_version": support.get("version")}, ["joint_feature_signature_not_seen_in_fit"]
    minimum_videos = int(support.get("minimum_signature_videos", 0))
    minimum_channels = int(support.get("minimum_signature_channels", 0))
    reasons = []
    if minimum_videos < 2 or minimum_channels < 2:
        reasons.append("joint_feature_support_policy_invalid")
    if int(match.get("video_count", 0)) < minimum_videos:
        reasons.append("joint_feature_minimum_videos_not_met")
    if int(match.get("channel_count", 0)) < minimum_channels:
        reasons.append("joint_feature_minimum_channels_not_met")
    return {
        "status": "unsupported" if reasons else "supported", "topic_signature": signature,
        "policy_version": support.get("version"), "source_partition": support.get("source_partition"),
        "video_count": int(match.get("video_count", 0)), "channel_count": int(match.get("channel_count", 0)),
        "minimum_video_count": minimum_videos, "minimum_channel_count": minimum_channels,
    }, reasons


def qualified_scope_reasons(scopes: Any, context: dict | None = None) -> list[str]:
    if not isinstance(scopes, dict) or scopes.get("schema_version") != QUALIFIED_SCOPES_VERSION:
        return ["qualified_scopes_missing"]
    items = scopes.get("contexts")
    if not isinstance(items, list) or not items:
        return ["qualified_scopes_missing"]
    qualified = [item for item in items if isinstance(item, dict)
                 and item.get("qualified") is True
                 and all(isinstance(item.get(key), str) and item[key] for key in CONTEXT_FIELDS)]
    if not qualified:
        return ["qualified_context_missing"]
    if context is not None and not any(
        all(item[key] == context.get(key) for key in CONTEXT_FIELDS) for item in qualified
    ):
        return ["context_not_independent_test_qualified"]
    return []
