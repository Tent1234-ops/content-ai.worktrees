"""Create an immutable fail-closed Outcome Prediction Phase 6 evidence bundle."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("CONTENT_AI_SKIP_DB_BOOTSTRAP", "1")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database.db import SessionLocal, engine  # noqa: E402
from app.services.outcome_final_evaluation import (  # noqa: E402
    build_phase6_reports,
    write_phase6_bundle,
)
from app.services.outcome_model_management import training_overview  # noqa: E402
from app.services.outcome_prediction_readiness import reject_database_writes  # noqa: E402


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readiness", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--browser-evidence", type=Path)
    parser.add_argument("--backend-test-count", required=True, type=int)
    parser.add_argument("--flutter-test-count", required=True, type=int)
    parser.add_argument("--flutter-analyze-passed", action="store_true")
    parser.add_argument("--web-build-passed", action="store_true")
    parser.add_argument("--backend-command", default="py -m unittest discover -s tests -q")
    parser.add_argument("--flutter-command", default="flutter test --no-pub")
    parser.add_argument("--flutter-analyze-command", default="flutter analyze --no-pub")
    parser.add_argument("--web-build-command", default="flutter build web --release --no-pub")
    parser.add_argument(
        "--phase5-freeze", type=Path,
        default=ROOT / "docs/implementation/outcome-prediction-phase-5-freeze.json",
    )
    parser.add_argument(
        "--data-use", type=Path,
        default=ROOT / "docs/implementation/outcome-prediction-data-use-v1.json",
    )
    parser.add_argument(
        "--utility-protocol", type=Path,
        default=ROOT / "docs/implementation/outcome-prediction-utility-study-v1.json",
    )
    args = parser.parse_args()

    readiness = _json(args.readiness)
    freeze = _json(args.phase5_freeze)
    data_use = _json(args.data_use)
    utility_protocol = _json(args.utility_protocol)
    browser = _json(args.browser_evidence) if args.browser_evidence else None

    with reject_database_writes(engine):
        with SessionLocal() as db:
            overview = training_overview(db)
            db.rollback()

    browser_passed = bool(browser and browser.get("passed") is True)
    software_evidence = {
        "schema_version": "outcome-phase6-software-evidence-v1",
        "backend_tests": {
            "passed": args.backend_test_count > 0,
            "count": args.backend_test_count,
            "command": args.backend_command,
        },
        "flutter_tests": {
            "passed": args.flutter_test_count > 0,
            "count": args.flutter_test_count,
            "command": args.flutter_command,
        },
        "flutter_analyze": {
            "passed": args.flutter_analyze_passed,
            "command": args.flutter_analyze_command,
        },
        "web_build": {
            "passed": args.web_build_passed,
            "command": args.web_build_command,
        },
        "browser": {
            "passed": browser_passed,
            "artifact": str(args.browser_evidence) if args.browser_evidence else None,
            "screenshot_count": len((browser or {}).get("screenshots") or []),
            "errors": (browser or {}).get("errors"),
        },
        "note": "Counts and commands are supplied only after successful local runs; raw console output remains in the Handoff.",
    }
    reports = build_phase6_reports(
        readiness=readiness,
        phase5_freeze=freeze,
        data_use=data_use,
        utility_protocol=utility_protocol,
        outcome_overview=overview,
        browser_evidence=browser,
        software_evidence=software_evidence,
    )
    result = write_phase6_bundle(args.output_dir, reports)
    print(json.dumps({
        "status": "complete",
        **result,
        "decision": reports["release-decision.json"]["decision"],
        "independent_test_opened": False,
        "phase7_started": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
