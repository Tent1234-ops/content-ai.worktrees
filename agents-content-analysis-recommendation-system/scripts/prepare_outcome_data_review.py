"""Export read-only repair queues; never create labels or a training manifest."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("CONTENT_AI_SKIP_DB_BOOTSTRAP", "1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.outcome_dataset import database_source_records  # noqa: E402
from app.services.outcome_prediction_readiness import (  # noqa: E402
    _age_bucket, data_use_gate, database_identity, reject_database_writes,
    sha256_json, validate_protocol,
)

CATEGORIES = ("phone", "camera", "laptop")
TEXT_FAILURES = {
    "production_contract_not_met", "source_identity_invalid",
    "transcript_missing", "transcript_hash_mismatch", "transcript_not_full_video",
}
QUEUES = ("development_review", "protected_do_not_train", "transcript_repair")


def parse_cutoff(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("cutoff requires a timezone")
    return parsed.astimezone(timezone.utc)


def partition_minimums(protocol: dict) -> dict:
    minimums = protocol["split_policy"]["minimums"]
    bins = protocol["evaluation"]["calibration"]
    bin_floor = bins["bins"] * bins["minimum_videos_per_bin"]
    per_label = 2 * protocol["split_policy"]["calibration_and_test_minimum_per_label"]
    test_floor = len(protocol["sampling"]["target_categories"]) * protocol[
        "split_policy"]["minimum_test_per_qualified_category"]["videos"]
    result = {}
    for role, values in minimums.items():
        effective = values["videos"]
        if role in {"calibration", "independent_test"}:
            effective = max(effective, bin_floor, per_label)
        if role == "independent_test":
            effective = max(effective, test_floor)
        result[role] = {
            "protocol_minimum_videos": values["videos"],
            "necessary_assessed_videos": effective,
            "minimum_channels": values["channels"],
            "sufficient_for_qualification": False,
        }
    return result


def prepare_review(records: list[dict], *, selected_ids: set[int],
                   cutoff: datetime, protocol: dict, training_gate: dict) -> dict:
    """Separate owner-declared sampling provenance from unchanged source metadata."""
    rows = []
    for record in records:
        reasons = set(record["exclusion_reasons"])
        owner_selected = record["dataset_id"] in selected_ids
        recorded_selected = record.get("collection_strategy") == "recommendation_high_performance"
        outcome_selected = owner_selected or recorded_selected
        role = record.get("outcome_role")
        if outcome_selected and role in {"calibration", "independent_test"}:
            reasons.add("outcome_selected_holdout_forbidden")
        text_ok = record["transcript_scope"] == "full_video" and not (reasons & TEXT_FAILURES)
        if not text_ok:
            queue = "transcript_repair"
        elif record["source_split"] in {"validation", "test"}:
            queue = "protected_do_not_train"
        elif record["source_split"] == "train" and role in {"fit", "tuning"}:
            queue = "development_review"
        else:
            queue = "transcript_repair"
        observation = record.get("observation") or {}
        projected_age = _age_bucket(
            datetime.fromisoformat(record["published_at"].replace("Z", "+00:00"))
            if record.get("published_at") else None, cutoff,
        )[0]
        rows.append({
            "dataset_id": record["dataset_id"],
            "video_id": record["source_youtube_id"],
            "source_url": record["source_url"],
            "channel_id": record["source_channel_id"],
            "category": record["accepted_category"],
            "source_split_unchanged": record["source_split"],
            "proposed_role_not_a_manifest": role,
            "queue": queue,
            "protected": record["source_split"] in {"validation", "test"},
            "transcript_scope": record["transcript_scope"],
            "transcript_sha256": record["transcript_sha256"],
            "duration_seconds": record["duration_seconds"],
            "published_at": record["published_at"],
            "confirmed_format": record["confirmed_format"],
            "format_evidence": record.get("format_provenance"),
            "observation_id": observation.get("observation_id"),
            "observed_at": observation.get("observed_at"),
            "view_metric_version": observation.get("view_metric_version"),
            "actual_observation_age_context": record["frozen_age_context"],
            "projected_age_if_refreshed_at_cutoff_not_an_observation": projected_age,
            "recorded_collection_strategy_unchanged": record.get("collection_strategy"),
            "owner_declared_high_response_selection": owner_selected,
            "outcome_selected": outcome_selected,
            "proposed_sampling_frame_requires_review": "high_response_protocol_v1" if outcome_selected else "",
            "prior_explicit_roles": "|".join(record.get("prior_explicit_roles") or []),
            "exclusion_reasons": "|".join(sorted(reasons)),
            "structurally_eligible_now": not reasons,
            "training_allowed_now": not reasons and training_gate["allowed"],
            "reviewed_format_to_fill": "",
            "format_source_evidence_to_fill": "",
            "reviewer_notes_to_fill": "",
        })
    minimums = partition_minimums(protocol)
    by_category = {}
    for category in CATEGORIES:
        members = [r for r in rows if r["category"] == category]
        by_category[category] = {
            "rows": len(members),
            "full_transcript_rows": sum(r["transcript_scope"] == "full_video" for r in members),
            "queues": dict(Counter(r["queue"] for r in members)),
            "development_roles": {
                role: {
                    "videos": len({r["video_id"] for r in members
                                   if r["queue"] == "development_review" and r["proposed_role_not_a_manifest"] == role}),
                    "channels": len({r["channel_id"] for r in members
                                     if r["queue"] == "development_review" and r["proposed_role_not_a_manifest"] == role}),
                } for role in ("fit", "tuning")
            },
        }
    # These age-only counts are optimistic upper bounds, not supported benchmark cells.
    projected_coverage = []
    for category in CATEGORIES:
        members = [r for r in rows if r["category"] == category and r["queue"] == "development_review"]
        age_key = "projected_age_if_refreshed_at_cutoff_not_an_observation"
        for age in sorted({r[age_key] for r in members} - {"unknown", "invalid"}):
            fit = [r for r in members if r[age_key] == age and r["proposed_role_not_a_manifest"] == "fit"]
            tuning = [r for r in members if r[age_key] == age and r["proposed_role_not_a_manifest"] == "tuning"]
            videos = len({r["video_id"] for r in fit})
            channels = len({r["channel_id"] for r in fit})
            min_videos = protocol["context_support"]["minimum_fit_videos"]
            min_channels = protocol["context_support"]["minimum_fit_channels"]
            projected_coverage.append({
                "category": category, "projected_age": age,
                "fit_videos": videos, "fit_channels": channels,
                "tuning_videos": len({r["video_id"] for r in tuning}),
                "tuning_channels": len({r["channel_id"] for r in tuning}),
                "fit_additional_count_lower_bound": max(0, min_videos - videos, min_channels - channels),
                "assumption": "same verified format and metric; refresh succeeds; labels and identity support untested",
                "supported_cell": False,
            })
    # Do not turn unverified legacy holdouts into certified new samples.
    holdout_gap = {}
    for role in ("calibration", "independent_test"):
        current = len({r["video_id"] for r in rows
                       if r["proposed_role_not_a_manifest"] == role and r["structurally_eligible_now"]})
        holdout_gap[role] = {
            "current_structurally_eligible_videos": current,
            "necessary_assessed_videos": minimums[role]["necessary_assessed_videos"],
            "unfilled_assessed_slots": max(0, minimums[role]["necessary_assessed_videos"] - current),
            "must_not_count_outcome_selected_or_unverified_legacy_rows": True,
            "not_a_guaranteed_new_video_quota": True,
        }
    summary = {
        "schema_version": "outcome-data-preparation-review-v1",
        "cutoff": cutoff.isoformat().replace("+00:00", "Z"),
        "protocol_sha256": protocol["protocol_sha256"],
        "active_rows": len(rows),
        "unique_videos": len({r["video_id"] for r in rows}),
        "unique_channels": len({r["channel_id"] for r in rows}),
        "owner_selected_rows": len(selected_ids),
        "outcome_selected_rows": sum(r["outcome_selected"] for r in rows),
        "structurally_eligible_now": sum(r["structurally_eligible_now"] for r in rows),
        "training_allowed_now": sum(r["training_allowed_now"] for r in rows),
        "training_data_use_gate": training_gate,
        "queue_counts": dict(Counter(r["queue"] for r in rows)),
        "by_category": by_category,
        "issue_counts": dict(Counter(reason for r in rows for reason in r["exclusion_reasons"].split("|") if reason)),
        "development_issue_counts": dict(Counter(reason for r in rows if r["queue"] == "development_review"
                                                 for reason in r["exclusion_reasons"].split("|") if reason)),
        "partition_minimums": minimums,
        "holdout_gap": holdout_gap,
        "projected_age_coverage_not_actual_support": projected_coverage,
        "exact_additional_collection_count": None,
        "exact_count_blockers": ["confirmed_format", "compatible_metric_and_age_cells", "disjoint_channels_and_identities",
                                 "two_labels_and_topic_support", "calibration_bins_with_ties", "sampling_provenance", "data_use"],
        "labels_or_test_scores_computed": False,
        "production_data_modified": False,
        "records": rows,
    }
    return summary


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            # Public text can begin with spreadsheet formulas; export inert review cells.
            writer.writerow({key: "'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@")) else value
                             for key, value in row.items()})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cutoff", required=True, type=parse_cutoff)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--owner-confirmed-notebooklm-high-response", required=True, action="store_true",
                        help="Explicit owner statement; not inferred from collection_strategy")
    parser.add_argument("--owner-statement", required=True)
    args = parser.parse_args()
    protocol = json.loads((ROOT / "docs/implementation/outcome-prediction-protocol-v1.json").read_text(encoding="utf-8"))
    rights = json.loads((ROOT / "docs/implementation/outcome-prediction-data-use-v1.json").read_text(encoding="utf-8"))
    if not validate_protocol(protocol)["valid"] or not data_use_gate(rights, "audit")["allowed"]:
        raise SystemExit("Audit permission or frozen protocol invalid")

    from app.database.db import SessionLocal, engine
    from app.database.models import DatasetContent

    with reject_database_writes(engine):
        with SessionLocal() as db:
            before = database_identity(db)
            records = database_source_records(db, cutoff=args.cutoff, protocol=protocol, repo_root=ROOT)
            sources = db.query(DatasetContent.dataset_id, DatasetContent.dataset_source,
                               DatasetContent.transcript_acquisition_method).all()
            active_ids = {r["dataset_id"] for r in records}
            selected_ids = {row.dataset_id for row in sources if row.dataset_id in active_ids
                            and row.dataset_source == "youtube_public_research"
                            and row.transcript_acquisition_method == "notebooklm_manual_source"}
            after = database_identity(db)
            db.rollback()
    if before != after:
        raise SystemExit("Database identity changed during read-only audit; retry with a stable snapshot")
    report = prepare_review(records, selected_ids=selected_ids, cutoff=args.cutoff,
                            protocol=protocol, training_gate=data_use_gate(rights, "training"))
    report.update(database_unchanged=True, database_identity_before=before, database_identity_after=after)
    confirmation = {
        "status": "owner_declared_selection_only_not_rights_confirmation",
        "owner_statement": args.owner_statement,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Only the enumerated active NotebookLM Phone/Camera/Laptop rows at this audit",
        "interpretation": "Selected primarily for high views/engagement, not proof every selected clip is high performing",
        "database_write_authorized": False,
        "training_rights_confirmed": False,
        "identities": [{k: r[k] for k in ("dataset_id", "source_youtube_id", "transcript_sha256")}
                       for r in records if r["dataset_id"] in selected_ids],
    }
    confirmation["sha256"] = sha256_json(confirmation)
    report["selection_confirmation_sha256"] = confirmation["sha256"]
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "selection-confirmation.json", confirmation)
    write_json(output / "preparation-report.json", report)
    review_rows = report.pop("records")
    if review_rows:
        fields = list(review_rows[0])
        write_csv(output / "all-review-rows.csv", review_rows, fields)
        for index, queue in enumerate(QUEUES, 1):
            write_csv(output / f"{index:02d}-{queue}.csv", [r for r in review_rows if r["queue"] == queue], fields)
    coverage = report.pop("projected_age_coverage_not_actual_support")
    if coverage:
        write_csv(output / "projected-age-coverage.csv", coverage, list(coverage[0]))
    write_json(output / "summary.json", report)
    print(json.dumps({k: report[k] for k in ("active_rows", "owner_selected_rows", "queue_counts",
                                           "training_allowed_now", "database_unchanged")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
