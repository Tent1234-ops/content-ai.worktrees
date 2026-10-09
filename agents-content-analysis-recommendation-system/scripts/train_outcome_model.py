#!/usr/bin/env python
"""Train/validate an Outcome candidate without opening Independent Test."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("CONTENT_AI_SKIP_DB_BOOTSTRAP", "1")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.outcome_training import train_and_validate_outcome_model  # noqa: E402
from app.services.outcome_training_fixture import write_synthetic_fixture  # noqa: E402


def _write(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--phase2-dir", type=Path)
    parser.add_argument("--synthetic-fixture", action="store_true")
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
        parser.error("output directory already exists; Phase 3 artifacts are immutable")
    if args.synthetic_fixture and args.phase2_dir:
        parser.error("choose either --synthetic-fixture or --phase2-dir")
    if not args.synthetic_fixture and not args.phase2_dir:
        parser.error("--phase2-dir is required for a real-data run")

    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    if args.synthetic_fixture:
        args.output_dir.mkdir(parents=True)
        fixture = write_synthetic_fixture(args.output_dir / "fixture-input", protocol)
        result = train_and_validate_outcome_model(
            manifest_path=fixture["manifest_path"],
            features_path=fixture["features_path"],
            protocol_path=args.protocol,
            data_use_path=fixture["data_use_path"],
            output_dir=args.output_dir / "fixture-model",
            trusted_phase2_root=args.output_dir / "fixture-input",
            source_kind="synthetic_fixture",
        )
    else:
        phase2 = args.phase2_dir.resolve()
        manifest = phase2 / "manifest.json"
        features = phase2 / "features.json"
        if not manifest.is_file() or not features.is_file():
            args.output_dir.mkdir(parents=True)
            build_report = {}
            if (phase2 / "build-report.json").is_file():
                build_report = json.loads(
                    (phase2 / "build-report.json").read_text(encoding="utf-8")
                )
            result = {
                "schema_version": "outcome-training-report-v1",
                "status": "blocked",
                "source_kind": "real",
                "reason_codes": ["phase2_frozen_manifest_missing"],
                "phase2_status": build_report.get("status"),
                "artifact_created": False,
                "independent_test_opened": False,
                "production_eligible": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            _write(args.output_dir / "preflight-report.json", result)
        else:
            result = train_and_validate_outcome_model(
                manifest_path=manifest,
                features_path=features,
                protocol_path=args.protocol,
                data_use_path=args.data_use_record,
                output_dir=args.output_dir,
                trusted_phase2_root=phase2,
                source_kind="real",
            )
            if not result.get("artifact_created"):
                args.output_dir.mkdir(parents=True, exist_ok=True)
                _write(args.output_dir / "preflight-report.json", result)
    print(json.dumps({
        "status": result.get("status"),
        "source_kind": result.get("source_kind", "synthetic_fixture" if args.synthetic_fixture else "real"),
        "artifact_created": result.get("artifact_created", False),
        "independent_test_opened": False,
        "production_eligible": False,
        "output_dir": str(args.output_dir.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
