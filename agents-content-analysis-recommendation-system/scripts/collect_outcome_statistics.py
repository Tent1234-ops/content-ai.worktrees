#!/usr/bin/env python
"""Plan explicit-manifest collection; live mode requires two explicit flags."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

os.environ.setdefault("CONTENT_AI_SKIP_DB_BOOTSTRAP", "1")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.outcome_statistics import collect_outcome_statistics  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--data-use-record", type=Path,
        default=ROOT / "docs/implementation/outcome-prediction-data-use-v1.json",
    )
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--approve-live", action="store_true")
    args = parser.parse_args()
    if args.live and not args.approve_live:
        parser.error("--live also requires --approve-live")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    data_use = json.loads(args.data_use_record.read_text(encoding="utf-8"))
    result = collect_outcome_statistics(
        manifest=manifest, data_use_record=data_use,
        now=datetime.utcnow(), dry_run=not args.live,
        approved=args.approve_live,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") in {"ready", "completed", "partial", "already_collected"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
