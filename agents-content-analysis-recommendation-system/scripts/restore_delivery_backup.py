"""Restore a delivery backup into an empty, explicitly separate database."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("CONTENT_AI_SKIP_DB_BOOTSTRAP", "1")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, inspect, select  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.database import models  # noqa: E402,F401
from app.database.db import Base  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decode_value(value):
    if not isinstance(value, dict) or "$type" not in value:
        return value
    kind = value["$type"]
    raw = value["value"]
    if kind == "datetime":
        return datetime.fromisoformat(raw)
    if kind == "date":
        return date.fromisoformat(raw)
    if kind == "time":
        return time.fromisoformat(raw)
    if kind == "decimal":
        return Decimal(raw)
    if kind == "bytes":
        return base64.b64decode(raw)
    raise ValueError(f"Unknown encoded value type: {kind}")


def restore(backup: Path, database_url: str, report_path: Path | None = None) -> dict:
    manifest_path = backup / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_manifest = (backup / "manifest.sha256").read_text(encoding="ascii").split()[0]
    if sha256_file(manifest_path) != expected_manifest:
        raise RuntimeError("Backup manifest checksum mismatch")

    target_url = make_url(database_url)
    source = manifest["source_database"]
    if (target_url.get_backend_name() == source["dialect"] and
            str(target_url.database or "") == str(source["database"] or "")):
        raise RuntimeError("Refusing to restore into the source database")
    if target_url.get_backend_name() != "sqlite":
        raise RuntimeError("This verified restore path accepts SQLite only; use a separate empty SQLite URL")

    target_file = Path(target_url.database).resolve() if target_url.database not in {None, ":memory:"} else None
    if target_file and target_file.exists() and target_file.stat().st_size:
        raise RuntimeError(f"Refusing to overwrite non-empty target file: {target_file}")
    if target_file:
        target_file.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    try:
        if inspect(engine).get_table_names():
            raise RuntimeError("Restore target must not contain tables")
        Base.metadata.create_all(engine)
        restored = []
        with engine.begin() as connection:
            for table_info in manifest["database_tables"]:
                table = Base.metadata.tables.get(table_info["name"])
                if table is None:
                    raise RuntimeError(f"Current schema is missing table {table_info['name']}")
                path = backup / "database" / f"{table.name}.jsonl"
                if sha256_file(path) != table_info["sha256"]:
                    raise RuntimeError(f"Checksum mismatch: {table.name}")
                batch = []
                with path.open("r", encoding="utf-8") as handle:
                    for raw in handle:
                        payload = json.loads(raw)
                        batch.append({key: decode_value(value) for key, value in payload.items()})
                        if len(batch) >= 500:
                            connection.execute(table.insert(), batch)
                            batch.clear()
                if batch:
                    connection.execute(table.insert(), batch)
                actual = connection.execute(select(table)).fetchall()
                if len(actual) != table_info["row_count"]:
                    raise RuntimeError(
                        f"Row-count mismatch for {table.name}: {len(actual)} != {table_info['row_count']}"
                    )
                restored.append({"name": table.name, "row_count": len(actual)})
        report = {
            "schema_version": "content-ai-delivery-restore-report-v1",
            "restored_at": datetime.now(timezone.utc).isoformat(),
            "backup_manifest_sha256": expected_manifest,
            "target": {"dialect": "sqlite", "path": str(target_file) if target_file else ":memory:"},
            "source_database_was_not_modified": True,
            "tables": restored,
            "row_total": sum(item["row_count"] for item in restored),
            "passed": True,
        }
        if report_path:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = restore(args.backup.resolve(), args.database_url, args.report.resolve() if args.report else None)
    print(json.dumps({"passed": True, "tables": len(report["tables"]), "rows": report["row_total"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
