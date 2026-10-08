"""Create a deterministic read-only Outcome Prediction Phase 1 audit."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("CONTENT_AI_SKIP_DB_BOOTSTRAP", "1")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database.db import SessionLocal, engine  # noqa: E402
from app.services.outcome_prediction_readiness import (  # noqa: E402
    audit_outcome_readiness,
    database_identity,
    reject_database_writes,
    sha256_json,
    validate_protocol,
)


def parse_cutoff(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("--cutoff must include UTC offset or Z")
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def _summary_markdown(audit: dict, protocol_check: dict) -> str:
    dataset = audit["dataset"]
    stats = audit["statistics"]
    holdout = audit["holdout"]
    classifier = audit["active_classifier"]
    classifier_readiness = classifier.get("readiness") or {}
    lines = [
        "# Outcome Prediction Phase 1 readiness audit", "",
        f"- Captured: `{audit['captured_at']}`",
        f"- Frozen cutoff: `{audit['cutoff']}`",
        f"- Audit SHA-256: `{audit['audit_sha256']}`",
        f"- Protocol SHA-256: `{protocol_check['protocol_sha256']}`",
        f"- Database unchanged: **{str(audit['database_unchanged']).lower()}**", "",
        "## Decision", "",
        f"- Software audit: `{audit['decisions']['software_readiness_audit']}`",
        f"- Data rights: `{audit['decisions']['data_rights']}`",
        f"- Real training: `{audit['decisions']['real_training']}`",
        f"- Real serving: `{audit['decisions']['real_serving']}`",
        f"- Prediction qualified: `{str(audit['decisions']['prediction_qualified']).lower()}`", "",
        "Phase 1 does not train a model. Row counts are not treated as independent samples, and no Test outcomes were used to choose features or thresholds.", "",
        "## Dataset", "",
        f"- Active Phone/Camera/Laptop rows: **{dataset['active_target_rows']}**",
        f"- Unique Video IDs: **{dataset['independent_video_ids']}**",
        f"- Unique channels: **{dataset['independent_channels']}**",
        f"- Classification production-contract rows: **{dataset['classification_production_contract_rows']}**",
        f"- Current reference-eligible rows: **{dataset['reference_eligible_rows']}**",
        f"- Structurally ready before rights/outcome split: **{dataset['structurally_ready_without_rights_or_outcome_split']}**",
        f"- Training-allowed rows after rights gate: **{dataset['training_allowed_rows']}**", "",
        "### Rows by category", "",
        "| Category | Rows | Structurally ready channels |",
        "|---|---:|---:|",
    ]
    for category in ("phone", "camera", "laptop"):
        coverage = audit["coverage"].get(category, {})
        lines.append(
            f"| {category} | {dataset['by_category'].get(category, 0)} | {coverage.get('structurally_ready_channels', 0)} |"
        )
    lines.extend([
        "", "## Statistics", "",
        f"- Observation rows: **{stats['observation_rows']}** (these are not independent videos)",
        f"- Videos with a successful views observation before cutoff: **{stats['videos_with_any_successful_views']}**",
        f"- Videos with at least two successful observations: **{stats['videos_with_two_or_more_successful_observations']}**",
        f"- Collector selector: `{stats['collector_scope']['selector']}`; train-only reference scope = `{str(stats['collector_scope']['train_only']).lower()}`",
        "- Existing collector does not collect protected holdout rows through a separate manifest path.", "",
        "## Holdout and prior use", "",
        f"- Existing classification Validation/Test rows: **{holdout['classification_holdout_rows']}**",
        f"- With structurally usable recent outcome: **{holdout['with_recent_structural_outcome']}**",
        f"- Missing/invalid outcome inputs: **{holdout['missing_or_invalid_outcome']}**",
        f"- With explicit prior artifact roles: **{holdout['with_explicit_prior_artifact_roles']}**",
        f"- Fresh Outcome Test demonstrated: **{holdout['fresh_outcome_test_count']}**",
        "", "## Active classifier dependency", "",
        f"- Model ID: `{classifier.get('model_id')}`",
        f"- Registry status: `{classifier.get('status')}`",
        f"- Readiness: `{classifier_readiness.get('status')}`",
        f"- Can accept predictions: `{str(bool(classifier_readiness.get('can_accept_predictions'))).lower()}`",
        f"- Reasons: `{', '.join(classifier_readiness.get('reason_codes') or []) or 'none'}`", "",
        "## Gaps", "",
        f"Total actionable gap rows: **{len(audit['gaps'])}**. See `gaps.csv` and `gaps.json` for exact rows, owners and deadlines.", "",
        "Global blockers:", "",
    ])
    for gap in [item for item in audit["gaps"] if item["dataset_id"] is None]:
        lines.append(f"- `{gap['reason_code']}`: {gap['suggested_action']} (owner `{gap['owner']}`, deadline `{gap['deadline']}`)")
    lines.extend([
        "", "## Limitations", "",
        "- Structural readiness is not an Outcome split and is not permission to train.",
        "- Artifact scanning only proves explicit JSON/JSONL use; undocumented prior human use remains unknown.",
        "- No Outcome labels, topic associations, model metrics or probabilities were calculated in this audit.",
        "- Data-use status remains unverified until the project owner supplies applicable confirmation evidence.",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cutoff", required=True, type=parse_cutoff,
                        help="Frozen UTC cutoff, for example 2026-10-08T12:00:00Z")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--protocol", type=Path,
                        default=ROOT / "docs/implementation/outcome-prediction-protocol-v1.json")
    parser.add_argument("--data-use", type=Path,
                        default=ROOT / "docs/implementation/outcome-prediction-data-use-v1.json")
    args = parser.parse_args()

    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    protocol_check = validate_protocol(protocol)
    if not protocol_check["valid"]:
        print(json.dumps({"status": "invalid_protocol", **protocol_check}, ensure_ascii=False))
        return 2
    data_use = json.loads(args.data_use.read_text(encoding="utf-8"))

    with reject_database_writes(engine):
        with SessionLocal() as db:
            before = database_identity(db)
            audit = audit_outcome_readiness(
                db, cutoff=args.cutoff, repo_root=ROOT, data_use_record=data_use,
                latest_observation_hours=int(protocol["cutoff_policy"]["latest_successful_observation_max_age_hours"]),
            )
            after = database_identity(db)
            db.rollback()
    audit["database_identity_before"] = before
    audit["database_identity_after"] = after
    audit["database_unchanged"] = before == after
    audit["protocol"] = protocol_check
    audit.pop("audit_sha256", None)
    audit["audit_sha256"] = sha256_json(audit)
    if not audit["database_unchanged"]:
        print(json.dumps({"status": "database_changed", "before": before, "after": after}))
        return 3

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    _write_json(output_dir / "readiness.json", audit)
    _write_json(output_dir / "protocol-validation.json", protocol_check)
    _write_json(output_dir / "data-use-decision.json", data_use)
    _write_json(output_dir / "gaps.json", {
        "schema_version": "outcome-readiness-gaps-v1",
        "cutoff": audit["cutoff"],
        "audit_sha256": audit["audit_sha256"],
        "items": audit["gaps"],
    })
    gap_fields = [
        "gap_id", "dataset_id", "video_id", "category", "current_split",
        "split_protection", "missing_field", "reason_code", "suggested_action",
        "owner", "deadline", "blocking_phase2",
    ]
    with (output_dir / "gaps.csv").open("x", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=gap_fields)
        writer.writeheader()
        writer.writerows(audit["gaps"])
    (output_dir / "summary.md").write_text(
        _summary_markdown(audit, protocol_check), encoding="utf-8"
    )
    print(json.dumps({
        "status": "complete", "output_dir": str(output_dir),
        "database_unchanged": audit["database_unchanged"],
        "active_rows": audit["dataset"]["active_target_rows"],
        "structurally_ready": audit["dataset"]["structurally_ready_without_rights_or_outcome_split"],
        "training_allowed": audit["dataset"]["training_allowed_rows"],
        "gaps": len(audit["gaps"]),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
