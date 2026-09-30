from __future__ import annotations

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
from app.database.migrations import migrate_phase13_taxonomy_schema
from app.services.taxonomy import sync_taxonomy_registry, taxonomy_coverage


def migrate() -> dict[str, object]:
    Base.metadata.create_all(bind=engine)
    schema = migrate_phase13_taxonomy_schema(engine)
    db = SessionLocal()
    try:
        registry = sync_taxonomy_registry(db)
        coverage = taxonomy_coverage(db)
    finally:
        db.close()
    return {
        "status": "ok",
        "schema": schema,
        "registry": registry,
        "coverage": coverage,
    }


if __name__ == "__main__":
    print(json.dumps(migrate(), ensure_ascii=False, indent=2))
