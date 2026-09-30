from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from app.database.db import Base, SessionLocal, engine
from app.database.migrations import (
    migrate_phase13_taxonomy_schema,
    migrate_view_metric_schema,
    migrate_youtube_cc_dataset_schema,
)
from app.services.youtube_cc_dataset import (
    YouTubeCCDatasetError,
    import_reviewed_youtube_cc_dataset,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import only human-reviewed public YouTube transcript candidates."
    )
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Exit 1 unless all 12 leaves have at least 30 approved rows",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    Base.metadata.create_all(bind=engine)
    migrate_phase13_taxonomy_schema(engine)
    migrate_youtube_cc_dataset_schema(engine)
    migrate_view_metric_schema(engine)
    db = SessionLocal()
    try:
        result = import_reviewed_youtube_cc_dataset(
            db,
            candidate_path=args.candidates,
            review_path=args.reviews,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.require_ready and not bool(result["coverage"]["ready"]):
            return 1
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except YouTubeCCDatasetError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
