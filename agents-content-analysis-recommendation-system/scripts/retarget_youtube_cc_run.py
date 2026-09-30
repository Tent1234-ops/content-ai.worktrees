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
from app.services.taxonomy import sync_taxonomy_registry
from app.services.youtube_cc_dataset import (
    YouTubeCCDatasetError,
    retarget_youtube_cc_collection_languages,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Narrow an unfinished, unreviewed YouTube collection run to a "
            "smaller transcript-language set while archiving excluded candidates."
        )
    )
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument(
        "--languages",
        default="th",
        help="Comma-separated target languages (default: th)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    languages = tuple(
        item.strip().lower()
        for item in str(args.languages).split(",")
        if item.strip()
    )
    Base.metadata.create_all(bind=engine)
    migrate_phase13_taxonomy_schema(engine)
    migrate_youtube_cc_dataset_schema(engine)
    migrate_view_metric_schema(engine)
    db = SessionLocal()
    try:
        sync_taxonomy_registry(db)
        result = retarget_youtube_cc_collection_languages(
            db,
            collection_run_id=args.run_id,
            languages=languages,
        )
        progress = result.get("progress") or {}
        print(
            json.dumps(
                {
                    "collection_run_id": result.get("collection_run_id"),
                    "status": result.get("status"),
                    "languages": (result.get("config") or {}).get("languages"),
                    "accepted": progress.get("accepted_total"),
                    "target": progress.get("target_total"),
                    "remaining": progress.get("remaining_total"),
                    "retarget": result.get("retarget"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except YouTubeCCDatasetError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
