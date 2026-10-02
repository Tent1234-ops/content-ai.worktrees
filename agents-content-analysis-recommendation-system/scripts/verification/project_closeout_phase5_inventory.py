"""Capture a read-only, reproducible inventory for Closeout Phase 5.

The command never trains, activates, imports, approves, fetches providers, or
changes application rows. The output directory must not already contain the
inventory file so an older acceptance run cannot be silently overwritten.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import sys

from sqlalchemy import func


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.database.db import SessionLocal
from app.database.models import (
    ClassificationModel,
    DatasetContent,
    DatasetReviewEvent,
    ModelEvaluationMetric,
    ReferenceVideoStatistic,
    SystemConfig,
    TrendSnapshotItem,
    TrendSnapshotRun,
)
from app.services.analysis_settings import get_analysis_settings
from app.services.classification_readiness import classification_model_snapshot
from app.services.youtube_cc_dataset import list_youtube_cc_review_queue


SOURCE_ROOTS = ("app", "models", "scripts", "frontend_flutter/lib", "frontend_flutter/test")
SOURCE_SUFFIXES = {".py", ".dart", ".cjs", ".js"}
PACKAGE_NAMES = (
    "fastapi",
    "sqlalchemy",
    "scikit-learn",
    "pythainlp",
    "faster-whisper",
    "numpy",
)


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_identity(relative_root: str) -> dict:
    base = ROOT / relative_root
    rows = []
    if base.exists():
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.suffix.lower() in SOURCE_SUFFIXES and "__pycache__" not in path.parts:
                rows.append((path.relative_to(ROOT).as_posix(), sha256(path)))
    payload = "\n".join(f"{name}\t{digest}" for name, digest in rows).encode("utf-8")
    return {
        "root": relative_root,
        "file_count": len(rows),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def database_identity(db) -> dict:
    dataset_rows = db.query(
        DatasetContent.dataset_id,
        DatasetContent.transcript_sha256,
        DatasetContent.taxonomy_leaf_key,
        DatasetContent.data_split,
        DatasetContent.is_active,
        DatasetContent.is_training_eligible,
        DatasetContent.is_keyword_recommendation_eligible,
        DatasetContent.is_duration_recommendation_eligible,
        DatasetContent.deleted_at,
    ).order_by(DatasetContent.dataset_id).all()
    payload = json.dumps([tuple(str(value) for value in row) for row in dataset_rows]).encode("utf-8")
    return {
        "dataset_rows": len(dataset_rows),
        "dataset_identity_sha256": hashlib.sha256(payload).hexdigest(),
        "active_model_ids": [
            row.model_id
            for row in db.query(ClassificationModel).filter_by(is_active=True).order_by(ClassificationModel.model_id)
        ],
        "system_config_ids": [row.config_id for row in db.query(SystemConfig).order_by(SystemConfig.config_id)],
        "pending_review_events": db.query(DatasetReviewEvent).filter_by(decision="pending").count(),
        "pending_review_candidates": list_youtube_cc_review_queue(
            db, limit=1, review_status="pending"
        )["total"],
    }


def dataset_inventory(db) -> dict:
    rows = db.query(DatasetContent).all()
    active = [row for row in rows if row.is_active and row.deleted_at is None]
    role_counts = {
        "training": sum(bool(row.is_training_eligible) for row in active),
        "keyword_reference": sum(bool(row.is_keyword_recommendation_eligible) for row in active),
        "duration_reference": sum(bool(row.is_duration_recommendation_eligible) for row in active),
        "holdout": sum(row.data_split in {"validation", "test", "out_of_scope"} for row in active),
    }
    split_leaf = Counter(
        (row.taxonomy_leaf_key or "unknown", row.data_split or "unassigned")
        for row in active
        if row.is_training_eligible or row.data_split in {"validation", "test", "out_of_scope"}
    )
    reference_versions = Counter(
        (row.dataset_source, row.dataset_version)
        for row in active
        if row.is_keyword_recommendation_eligible or row.is_duration_recommendation_eligible
    )
    return {
        "total": len(rows),
        "active": len(active),
        "roles": role_counts,
        "classification_by_leaf_and_split": [
            {"leaf": leaf, "split": split, "count": count}
            for (leaf, split), count in sorted(split_leaf.items())
        ],
        "reference_versions": [
            {"dataset_source": source, "dataset_version": version, "count": count}
            for (source, version), count in sorted(reference_versions.items())
        ],
    }


def model_inventory(db) -> dict:
    active = db.query(ClassificationModel).filter_by(is_active=True).one_or_none()
    snapshot = classification_model_snapshot(active)
    if active and active.artifact_path:
        try:
            snapshot["artifact_path"] = str(Path(active.artifact_path).resolve().relative_to(ROOT)).replace("\\", "/")
        except ValueError:
            snapshot["artifact_path"] = "outside_workspace"
    metrics = []
    if active:
        for row in db.query(ModelEvaluationMetric).filter_by(model_id=active.model_id).order_by(
            ModelEvaluationMetric.dataset_split,
            ModelEvaluationMetric.taxonomy_leaf_key,
            ModelEvaluationMetric.metric_name,
        ):
            metrics.append({
                "split": row.dataset_split,
                "leaf": row.taxonomy_leaf_key,
                "metric": row.metric_name,
                "value": row.metric_value,
                "sample_size": row.sample_size,
            })
    return {"active": snapshot, "metrics": metrics}


def latest_trends(db) -> list[dict]:
    rows = db.query(
        TrendSnapshotItem.platform,
        func.max(TrendSnapshotItem.created_at),
        func.count(TrendSnapshotItem.item_id),
    ).group_by(TrendSnapshotItem.platform).all()
    return [
        {"platform": platform_name, "latest_completed_at": completed_at, "stored_item_rows": count}
        for platform_name, completed_at, count in rows
    ]


def utility_status() -> dict:
    path = ROOT / "artifacts/evaluation/recommendation-utility-pending-20260930/preflight-final-v2/readiness.json"
    if not path.is_file():
        return {"status": "not_available", "path": str(path.relative_to(ROOT)).replace("\\", "/")}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "status": payload.get("state"),
        "manifest_complete": payload.get("manifest_complete"),
        "reviewer_plan_complete": payload.get("reviewer_plan_complete"),
        "missing": payload.get("missing", []),
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "sha256": sha256(path),
    }


def package_versions() -> dict:
    versions = {}
    for name in PACKAGE_NAMES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise SystemExit(f"Refusing to overwrite acceptance artifact: {output}")

    with SessionLocal() as db:
        before = database_identity(db)
        reference_cutoff = db.query(func.max(ReferenceVideoStatistic.observed_at)).scalar()
        report = {
            "schema_version": "project-closeout-phase5-inventory-v1",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "mode": "read_only",
            "runtime": {
                "python": sys.version,
                "platform": platform.platform(),
                "packages": package_versions(),
            },
            "release": {
                "source_trees": [tree_identity(root) for root in SOURCE_ROOTS],
                "requirements_sha256": sha256(ROOT / "requirements.txt"),
                "pubspec_lock_sha256": sha256(ROOT / "frontend_flutter/pubspec.lock"),
                "web_index_sha256": sha256(ROOT / "frontend_flutter/build/web/index.html"),
                "web_main_sha256": sha256(ROOT / "frontend_flutter/build/web/main.dart.js"),
                "git_status": "unavailable_broken_worktree_metadata",
            },
            "analysis_settings": get_analysis_settings(db, admin=True),
            "classification": model_inventory(db),
            "dataset": dataset_inventory(db),
            "reference_statistics_cutoff": reference_cutoff,
            "latest_trends": latest_trends(db),
            "utility_evaluation": utility_status(),
            "database_before": before,
        }
        db.rollback()
        report["database_after"] = database_identity(db)
        report["database_unchanged"] = report["database_before"] == report["database_after"]

    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "database_unchanged": report["database_unchanged"],
        "active_model": report["classification"]["active"].get("model_id"),
        "model_readiness": report["classification"]["active"].get("readiness", {}).get("status"),
        "utility_status": report["utility_evaluation"].get("status"),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
