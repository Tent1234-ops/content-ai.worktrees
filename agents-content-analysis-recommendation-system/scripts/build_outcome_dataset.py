#!/usr/bin/env python
"""Build a frozen Outcome dataset or an honest blocked readiness artifact."""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("CONTENT_AI_SKIP_DB_BOOTSTRAP", "1")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database.db import SessionLocal, engine  # noqa: E402
from app.services.outcome_dataset import (  # noqa: E402
    database_source_records,
    fit_benchmarks,
    freeze_manifest,
    label_records,
    phase2_readiness_report,
)
from app.services.outcome_prediction_readiness import (  # noqa: E402
    database_identity,
    reject_database_writes,
    validate_protocol,
)


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise argparse.ArgumentTypeError("cutoff must be an explicit UTC timestamp ending in Z or +00:00")
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cutoff", required=True, type=parse_utc)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--protocol", type=Path,
        default=ROOT / "docs/implementation/outcome-prediction-protocol-v1.json",
    )
    parser.add_argument(
        "--data-use-record", type=Path,
        default=ROOT / "docs/implementation/outcome-prediction-data-use-v1.json",
    )
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("output directory already exists; Phase 2 artifacts are immutable")
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    data_use = json.loads(args.data_use_record.read_text(encoding="utf-8"))
    protocol_result = validate_protocol(protocol)
    if not protocol_result["valid"]:
        print(json.dumps(protocol_result, ensure_ascii=False))
        return 2

    args.output_dir.mkdir(parents=True)
    with SessionLocal() as db:
        before = database_identity(db)
        with reject_database_writes(engine):
            report, exclusions, schema = phase2_readiness_report(
                db, cutoff=args.cutoff, protocol=protocol,
                data_use_record=data_use, repo_root=ROOT,
            )
        after = database_identity(db)
        if before != after:
            raise RuntimeError("Phase 2 readiness audit changed the database")

        report["database_unchanged"] = True
        report["database_identity_sha256"] = before["identity_sha256"]
        write_json(args.output_dir / "build-report.json", report)
        write_json(args.output_dir / "exclusions.json", exclusions)
        write_json(args.output_dir / "feature-schema.json", schema)
        fields = [
            "dataset_id", "source_youtube_id", "category", "source_split",
            "intended_outcome_role", "split_protection", "reason_codes",
        ]
        with (args.output_dir / "exclusions.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for item in exclusions:
                writer.writerow({**item, "reason_codes": "|".join(item["reason_codes"])})

        if report["status"] == "ready_to_freeze":
            records = database_source_records(
                db, cutoff=args.cutoff, protocol=protocol, repo_root=ROOT
            )
            frozen = freeze_manifest(
                records, cutoff=args.cutoff, protocol=protocol,
                data_use_record=data_use,
            )
            if frozen.get("manifest"):
                write_json(args.output_dir / "manifest.json", frozen["manifest"])
                write_json(args.output_dir / "features.json", frozen["feature_records"])
                development = [
                    item for item in records
                    if not item["exclusion_reasons"] and item["outcome_role"] != "independent_test"
                ]
                benchmarks = fit_benchmarks(development, protocol)
                write_json(args.output_dir / "fit-benchmarks.json", benchmarks)
                write_json(
                    args.output_dir / "development-labels.json",
                    label_records(development, benchmarks),
                )
                report["manifest_created"] = True
                report["manifest_sha256"] = frozen["manifest"]["manifest_sha256"]
                write_json(args.output_dir / "build-report.json", report)

    summary = [
        "# Outcome Prediction Phase 2 dataset build",
        "",
        f"- Status: `{report['status']}`",
        f"- Frozen cutoff: `{report['cutoff_utc']}`",
        f"- Protocol SHA-256: `{report['protocol_sha256']}`",
        f"- Database unchanged: **{str(report['database_unchanged']).lower()}**",
        f"- Source videos: **{report['independent_video_ids']}**",
        f"- Source channels: **{report['channels']}**",
        f"- Structurally eligible: **{report['structurally_eligible_rows']}**",
        f"- Training allowed: **{report['training_allowed_rows']}**",
        f"- Frozen manifest created: **{str(report['manifest_created']).lower()}**",
        f"- Independent Test labels opened: **{str(report['independent_test_labels_opened']).lower()}**",
        "",
        "A blocked readiness report is not a training dataset and must not be used by Phase 3.",
    ]
    (args.output_dir / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"], "database_unchanged": True,
        "videos": report["independent_video_ids"],
        "eligible": report["structurally_eligible_rows"],
        "manifest_created": report["manifest_created"],
        "output_dir": str(args.output_dir),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
