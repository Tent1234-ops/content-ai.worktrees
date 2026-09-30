from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from app.database.db import SessionLocal
from app.database.models import (
    AnalysisResult,
    ClusterMembership,
    DatasetContent,
    SystemLog,
)
from app.services.dataset_eligibility import production_transcript_query
from app.services.taxonomy import taxonomy_coverage


DEMO_SOURCE_PLATFORM = "youtube_seed"


def _demo_ids(db) -> list[int]:
    return [
        int(row[0])
        for row in (
            db.query(DatasetContent.dataset_id)
            .filter(DatasetContent.source_platform == DEMO_SOURCE_PLATFORM)
            .all()
        )
    ]


def submission_report(db) -> dict[str, Any]:
    demo_ids = _demo_ids(db)
    analysis_references = 0
    cluster_references = 0
    if demo_ids:
        analysis_references = (
            db.query(AnalysisResult)
            .filter(AnalysisResult.dataset_id.in_(demo_ids))
            .count()
        )
        cluster_references = (
            db.query(ClusterMembership)
            .filter(ClusterMembership.dataset_id.in_(demo_ids))
            .count()
        )

    coverage = taxonomy_coverage(db)
    production_rows = production_transcript_query(db).count()
    ready = bool(coverage["ready"]) and production_rows > 0 and not demo_ids
    return {
        "status": "ready" if ready else "not_ready",
        "ready_for_submission": ready,
        "production_transcript_rows": production_rows,
        "taxonomy_ready_leaves": coverage["ready_leaf_count"],
        "taxonomy_leaf_count": coverage["leaf_count"],
        "taxonomy": coverage["leaves"],
        "demo_rows": len(demo_ids),
        "demo_analysis_references": analysis_references,
        "demo_cluster_references": cluster_references,
    }


def purge_demo_rows(db) -> int:
    report = submission_report(db)
    reference_count = int(report["demo_analysis_references"]) + int(
        report["demo_cluster_references"]
    )
    if reference_count:
        raise RuntimeError(
            "Refusing to delete legacy demo rows because analysis or cluster rows "
            f"still reference them ({reference_count} references)."
        )

    deleted = (
        db.query(DatasetContent)
        .filter(DatasetContent.source_platform == DEMO_SOURCE_PLATFORM)
        .delete(synchronize_session=False)
    )
    db.add(
        SystemLog(
            action="purge_legacy_demo_dataset",
            status="success",
            detail=json.dumps(
                {"deleted_rows": int(deleted or 0)},
                ensure_ascii=False,
            ),
        )
    )
    db.commit()
    return int(deleted or 0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Report whether the database contains a complete, real transcript "
            "dataset and no legacy demo rows."
        )
    )
    parser.add_argument(
        "--purge-demo",
        action="store_true",
        help="Delete youtube_seed rows after refusing any referenced rows",
    )
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Exit with status 1 unless all taxonomy leaves are ready and demo rows are zero",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db = SessionLocal()
    try:
        deleted = purge_demo_rows(db) if args.purge_demo else 0
        report = submission_report(db)
        if args.purge_demo:
            report["demo_rows_deleted"] = deleted
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if args.require_ready and not report["ready_for_submission"]:
            return 1
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
