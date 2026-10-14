"""Freeze or evaluate one registered Outcome candidate; activation is separate."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("CONTENT_AI_SKIP_DB_BOOTSTRAP", "1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database.db import SessionLocal
from app.services.outcome_independent_evaluation import freeze_candidate, evaluate_candidate
from app.services.outcome_model_management import ARTIFACT_ROOT, PHASE2_ROOT, PROTOCOL_PATH, DATA_USE_PATH


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", type=int, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--actor", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--freeze-only", action="store_true")
    mode.add_argument("--confirm-open-test", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.confirm_open_test and args.output_dir is None:
        parser.error("--output-dir is required to evaluate; existing output cannot be overwritten")
    inputs = dict(model_id=args.model_id, manifest_path=args.manifest, features_path=args.features,
                  protocol_path=PROTOCOL_PATH, data_use_path=DATA_USE_PATH, trusted_root=ARTIFACT_ROOT,
                  phase2_root=PHASE2_ROOT, repo_root=ROOT)
    with SessionLocal() as db:
        if args.freeze_only:
            result = freeze_candidate(db, output_path=args.freeze, actor=args.actor, **inputs)
            db.rollback()
            print(json.dumps({"status": "frozen", "freeze_sha256": result["freeze_sha256"], "test_opened": False}))
        else:
            result = evaluate_candidate(
                db, freeze_path=args.freeze, output_dir=args.output_dir,
                ledger_root=ARTIFACT_ROOT.parent / "independent-test-access",
                actor=args.actor, confirm_open_test=True, **inputs,
            )
            print(json.dumps({"status": result["status"], "production_eligible": result["production_eligible"],
                              "active_model_changed": False, "run_id": result["run_id"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
