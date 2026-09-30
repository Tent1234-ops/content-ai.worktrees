"""Audit stored trend titles and prepare/validate a human topic evaluation set."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="Read-only database audit; never calls provider APIs")
    export.add_argument("--days", type=int, default=90)
    export.add_argument("--region", default="TH")
    export.add_argument("--size", type=int, default=200)
    export.add_argument("--test-size", type=int, default=100)
    export.add_argument("--seed", type=int, default=20260925)
    export.add_argument("--output", type=Path)
    validate = commands.add_parser("validate", help="Validate frozen sources and human labels")
    validate.add_argument("--bundle", type=Path, required=True)
    validate.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    # Auditing existing sources must not trigger the app's schema bootstrap.
    os.environ["CONTENT_AI_SKIP_DB_BOOTSTRAP"] = "1"
    from app.services.trend_topic_preparation import (
        inspect_topic_sources, validate_preparation_bundle, write_preparation_bundle,
    )
    if args.command == "validate":
        result = validate_preparation_bundle(args.bundle)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["valid"] and (not args.require_complete or result["ready_for_evaluation"]) else 1
    from app.database.db import SessionLocal
    now = datetime.utcnow()
    output = args.output or ROOT / "artifacts" / "trend-topics" / "evaluation" / now.strftime("%Y%m%dT%H%M%S%fZ")
    if output.exists():
        parser.error("Output already exists. Frozen evaluation sets must not be overwritten.")
    with SessionLocal() as db:
        report, candidates, observations = inspect_topic_sources(
            db, region=args.region, days=args.days, now=now)
    manifest = write_preparation_bundle(output, report, candidates, observations,
                                        size=args.size, test_size=args.test_size, seed=args.seed)
    result = validate_preparation_bundle(output)
    print(json.dumps({"bundle": str(output.resolve()), "candidate_videos": len(candidates),
                      "selection": manifest["selection"], "validation": result}, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
