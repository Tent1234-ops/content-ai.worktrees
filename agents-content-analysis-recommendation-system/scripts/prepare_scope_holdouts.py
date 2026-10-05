"""Preview, then explicitly apply an immutable channel holdout plan."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database.db import SessionLocal, engine
from app.database.models import DatasetSplitPlan
from app.services.dataset_split_plan import apply_scope_holdout_plan, plan_digest, propose_scope_holdout_plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--apply", type=Path)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--admin-user-id", type=int)
    args = parser.parse_args()
    with SessionLocal() as db:
        if args.apply:
            if not args.expected_sha256 or not args.admin_user_id:
                parser.error("Apply requires --expected-sha256 and --admin-user-id")
            payload = json.loads(args.apply.read_text(encoding="utf-8"))
            DatasetSplitPlan.__table__.create(engine, checkfirst=True)
            report = apply_scope_holdout_plan(db, payload, expected_sha256=args.expected_sha256,
                                             user_id=args.admin_user_id)
            print(json.dumps({"applied": payload["version"], "counts": payload["counts_after"],
                              "dataset_fingerprint": report["dataset_fingerprint"],
                              "partition_integrity_passed": report["partition_integrity_passed"]}))
        else:
            if not args.output or not args.version:
                parser.error("Preview requires --version and --output")
            plan = propose_scope_holdout_plan(db, version=args.version)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as output:
                json.dump(plan, output, ensure_ascii=True, indent=2)
            print(json.dumps({"preview": str(args.output), "sha256": plan_digest(plan),
                              "counts": plan["counts_after"], "changed_rows": len(plan["changes"]),
                              "database_changed": False}))


if __name__ == "__main__":
    main()
