"""Read current collection gaps and preview fixed channel splits without API calls."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database.db import SessionLocal
from app.services.model_management import training_dataset
from app.services.classification_collection_plan import preview_collection_channels


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", action="append", default=[], help="YouTube channel ID, repeat up to 50 times")
    parser.add_argument("--output", type=Path, help="Optional NEW JSON file; existing files are never overwritten")
    args = parser.parse_args()
    with SessionLocal() as db:
        report = training_dataset(db)
        result = {"dataset_fingerprint": report["dataset_fingerprint"],
                  "collection_plan": report["collection_plan"], "database_changed": False}
        if args.channel:
            result["channel_preview"] = preview_collection_channels(db, args.channel)
        db.rollback()
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(payload)
    print(payload)


if __name__ == "__main__":
    main()
