"""Create a private, checksummed delivery backup without copying .env secrets."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import sys
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("CONTENT_AI_SKIP_DB_BOOTSTRAP", "1")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect, select  # noqa: E402

from app.database import models  # noqa: E402,F401
from app.database.db import Base, SessionLocal, engine  # noqa: E402
from app.database.models import ClassificationModel  # noqa: E402

SCHEMA_VERSION = "content-ai-private-delivery-backup-v1"
VERSION_FILES = (
    "app/services/taxonomy.py",
    "app/services/recommendation_templates.json",
    "app/services/actionable_recommendations.py",
    "app/services/recommendation_evidence.py",
    "app/services/topic_comparisons.py",
    "app/services/revision_comparisons.py",
    "app/services/nlp.py",
    "requirements.txt",
    "frontend_flutter/pubspec.lock",
    ".env.example",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def encode_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return {"$type": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"$type": "date", "value": value.isoformat()}
    if isinstance(value, time):
        return {"$type": "time", "value": value.isoformat()}
    if isinstance(value, Decimal):
        return {"$type": "decimal", "value": str(value)}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"$type": "bytes", "value": base64.b64encode(bytes(value)).decode("ascii")}
    raise TypeError(f"Unsupported backup value type: {type(value).__name__}")


def encode_row(row: dict) -> str:
    payload = {key: encode_value(value) for key, value in row.items()}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _table_order(table):
    primary = [column for column in table.primary_key.columns]
    return primary or list(table.columns)


def _copy_asset(source: Path, output: Path, *, label: str) -> dict:
    relative = source.resolve().relative_to(ROOT)
    target = output / "assets" / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return {
        "label": label,
        "path": relative.as_posix(),
        "sha256": sha256_file(target),
        "size": target.stat().st_size,
    }


def create_backup(output: Path) -> dict:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing backup: {output}")
    output.mkdir(parents=True)
    table_dir = output / "database"
    table_dir.mkdir()

    inspector = inspect(engine)
    source_tables = set(inspector.get_table_names())
    model_tables = {table.name for table in Base.metadata.tables.values()}
    unknown_tables = sorted(source_tables - model_tables)
    if unknown_tables:
        raise RuntimeError(f"Database contains tables not represented by current models: {unknown_tables}")

    tables = []
    with engine.connect() as connection:
        for table in Base.metadata.sorted_tables:
            if table.name not in source_tables:
                continue
            path = table_dir / f"{table.name}.jsonl"
            count = 0
            with path.open("w", encoding="utf-8", newline="\n") as handle:
                query = select(table)
                order = _table_order(table)
                if order:
                    query = query.order_by(*order)
                for row in connection.execute(query).mappings():
                    handle.write(encode_row(dict(row)))
                    handle.write("\n")
                    count += 1
            tables.append(
                {
                    "name": table.name,
                    "row_count": count,
                    "sha256": sha256_file(path),
                    "columns": [column.name for column in table.columns],
                    "primary_key": [column.name for column in table.primary_key.columns],
                }
            )

    assets = []
    for relative in VERSION_FILES:
        source = ROOT / relative
        if not source.is_file():
            raise FileNotFoundError(f"Required version file is missing: {relative}")
        assets.append(_copy_asset(source, output, label="version_contract"))

    db = SessionLocal()
    try:
        active_models = db.query(ClassificationModel).filter_by(is_active=True).all()
        if len(active_models) != 1:
            raise RuntimeError(f"Expected exactly one active model, found {len(active_models)}")
        active = active_models[0]
        artifact = Path(active.artifact_path).resolve()
        if not artifact.is_file() or ROOT not in artifact.parents:
            raise RuntimeError("Active model artifact is missing or outside the workspace")
        assets.append(_copy_asset(artifact, output, label="active_model_artifact"))
        evaluation = artifact.with_name("evaluation.json")
        if evaluation.is_file():
            assets.append(_copy_asset(evaluation, output, label="active_model_evaluation"))
        active_model = {
            "model_id": active.model_id,
            "model_key": active.model_key,
            "model_version": active.model_version,
            "taxonomy_version": active.taxonomy_version,
            "artifact_path": artifact.relative_to(ROOT).as_posix(),
            "artifact_sha256": sha256_file(artifact),
        }
    finally:
        db.close()

    env_keys = []
    for raw in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            env_keys.append(line.split("=", 1)[0].strip())

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "privacy": "private backup; database rows may contain password hashes and user content",
        "source_database": {
            "dialect": engine.url.get_backend_name(),
            "database": engine.url.database,
            "url_not_recorded": True,
        },
        "database_tables": tables,
        "database_row_total": sum(item["row_count"] for item in tables),
        "active_model": active_model,
        "assets": assets,
        "environment": {
            "private_env_present": (ROOT / ".env").is_file(),
            "private_env_included": False,
            "required_key_names": env_keys,
        },
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "manifest.sha256").write_text(f"{sha256_file(manifest_path)}  manifest.json\n", encoding="ascii")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = create_backup(args.output.resolve())
    print(json.dumps({
        "output": str(args.output.resolve()),
        "tables": len(result["database_tables"]),
        "rows": result["database_row_total"],
        "assets": len(result["assets"]),
        "private_env_included": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
