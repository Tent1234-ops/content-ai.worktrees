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
    migrate_classification_split_strategy,
    migrate_phase13_taxonomy_schema,
    migrate_view_metric_schema,
    migrate_youtube_cc_dataset_schema,
)
from app.services.classification_training import (
    DEFAULT_GROUPED_CV_FOLDS,
    DEFAULT_MULTILINGUAL_EMBEDDING_MODEL,
    MODEL_PROMOTION_THRESHOLD,
    UNKNOWN_CONFIDENCE_THRESHOLD,
    ClassificationTrainingError,
    train_and_evaluate_classification_models,
)
from app.services.taxonomy import MIN_VERIFIED_SAMPLES, sync_taxonomy_registry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare channel-grouped public YouTube splits and benchmark multiple "
            "taxonomy classifiers. Evaluated models are never activated automatically."
        )
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=ROOT / "artifacts" / "classification_training",
        help="Directory for immutable split manifests, model files and reports",
    )
    parser.add_argument(
        "--model-version",
        help="Unique model version; defaults to the current UTC timestamp",
    )
    parser.add_argument(
        "--leaves",
        help="Optional comma-separated taxonomy leaves; defaults to all active leaves",
    )
    parser.add_argument(
        "--minimum-samples-per-leaf",
        type=int,
        default=MIN_VERIFIED_SAMPLES,
        help=f"Readiness gate per leaf (default: {MIN_VERIFIED_SAMPLES})",
    )
    parser.add_argument(
        "--unknown-threshold",
        type=float,
        default=UNKNOWN_CONFIDENCE_THRESHOLD,
        help=(
            "Return Unknown/Other when the highest class probability is below this "
            f"value (default: {UNKNOWN_CONFIDENCE_THRESHOLD})"
        ),
    )
    parser.add_argument(
        "--promotion-threshold",
        type=float,
        default=MODEL_PROMOTION_THRESHOLD,
        help=(
            "Required grouped-CV/test accuracy, Macro F1, and minimum per-class "
            "recall; does not activate the model automatically "
            f"(default: {MODEL_PROMOTION_THRESHOLD})"
        ),
    )
    parser.add_argument(
        "--grouped-cv-folds",
        type=int,
        default=DEFAULT_GROUPED_CV_FOLDS,
        help=(
            "Requested Stratified Group K-fold count; automatically reduced when "
            f"a class has fewer channels (default: {DEFAULT_GROUPED_CV_FOLDS})"
        ),
    )
    parser.add_argument(
        "--embedding-model",
        default=DEFAULT_MULTILINGUAL_EMBEDDING_MODEL,
        help="Sentence Transformers model name or local directory",
    )
    parser.add_argument(
        "--embedding-cache-folder",
        type=Path,
        default=ROOT / "models_cache" / "sentence_transformers",
        help="Local cache used by the multilingual embedding benchmark",
    )
    parser.add_argument(
        "--allow-embedding-download",
        action="store_true",
        help=(
            "Allow downloading the embedding model. Without this flag an uncached "
            "embedding benchmark is reported as skipped instead of using network."
        ),
    )
    parser.add_argument(
        "--no-phase22-gate",
        action="store_true",
        help=(
            "Benchmark without the larger Phase 22 collection targets. The "
            "validation-selected scope policy and independent Unknown test gate "
            "are still required; this option cannot bypass them."
        ),
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Write and validate split artifacts without fitting models",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help=(
            "Fit/evaluate with the incomplete real dataset only to verify the "
            "pipeline; models are marked smoke_test_only and can never qualify"
        ),
    )
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Exit 1 when the real reviewed dataset is not ready for training",
    )
    parser.add_argument(
        "--require-phase22-ready",
        action="store_true",
        help="Exit 1 unless all Phase 22 collection targets meet their minimums",
    )
    args = parser.parse_args()
    if args.smoke_test and args.prepare_only:
        parser.error("--smoke-test cannot be combined with --prepare-only")
    if args.smoke_test and args.require_ready:
        parser.error("--smoke-test cannot be combined with --require-ready")
    return args


def main() -> int:
    args = parse_args()
    leaves = (
        tuple(
            item.strip()
            for item in str(args.leaves or "").split(",")
            if item.strip()
        )
        or None
    )
    Base.metadata.create_all(bind=engine)
    migrate_phase13_taxonomy_schema(engine)
    migrate_youtube_cc_dataset_schema(engine)
    migrate_view_metric_schema(engine)
    migrate_classification_split_strategy(engine)
    db = SessionLocal()
    try:
        sync_taxonomy_registry(db)
        result = train_and_evaluate_classification_models(
            db,
            artifact_root=args.artifact_root,
            model_version=args.model_version,
            required_leaf_keys=leaves,
            minimum_samples_per_leaf=args.minimum_samples_per_leaf,
            unknown_threshold=args.unknown_threshold,
            promotion_threshold=args.promotion_threshold,
            prepare_only=args.prepare_only,
            smoke_test=args.smoke_test,
            grouped_cv_folds=args.grouped_cv_folds,
            embedding_model=args.embedding_model,
            embedding_cache_folder=args.embedding_cache_folder,
            allow_embedding_download=args.allow_embedding_download,
            enforce_phase22_gate=not args.no_phase22_gate,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.require_ready and not bool(result["dataset"]["ready"]):
            return 1
        if args.require_phase22_ready and not bool(
            result["dataset"]["phase22_ready"]
        ):
            return 1
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ClassificationTrainingError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
