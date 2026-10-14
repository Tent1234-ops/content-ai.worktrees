"""Check sealed holdout identities and provenance without reading Test outcomes."""
from __future__ import annotations

import json
from collections import defaultdict

from app.services.outcome_dataset import identity_keys, verify_manifest
from app.services.outcome_prediction_readiness import _normalized_text_hash, _transcript_hash


def sealed_holdout_check(manifest, *, current_rows=None, prior_use=None, reference_rows=()):
    reasons = []
    if not isinstance(manifest, dict) or not verify_manifest(manifest):
        return {"valid": False, "fresh_count": 0, "reason_codes": ["sealed_manifest_missing_or_invalid"],
                "dataset_ids": []}
    records = manifest.get("records") or []
    identities = defaultdict(set)
    video_ids, dataset_ids = set(), set()
    for row in records:
        for key in identity_keys(row):
            identities[key].add(row.get("outcome_role"))
        if row.get("source_youtube_id") in video_ids or row.get("dataset_id") in dataset_ids:
            reasons.append("duplicate_manifest_sample")
        video_ids.add(row.get("source_youtube_id"))
        dataset_ids.add(row.get("dataset_id"))
    if any(len(roles) > 1 for roles in identities.values()):
        reasons.append("identity_partition_overlap")
    reference_keys = set()
    for row in reference_rows:
        try:
            metadata = json.loads(row.raw_metadata_json or "{}")
            if not isinstance(metadata, dict):
                raise ValueError("Invalid reference metadata")
        except (TypeError, ValueError):
            reasons.append("reference_provenance_unreadable")
            metadata = {}
        reference_keys.update(identity_keys({
            "source_youtube_id": row.source_youtube_id, "source_channel_id": row.source_channel_id,
            "creator_group_key": row.creator_group_key, "transcript_sha256": row.transcript_sha256,
            "normalized_transcript_sha256": _normalized_text_hash(row.transcript or ""),
            "near_duplicate_group_key": metadata.get("outcome_near_duplicate_group_key"),
        }))
    prior_use = prior_use or {}
    if prior_use.get("errors"):
        reasons.append("prior_use_scan_incomplete")
    tests = [row for row in records if row.get("outcome_role") == "independent_test"]
    fresh = []
    for row in tests:
        local = []
        if (row.get("outcome_access") != "sealed_until_phase_6_evaluation"
                or "views" in (row.get("observation") or {})):
            local.append("independent_test_not_sealed")
        if (row.get("source_split") != "test" or row.get("split_protection") != "protected"
                or row.get("outcome_holdout_status") != "fresh_confirmed"
                or row.get("outcome_prior_use_reviewed") is not True
                or not row.get("normalized_transcript_sha256")):
            local.append("fresh_outcome_test_not_demonstrated")
        if (row.get("collection_strategy") == "recommendation_high_performance"
                or row.get("sampling_frame") == "high_response_protocol_v1"):
            local.append("outcome_selected_holdout_forbidden")
        prior = (row.get("prior_explicit_roles") or []) + list(
            (prior_use.get("by_dataset_id") or {}).get(str(row["dataset_id"]), [])) + list(
            (prior_use.get("by_video_id") or {}).get(row["source_youtube_id"], []))
        if prior:
            local.append("independent_test_previously_used")
        if reference_keys.intersection(identity_keys(row)):
            local.append("independent_test_reference_overlap")
        if current_rows is not None:
            current = current_rows.get(row["dataset_id"])
            if current is None or not current.is_active or current.deleted_at is not None:
                local.append("holdout_source_unavailable")
            else:
                try:
                    metadata = json.loads(current.raw_metadata_json or "{}")
                    if not isinstance(metadata, dict):
                        raise ValueError("Invalid holdout metadata")
                except (TypeError, ValueError):
                    local.append("holdout_provenance_unreadable")
                    metadata = {}
                if (current.data_split != "test" or metadata.get("outcome_holdout_status") != "fresh_confirmed"
                        or metadata.get("outcome_prior_use_reviewed") is not True):
                    local.append("holdout_live_provenance_changed")
                if metadata.get("outcome_near_duplicate_group_key") != row.get("near_duplicate_group_key"):
                    local.append("holdout_source_identity_changed")
                if any(getattr(current, key) != row.get(key) for key in (
                    "source_youtube_id", "source_channel_id", "creator_group_key", "transcript_sha256"
                )) or _transcript_hash(current.transcript or "") != row.get("transcript_sha256"):
                    local.append("holdout_source_identity_changed")
        if not local:
            fresh.append(row["dataset_id"])
        reasons.extend(local)
    if not tests:
        reasons.append("independent_test_missing")
    return {"valid": not reasons, "fresh_count": len(fresh) if not reasons else 0,
            "dataset_ids": fresh if not reasons else [], "reason_codes": sorted(set(reasons)),
            "manifest_sha256": manifest["manifest_sha256"]}
