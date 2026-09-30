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

from app.database.db import SessionLocal
from app.services.classification_training import (
    ClassificationTrainingError,
    activate_classification_model,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Activate one qualified classification model for Analyze Clip."
    )
    parser.add_argument("--model-id", type=int, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db = SessionLocal()
    try:
        result = activate_classification_model(db, args.model_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ClassificationTrainingError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
