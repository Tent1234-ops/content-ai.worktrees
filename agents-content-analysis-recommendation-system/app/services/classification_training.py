from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Sequence

import joblib
import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.naive_bayes import ComplementNB
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC
from sqlalchemy.orm import Session

from app.database.models import (
    ClassificationModel,
    DatasetContent,
    ModelEvaluationMetric,
    SystemLog,
)
from app.services.dataset_contract import (
    PRODUCTION_SPLITS,
    SPLIT_STRATEGY,
    YOUTUBE_PUBLIC_DATASET_SOURCE,
    channel_dataset_split,
)
from app.services.dataset_eligibility import (
    out_of_scope_evaluation_query,
    production_transcript_query,
)
from app.services.classification_acceptance import (
    POLICY_VERSION,
    MIN_UNKNOWN_TEST, MIN_UNKNOWN_CHANNELS, acceptance_summary,
    apply_acceptance_policy, evaluate_acceptance_policy, fit_acceptance_policy,
    partition_conflicts, is_validated_acceptance_policy,
)
from app.services.taxonomy import (
    ACTIVE_LEAF_KEYS,
    MIN_VERIFIED_SAMPLES,
    TAXONOMY_VERSION,
    UNKNOWN_LEAF_KEY,
)


MODEL_FAMILY = "taxonomy-text-classifier"
MODEL_PROMOTION_THRESHOLD = 0.80
UNKNOWN_CONFIDENCE_THRESHOLD = 0.60
RANDOM_STATE = 42
OVERALL_LEAF_KEY = "__overall__"
OVERALL_LANGUAGE = "all"
PHASE22_MINIMUM_SAMPLES_PER_LEAF = 80
PHASE22_TARGET_SAMPLES_PER_LEAF = 100
PHASE22_MINIMUM_UNIQUE_CHANNELS_PER_LEAF = 10
PHASE22_MINIMUM_OUT_OF_SCOPE_SAMPLES = 30
PHASE22_TARGET_OUT_OF_SCOPE_SAMPLES = 50
DEFAULT_GROUPED_CV_FOLDS = 5
DEFAULT_MULTILINGUAL_EMBEDDING_MODEL = (
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)


class ClassificationTrainingError(RuntimeError):
    pass


@dataclass(frozen=True)
class TrainingExample:
    dataset_id: int
    source_record_id: str
    source_youtube_id: str
    source_channel_id: str
    creator_group_key: str
    dataset_version: str
    split: str
    language: str
    leaf_key: str
    title: str
    transcript: str
    transcript_sha256: str

    @property
    def model_text(self) -> str:
        return self.transcript.strip()

    def artifact_record(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "source_record_id": self.source_record_id,
            "source_youtube_id": self.source_youtube_id,
            "source_channel_id": self.source_channel_id,
            "creator_group_key": self.creator_group_key,
            "dataset_version": self.dataset_version,
            "data_split": self.split,
            "language": self.language,
            "taxonomy_leaf_key": self.leaf_key,
            "title": self.title,
            "transcript": self.transcript,
            "transcript_sha256": self.transcript_sha256,
        }


@dataclass(frozen=True)
class PreparedClassificationDataset:
    examples: tuple[TrainingExample, ...]
    out_of_scope_examples: tuple[TrainingExample, ...]
    report: dict[str, Any]
    artifact_dir: Path | None


@dataclass(frozen=True)
class ClassificationModelSpec:
    model_key: str
    model_type: str
    description: str
    factory: Callable[[], Any]
    availability: Callable[[], tuple[bool, str | None]] | None = None
    tuning_factories: tuple[
        tuple[dict[str, float | int | str], Callable[[], Any]], ...
    ] = ()
    scope_policy_version: str = POLICY_VERSION


@lru_cache(maxsize=4)
def _load_sentence_transformer_cached(
    model_name_or_path: str,
    cache_folder: str | None,
    local_files_only: bool,
):
    from sentence_transformers import SentenceTransformer

    resolved_model_path = _resolve_sentence_transformer_model_path(
        model_name_or_path,
        cache_folder=cache_folder,
        local_files_only=local_files_only,
    )
    return SentenceTransformer(
        resolved_model_path,
        cache_folder=cache_folder,
        # Loading by the resolved snapshot path prevents Transformers from making
        # an incidental Hub metadata request while an offline benchmark is running.
        local_files_only=True,
    )


def _resolve_sentence_transformer_model_path(
    model_name_or_path: str,
    *,
    cache_folder: str | None,
    local_files_only: bool,
) -> str:
    local_path = Path(model_name_or_path).expanduser()
    if local_path.is_dir():
        return str(local_path.resolve())

    from huggingface_hub import snapshot_download

    return str(
        Path(
            snapshot_download(
                repo_id=model_name_or_path,
                cache_dir=cache_folder,
                local_files_only=local_files_only,
            )
        ).resolve()
    )


class SentenceEmbeddingTransformer(BaseEstimator, TransformerMixin):
    """Lazy, pickle-safe SentenceTransformer adapter for sklearn pipelines."""

    def __init__(
        self,
        model_name_or_path: str,
        *,
        cache_folder: str | None = None,
        local_files_only: bool = True,
        batch_size: int = 16,
        chunk_characters: int = 1_200,
        chunk_overlap_characters: int = 200,
        max_chunks_per_document: int = 12,
    ):
        self.model_name_or_path = model_name_or_path
        self.cache_folder = cache_folder
        self.local_files_only = local_files_only
        self.batch_size = batch_size
        self.chunk_characters = chunk_characters
        self.chunk_overlap_characters = chunk_overlap_characters
        self.max_chunks_per_document = max_chunks_per_document
        self._model = None

    def fit(self, texts, labels=None):
        del texts, labels
        return self

    def _load_model(self):
        if self._model is None:
            self._model = _load_sentence_transformer_cached(
                self.model_name_or_path,
                self.cache_folder,
                self.local_files_only,
            )
        return self._model

    def transform(self, texts):
        values = [str(text or "") for text in texts]
        chunks: list[str] = []
        document_indexes: list[int] = []
        step = max(1, self.chunk_characters - self.chunk_overlap_characters)
        for document_index, value in enumerate(values):
            starts = list(range(0, max(1, len(value)), step))
            if len(starts) > self.max_chunks_per_document:
                selected_indexes = np.linspace(
                    0,
                    len(starts) - 1,
                    num=self.max_chunks_per_document,
                    dtype=int,
                )
                starts = [starts[index] for index in sorted(set(selected_indexes))]
            for start in starts:
                chunks.append(value[start : start + self.chunk_characters] or " ")
                document_indexes.append(document_index)
        encoded = np.asarray(
            self._load_model().encode(
                chunks,
                batch_size=self.batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            ),
            dtype=float,
        )
        document_embeddings = []
        for document_index in range(len(values)):
            indexes = [
                index
                for index, value in enumerate(document_indexes)
                if value == document_index
            ]
            pooled = encoded[indexes].mean(axis=0)
            norm = float(np.linalg.norm(pooled))
            document_embeddings.append(pooled / norm if norm > 0 else pooled)
        return np.asarray(
            document_embeddings,
            dtype=float,
        )

    def __getstate__(self):
        state = dict(self.__dict__)
        state["_model"] = None
        return state


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_version(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-.")
    if not normalized:
        raise ClassificationTrainingError("model_version cannot be empty")
    return normalized[:100]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def _write_jsonl(path: Path, rows: Sequence[TrainingExample]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(
                json.dumps(row.artifact_record(), ensure_ascii=False, sort_keys=True)
                + "\n"
            )
    temporary.replace(path)


def _write_joblib(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    joblib.dump(payload, temporary)
    temporary.replace(path)


def _dataset_fingerprint(examples: Sequence[TrainingExample]) -> str:
    canonical_rows = [
        {
            "dataset_id": item.dataset_id,
            "source_record_id": item.source_record_id,
            "creator_group_key": item.creator_group_key,
            "dataset_version": item.dataset_version,
            "split": item.split,
            "language": item.language,
            "leaf_key": item.leaf_key,
            "transcript_sha256": item.transcript_sha256,
        }
        for item in sorted(examples, key=lambda value: value.dataset_id)
    ]
    return _sha256_text(
        json.dumps(canonical_rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def _dataset_row_to_example(row: DatasetContent) -> TrainingExample:
    return TrainingExample(
        dataset_id=int(row.dataset_id),
        source_record_id=str(row.source_record_id or ""),
        source_youtube_id=str(row.source_youtube_id or ""),
        source_channel_id=str(row.source_channel_id or ""),
        creator_group_key=str(row.creator_group_key or ""),
        dataset_version=str(row.dataset_version or ""),
        split=str(row.data_split or ""),
        language=str(row.language or "und"),
        leaf_key=str(row.taxonomy_leaf_key or ""),
        title=str(row.title or ""),
        transcript=str(row.transcript or ""),
        transcript_sha256=str(row.transcript_sha256 or ""),
    )


def _load_training_examples(
    db: Session,
    *,
    required_leaf_keys: Sequence[str],
) -> list[TrainingExample]:
    rows = (
        production_transcript_query(db)
        .filter(DatasetContent.taxonomy_leaf_key.in_(tuple(required_leaf_keys)))
        .order_by(DatasetContent.dataset_id.asc())
        .all()
    )
    return [_dataset_row_to_example(row) for row in rows]


def _load_out_of_scope_examples(db: Session) -> list[TrainingExample]:
    rows = out_of_scope_evaluation_query(db).order_by(
        DatasetContent.dataset_id.asc()
    ).all()
    return [_dataset_row_to_example(row) for row in rows]


def _phase22_collection_readiness(
    examples: Sequence[TrainingExample],
    out_of_scope_examples: Sequence[TrainingExample],
    *,
    required_leaf_keys: Sequence[str],
) -> dict[str, Any]:
    by_leaf = []
    issues: list[str] = []
    for leaf_key in required_leaf_keys:
        rows = [item for item in examples if item.leaf_key == leaf_key]
        sample_count = len(rows)
        channel_count = len({item.creator_group_key for item in rows})
        leaf_issues = []
        if sample_count < PHASE22_MINIMUM_SAMPLES_PER_LEAF:
            leaf_issues.append(
                f"needs {PHASE22_MINIMUM_SAMPLES_PER_LEAF - sample_count} more "
                "reviewed samples to reach the Phase 22 minimum"
            )
        if channel_count < PHASE22_MINIMUM_UNIQUE_CHANNELS_PER_LEAF:
            leaf_issues.append(
                f"needs {PHASE22_MINIMUM_UNIQUE_CHANNELS_PER_LEAF - channel_count} "
                "more unique channels"
            )
        if leaf_issues:
            issues.append(f"{leaf_key}: " + "; ".join(leaf_issues))
        by_leaf.append(
            {
                "leaf_key": leaf_key,
                "sample_count": sample_count,
                "minimum_sample_count": PHASE22_MINIMUM_SAMPLES_PER_LEAF,
                "target_sample_count": PHASE22_TARGET_SAMPLES_PER_LEAF,
                "remaining_to_minimum": max(
                    0, PHASE22_MINIMUM_SAMPLES_PER_LEAF - sample_count
                ),
                "remaining_to_target": max(
                    0, PHASE22_TARGET_SAMPLES_PER_LEAF - sample_count
                ),
                "unique_channels": channel_count,
                "minimum_unique_channels": (
                    PHASE22_MINIMUM_UNIQUE_CHANNELS_PER_LEAF
                ),
                "ready": not leaf_issues,
            }
        )

    unknown_count = len(out_of_scope_examples)
    unknown_channels = len(
        {item.creator_group_key for item in out_of_scope_examples}
    )
    if unknown_count < PHASE22_MINIMUM_OUT_OF_SCOPE_SAMPLES:
        issues.append(
            "unknown: needs "
            f"{PHASE22_MINIMUM_OUT_OF_SCOPE_SAMPLES - unknown_count} more "
            "human-reviewed out-of-scope evaluation samples"
        )
    return {
        "ready": not issues,
        "issues": issues,
        "minimum_samples_per_leaf": PHASE22_MINIMUM_SAMPLES_PER_LEAF,
        "target_samples_per_leaf": PHASE22_TARGET_SAMPLES_PER_LEAF,
        "minimum_unique_channels_per_leaf": (
            PHASE22_MINIMUM_UNIQUE_CHANNELS_PER_LEAF
        ),
        "by_leaf": by_leaf,
        "out_of_scope": {
            "sample_count": unknown_count,
            "minimum_sample_count": PHASE22_MINIMUM_OUT_OF_SCOPE_SAMPLES,
            "target_sample_count": PHASE22_TARGET_OUT_OF_SCOPE_SAMPLES,
            "remaining_to_minimum": max(
                0, PHASE22_MINIMUM_OUT_OF_SCOPE_SAMPLES - unknown_count
            ),
            "remaining_to_target": max(
                0, PHASE22_TARGET_OUT_OF_SCOPE_SAMPLES - unknown_count
            ),
            "unique_channels": unknown_channels,
            "usage": "evaluation_only_not_fitted",
            "ready": unknown_count >= PHASE22_MINIMUM_OUT_OF_SCOPE_SAMPLES,
        },
        "hard_case_collection_priorities": [
            {
                "true_leaf": "phone",
                "confusable_with": "camera",
                "example_scope": "phone camera reviews",
            },
            {
                "true_leaf": "camera",
                "confusable_with": "phone",
                "example_scope": "dedicated camera versus phone camera language",
            },
            {
                "true_leaf": "laptop",
                "confusable_with": "phone",
                "example_scope": "gaming laptop versus phone gaming language",
            },
            {
                "true_leaf": UNKNOWN_LEAF_KEY,
                "confusable_with": "phone",
                "example_scope": "phone accessories that are not phone reviews",
            },
        ],
    }


def _dataset_readiness(
    examples: Sequence[TrainingExample],
    *,
    required_leaf_keys: Sequence[str],
    minimum_samples_per_leaf: int,
    split_overrides=None,
) -> dict[str, Any]:
    split_counts: Counter[str] = Counter()
    language_counts: Counter[str] = Counter()
    channels_by_split: dict[str, set[str]] = defaultdict(set)
    channel_splits: dict[str, set[str]] = defaultdict(set)
    leaf_split_counts: dict[str, Counter[str]] = defaultdict(Counter)
    leaf_language_counts: dict[str, Counter[str]] = defaultdict(Counter)
    leaf_channels: dict[str, set[str]] = defaultdict(set)
    issues: list[str] = []

    for item in examples:
        split_counts[item.split] += 1
        language_counts[item.language] += 1
        channels_by_split[item.split].add(item.creator_group_key)
        channel_splits[item.creator_group_key].add(item.split)
        leaf_split_counts[item.leaf_key][item.split] += 1
        leaf_language_counts[item.leaf_key][item.language] += 1
        leaf_channels[item.leaf_key].add(item.creator_group_key)

        try:
            expected_split, expected_group = channel_dataset_split(
                item.source_channel_id, overrides=split_overrides
            )
        except ValueError as exc:
            issues.append(f"dataset_id={item.dataset_id}: {exc}")
            continue
        if item.split != expected_split:
            issues.append(
                f"dataset_id={item.dataset_id}: split={item.split} does not match "
                f"{SPLIT_STRATEGY} ({expected_split})"
            )
        if item.creator_group_key != expected_group:
            issues.append(
                f"dataset_id={item.dataset_id}: creator_group_key does not match channel"
            )

    leaked_channels = sorted(
        channel for channel, splits in channel_splits.items() if len(splits) > 1
    )
    if leaked_channels:
        issues.append(
            f"{len(leaked_channels)} channel group(s) leak across dataset splits"
        )

    by_leaf: list[dict[str, Any]] = []
    minimum_train_samples = max(2, math.ceil(minimum_samples_per_leaf * 0.50))
    minimum_evaluation_samples = max(
        1, math.ceil(minimum_samples_per_leaf * 0.10)
    )
    for leaf_key in required_leaf_keys:
        counts = leaf_split_counts[leaf_key]
        total = sum(counts.values())
        leaf_issues: list[str] = []
        if total < minimum_samples_per_leaf:
            leaf_issues.append(
                f"requires {minimum_samples_per_leaf - total} more verified sample(s)"
            )
        if counts["train"] < minimum_train_samples:
            leaf_issues.append(
                f"requires at least {minimum_train_samples} training samples"
            )
        if counts["validation"] < minimum_evaluation_samples:
            leaf_issues.append(
                "requires at least "
                f"{minimum_evaluation_samples} validation samples"
            )
        if counts["test"] < minimum_evaluation_samples:
            leaf_issues.append(
                f"requires at least {minimum_evaluation_samples} test samples"
            )
        if leaf_issues:
            issues.append(f"{leaf_key}: " + "; ".join(leaf_issues))
        by_leaf.append(
            {
                "leaf_key": leaf_key,
                "total": total,
                "minimum_required": minimum_samples_per_leaf,
                "minimum_split_counts": {
                    "train": minimum_train_samples,
                    "validation": minimum_evaluation_samples,
                    "test": minimum_evaluation_samples,
                },
                "split_counts": {
                    split: int(counts[split]) for split in PRODUCTION_SPLITS
                },
                "language_counts": dict(sorted(leaf_language_counts[leaf_key].items())),
                "unique_channels": len(leaf_channels[leaf_key]),
                "ready": not leaf_issues,
                "issues": leaf_issues,
            }
        )

    return {
        "ready": not issues,
        "issues": list(dict.fromkeys(issues)),
        "sample_count": len(examples),
        "split_counts": {
            split: int(split_counts[split]) for split in PRODUCTION_SPLITS
        },
        "language_counts": dict(sorted(language_counts.items())),
        "channel_counts": {
            split: len(channels_by_split[split]) for split in PRODUCTION_SPLITS
        },
        "unique_channels": len(channel_splits),
        "channel_leakage_count": len(leaked_channels),
        "leaked_creator_group_keys": leaked_channels,
        "by_leaf": by_leaf,
    }


def prepare_classification_dataset(
    db: Session,
    *,
    artifact_root: str | Path | None = None,
    required_leaf_keys: Sequence[str] | None = None,
    minimum_samples_per_leaf: int = MIN_VERIFIED_SAMPLES,
) -> PreparedClassificationDataset:
    leaves = tuple(dict.fromkeys(required_leaf_keys or ACTIVE_LEAF_KEYS))
    invalid_leaves = sorted(set(leaves) - set(ACTIVE_LEAF_KEYS))
    if invalid_leaves:
        raise ClassificationTrainingError(
            "Unknown or non-trainable taxonomy leaves: " + ", ".join(invalid_leaves)
        )
    if minimum_samples_per_leaf < 1:
        raise ClassificationTrainingError("minimum_samples_per_leaf must be positive")

    examples = _load_training_examples(db, required_leaf_keys=leaves)
    out_of_scope_examples = _load_out_of_scope_examples(db)
    from app.services.dataset_split_plan import load_split_registry
    registry = load_split_registry(db)
    fingerprint = _dataset_fingerprint([*examples, *out_of_scope_examples])
    readiness = _dataset_readiness(
        examples,
        required_leaf_keys=leaves,
        minimum_samples_per_leaf=minimum_samples_per_leaf,
        split_overrides=registry["overrides"],
    )
    invalid_assignments = []
    for row in [*examples, *out_of_scope_examples]:
        try:
            expected_split, expected_group = channel_dataset_split(row.source_channel_id, overrides=registry["overrides"])
            valid_assignment = row.split == expected_split and row.creator_group_key == expected_group
        except ValueError:
            valid_assignment = False
        if not valid_assignment:
            invalid_assignments.append(row.dataset_id)
            readiness["ready"] = False
            readiness["issues"].append(
                f"dataset_id={row.dataset_id}: split/group does not match its channel")
    selected_ids = {r.dataset_id for r in [*examples, *out_of_scope_examples]}
    # An archived or currently ineligible holdout still reserves its identity.
    reserved = [_dataset_row_to_example(row) for row in db.query(DatasetContent).filter(
        DatasetContent.data_split.in_(("validation", "test"))).all()
        if row.dataset_id not in selected_ids]
    conflicts = [row for row in partition_conflicts([*examples, *out_of_scope_examples, *reserved])
                 if selected_ids.intersection(row["dataset_ids"])]
    if conflicts:
        readiness["ready"] = False
        readiness["issues"].append("Identity overlap across train/validation/test (including Unknown)")
    readiness["partition_conflicts"] = conflicts
    readiness["invalid_partition_assignments"] = invalid_assignments
    readiness["partition_integrity_passed"] = not conflicts and not invalid_assignments
    phase22_readiness = _phase22_collection_readiness(
        examples,
        out_of_scope_examples,
        required_leaf_keys=leaves,
    )
    dataset_versions = sorted(
        {
            item.dataset_version
            for item in [*examples, *out_of_scope_examples]
        }
    )
    report: dict[str, Any] = {
        "status": "ready" if readiness["ready"] else "not_ready",
        "ready": bool(readiness["ready"]),
        "dataset_source": YOUTUBE_PUBLIC_DATASET_SOURCE,
        "dataset_versions": dataset_versions,
        "dataset_fingerprint": fingerprint,
        "taxonomy_version": TAXONOMY_VERSION,
        "required_leaf_keys": list(leaves),
        "minimum_samples_per_leaf": minimum_samples_per_leaf,
        "split_strategy": SPLIT_STRATEGY,
        "registered_holdout_plans": registry["plans"],
        "evaluation_dataset_note": (
            "Versioned channel repartition; not a fresh external test. Candidates fit from scratch."
            if registry["plans"] else "Original channel-hash partitions"
        ),
        "unknown_support": {
            "leaf_key": UNKNOWN_LEAF_KEY,
            "strategy": "validation_selected_confidence_and_train_similarity",
            "uses_synthetic_training_rows": False,
            "training_sample_count": 0,
            "evaluation_sample_count": len(out_of_scope_examples),
            "split_counts": dict(Counter(r.split for r in out_of_scope_examples)),
            "channel_counts": {split: len({r.source_channel_id for r in out_of_scope_examples
                                            if r.split == split and r.source_channel_id})
                               for split in PRODUCTION_SPLITS},
        },
        "phase22": phase22_readiness,
        "phase22_ready": bool(phase22_readiness["ready"]),
        **readiness,
        "artifacts": {},
    }

    artifact_dir: Path | None = None
    if artifact_root is not None:
        artifact_dir = Path(artifact_root) / f"dataset-{fingerprint[:16]}"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        split_artifacts: dict[str, dict[str, Any]] = {}
        for split in PRODUCTION_SPLITS:
            path = artifact_dir / f"{split}.jsonl"
            split_rows = [item for item in examples if item.split == split]
            _write_jsonl(path, split_rows)
            split_artifacts[split] = {
                "path": str(path.resolve()),
                "sha256": _sha256_file(path),
                "sample_count": len(split_rows),
            }
        out_of_scope_path = artifact_dir / "out_of_scope.jsonl"
        _write_jsonl(out_of_scope_path, out_of_scope_examples)
        report["artifacts"] = {
            "directory": str(artifact_dir.resolve()),
            "splits": split_artifacts,
            "out_of_scope": {
                "path": str(out_of_scope_path.resolve()),
                "sha256": _sha256_file(out_of_scope_path),
                "sample_count": len(out_of_scope_examples),
                "usage": "validation_calibrates_rejection_test_evaluates_train_reserved_not_fitted",
            },
        }
        manifest_path = artifact_dir / "dataset_manifest.json"
        report["artifacts"]["manifest_path"] = str(manifest_path.resolve())
        _write_json(manifest_path, report)
        report["artifacts"]["manifest_sha256"] = _sha256_file(manifest_path)

    return PreparedClassificationDataset(
        examples=tuple(examples),
        out_of_scope_examples=tuple(out_of_scope_examples),
        report=report,
        artifact_dir=artifact_dir,
    )


def _word_char_features() -> FeatureUnion:
    return FeatureUnion(
        [
            (
                "word",
                TfidfVectorizer(
                    analyzer="word",
                    ngram_range=(1, 2),
                    min_df=1,
                    max_features=40_000,
                    sublinear_tf=True,
                    strip_accents="unicode",
                ),
            ),
            (
                "char",
                TfidfVectorizer(
                    analyzer="char_wb",
                    ngram_range=(3, 5),
                    min_df=1,
                    max_features=40_000,
                    sublinear_tf=True,
                ),
            ),
        ]
    )


def _logistic_regression_pipeline(*, regularization_c: float) -> Pipeline:
    return Pipeline(
        [
            ("features", _word_char_features()),
            (
                "classifier",
                LogisticRegression(
                    C=regularization_c,
                    max_iter=4_000,
                    class_weight="balanced",
                    solver="lbfgs",
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )


def _embedding_model_availability(
    model_name_or_path: str,
    *,
    cache_folder: str | None,
    allow_download: bool,
) -> tuple[bool, str | None]:
    try:
        _resolve_sentence_transformer_model_path(
            model_name_or_path,
            cache_folder=cache_folder,
            local_files_only=not allow_download,
        )
    except Exception as exc:
        return (
            False,
            "multilingual embedding model is unavailable: "
            f"{exc}. Rerun with --allow-embedding-download when network "
            "download is intended",
        )
    return True, None


def default_classification_model_specs(
    *,
    embedding_model: str = DEFAULT_MULTILINGUAL_EMBEDDING_MODEL,
    embedding_cache_folder: str | Path | None = None,
    allow_embedding_download: bool = False,
) -> tuple[ClassificationModelSpec, ...]:
    cache_folder = (
        str(Path(embedding_cache_folder).resolve())
        if embedding_cache_folder is not None
        else None
    )
    return (
        ClassificationModelSpec(
            model_key="taxonomy-tfidf-complement-nb",
            model_type="tfidf_word_char_complement_nb",
            description="Word and character TF-IDF with Complement Naive Bayes",
            factory=lambda: Pipeline(
                [
                    ("features", _word_char_features()),
                    ("classifier", ComplementNB(alpha=0.5)),
                ]
            ),
        ),
        ClassificationModelSpec(
            model_key="taxonomy-tfidf-logreg-tuned",
            model_type="tfidf_word_char_tuned_logistic_regression",
            description=(
                "Word and character TF-IDF with tuned balanced logistic regression"
            ),
            factory=lambda: _logistic_regression_pipeline(
                regularization_c=4.0
            ),
            tuning_factories=tuple(
                (
                    {"C": regularization_c},
                    lambda regularization_c=regularization_c: (
                        _logistic_regression_pipeline(
                            regularization_c=regularization_c
                        )
                    ),
                )
                for regularization_c in (0.5, 1.0, 2.0, 4.0)
            ),
        ),
        ClassificationModelSpec(
            model_key="taxonomy-tfidf-linear-svm-calibrated",
            model_type="tfidf_word_char_calibrated_linear_svm",
            description="Word and character TF-IDF with calibrated balanced Linear SVM",
            factory=lambda: Pipeline(
                [
                    ("features", _word_char_features()),
                    (
                        "classifier",
                        CalibratedClassifierCV(
                            estimator=LinearSVC(
                                C=1.5,
                                class_weight="balanced",
                                dual="auto",
                                random_state=RANDOM_STATE,
                            ),
                            method="sigmoid",
                            cv=2,
                        ),
                    ),
                ]
            ),
        ),
        ClassificationModelSpec(
            model_key="taxonomy-multilingual-embeddings-logreg",
            model_type="multilingual_sentence_embeddings_logistic_regression",
            description=(
                "Multilingual sentence embeddings with balanced logistic regression"
            ),
            factory=lambda: Pipeline(
                [
                    (
                        "embeddings",
                        SentenceEmbeddingTransformer(
                            embedding_model,
                            cache_folder=cache_folder,
                            local_files_only=not allow_embedding_download,
                        ),
                    ),
                    (
                        "classifier",
                        LogisticRegression(
                            C=2.0,
                            max_iter=4_000,
                            class_weight="balanced",
                            random_state=RANDOM_STATE,
                        ),
                    ),
                ]
            ),
            availability=lambda: _embedding_model_availability(
                embedding_model,
                cache_folder=cache_folder,
                allow_download=allow_embedding_download,
            ),
        ),
    )


def predict_with_unknown(
    estimator: Any,
    texts: Sequence[str],
    *,
    unknown_threshold: float = UNKNOWN_CONFIDENCE_THRESHOLD,
) -> tuple[list[str], list[float]]:
    _raw_predictions, predictions, confidences = _prediction_details(
        estimator,
        texts,
        unknown_threshold=unknown_threshold,
    )
    return predictions, confidences


def _prediction_details(
    estimator: Any,
    texts: Sequence[str],
    *,
    unknown_threshold: float,
) -> tuple[list[str], list[str], list[float]]:
    if not 0.0 < unknown_threshold < 1.0:
        raise ClassificationTrainingError("unknown_threshold must be between 0 and 1")
    probabilities = np.asarray(estimator.predict_proba(list(texts)), dtype=float)
    classes = np.asarray(estimator.classes_, dtype=object)
    if probabilities.ndim != 2 or probabilities.shape[1] != len(classes):
        raise ClassificationTrainingError("classifier returned invalid probabilities")
    top_indexes = probabilities.argmax(axis=1)
    confidences = probabilities[np.arange(len(top_indexes)), top_indexes]
    raw_predictions = [str(classes[index]) for index in top_indexes]
    predictions = [
        raw_prediction if confidence >= unknown_threshold else UNKNOWN_LEAF_KEY
        for raw_prediction, confidence in zip(raw_predictions, confidences)
    ]
    return (
        raw_predictions,
        predictions,
        [round(float(value), 6) for value in confidences],
    )


def _evaluate_predictions(
    examples: Sequence[TrainingExample],
    predictions: Sequence[str],
    confidences: Sequence[float],
    *,
    labels: Sequence[str],
) -> dict[str, Any]:
    if len(examples) != len(predictions) or len(examples) != len(confidences):
        raise ClassificationTrainingError("prediction count does not match examples")
    if not examples:
        raise ClassificationTrainingError("cannot evaluate an empty dataset")
    y_true = [item.leaf_key for item in examples]
    y_pred = list(predictions)
    all_labels = list(labels)
    true_label_set = set(y_true)
    supported_labels = [label for label in all_labels if label in true_label_set]
    if not supported_labels:
        raise ClassificationTrainingError("evaluation has no supported taxonomy labels")
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=all_labels,
        average=None,
        zero_division=0,
    )
    precision_macro, recall_macro, f1_macro, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=supported_labels,
        average="macro",
        zero_division=0,
    )
    matrix_labels = list(dict.fromkeys([*all_labels, UNKNOWN_LEAF_KEY]))
    matrix = confusion_matrix(y_true, y_pred, labels=matrix_labels)
    per_class = {
        label: {
            "precision": round(float(precision[index]), 6),
            "recall": round(float(recall[index]), 6),
            "f1": round(float(f1[index]), 6),
            "support": int(support[index]),
        }
        for index, label in enumerate(all_labels)
    }
    unknown_count = sum(1 for value in y_pred if value == UNKNOWN_LEAF_KEY)
    return {
        "sample_size": len(examples),
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 6),
        "precision_macro": round(float(precision_macro), 6),
        "recall_macro": round(float(recall_macro), 6),
        "f1_macro": round(float(f1_macro), 6),
        "mean_confidence": round(float(np.mean(confidences)), 6),
        "unknown_prediction_count": unknown_count,
        "unknown_rate": round(unknown_count / len(examples), 6),
        "labels": matrix_labels,
        "metric_labels": supported_labels,
        "confusion_matrix": matrix.astype(int).tolist(),
        "per_class": per_class,
    }


def _evaluate_examples(
    estimator: Any,
    examples: Sequence[TrainingExample],
    *,
    labels: Sequence[str],
    unknown_threshold: float,
) -> dict[str, Any]:
    _raw_predictions, predictions, confidences = _prediction_details(
        estimator,
        [item.model_text for item in examples],
        unknown_threshold=unknown_threshold,
    )
    return _evaluate_predictions(
        examples,
        predictions,
        confidences,
        labels=labels,
    )


def _evaluation_by_language(
    estimator: Any,
    examples: Sequence[TrainingExample],
    *,
    labels: Sequence[str],
    unknown_threshold: float,
) -> dict[str, dict[str, Any]]:
    result = {
        OVERALL_LANGUAGE: _evaluate_examples(
            estimator,
            examples,
            labels=labels,
            unknown_threshold=unknown_threshold,
        )
    }
    for language in sorted({item.language for item in examples}):
        language_rows = [item for item in examples if item.language == language]
        result[language] = _evaluate_examples(
            estimator,
            language_rows,
            labels=labels,
            unknown_threshold=unknown_threshold,
        )
    return result


def _evaluation_by_language_from_predictions(
    examples: Sequence[TrainingExample],
    predictions: Sequence[str],
    confidences: Sequence[float],
    *,
    labels: Sequence[str],
) -> dict[str, dict[str, Any]]:
    result = {
        OVERALL_LANGUAGE: _evaluate_predictions(
            examples,
            predictions,
            confidences,
            labels=labels,
        )
    }
    for language in sorted({item.language for item in examples}):
        indexes = [
            index
            for index, item in enumerate(examples)
            if item.language == language
        ]
        result[language] = _evaluate_predictions(
            [examples[index] for index in indexes],
            [predictions[index] for index in indexes],
            [confidences[index] for index in indexes],
            labels=labels,
        )
    return result


def _grouped_cv_fold_count(
    examples: Sequence[TrainingExample],
    *,
    labels: Sequence[str],
    requested_folds: int,
) -> int:
    if requested_folds < 2:
        raise ClassificationTrainingError("grouped_cv_folds must be at least 2")
    groups_by_label = {
        label: {
            item.creator_group_key
            for item in examples
            if item.leaf_key == label
        }
        for label in labels
    }
    minimum_groups = min((len(groups) for groups in groups_by_label.values()), default=0)
    fold_count = min(requested_folds, minimum_groups)
    if fold_count < 2:
        details = ", ".join(
            f"{label}={len(groups)} channel(s)"
            for label, groups in groups_by_label.items()
        )
        raise ClassificationTrainingError(
            "grouped cross-validation needs at least two channels per class; " + details
        )
    return fold_count


def _hard_case_rows(
    examples: Sequence[TrainingExample],
    raw_predictions: Sequence[str],
    predictions: Sequence[str],
    confidences: Sequence[float],
) -> list[dict[str, Any]]:
    rows = []
    for item, raw_prediction, prediction, confidence in zip(
        examples,
        raw_predictions,
        predictions,
        confidences,
    ):
        if prediction == item.leaf_key:
            continue
        rows.append(
            {
                "dataset_id": item.dataset_id,
                "source_youtube_id": item.source_youtube_id,
                "channel_id": item.source_channel_id,
                "channel_group": item.creator_group_key,
                "title": item.title,
                "true_leaf_key": item.leaf_key,
                "raw_predicted_leaf_key": raw_prediction,
                "predicted_leaf_key": prediction,
                "confidence": round(float(confidence), 6),
                "error_type": (
                    "rejected_as_unknown"
                    if prediction == UNKNOWN_LEAF_KEY
                    else "misclassified"
                ),
            }
        )
    return sorted(rows, key=lambda item: (-item["confidence"], item["dataset_id"]))


def _grouped_cross_validation(
    spec: ClassificationModelSpec,
    examples: Sequence[TrainingExample],
    *,
    labels: Sequence[str],
    requested_folds: int,
    unknown_threshold: float,
) -> dict[str, Any]:
    fold_count = _grouped_cv_fold_count(
        examples,
        labels=labels,
        requested_folds=requested_folds,
    )
    y = np.asarray([item.leaf_key for item in examples], dtype=object)
    groups = np.asarray([item.creator_group_key for item in examples], dtype=object)
    splitter = StratifiedGroupKFold(
        n_splits=fold_count,
        shuffle=True,
        random_state=RANDOM_STATE,
    )
    raw_predictions = [""] * len(examples)
    predictions = [""] * len(examples)
    confidences = [0.0] * len(examples)
    fold_reports: list[dict[str, Any]] = []
    try:
        split_indexes = splitter.split(np.zeros(len(examples)), y, groups)
        for fold_number, (train_indexes, validation_indexes) in enumerate(
            split_indexes,
            start=1,
        ):
            train_groups = {str(groups[index]) for index in train_indexes}
            validation_groups = {str(groups[index]) for index in validation_indexes}
            overlap = sorted(train_groups & validation_groups)
            if overlap:
                raise ClassificationTrainingError(
                    f"grouped CV fold {fold_number} leaked {len(overlap)} channel(s)"
                )
            estimator = spec.factory()
            estimator.fit(
                [examples[index].model_text for index in train_indexes],
                [examples[index].leaf_key for index in train_indexes],
            )
            fold_raw, fold_predictions, fold_confidences = _prediction_details(
                estimator,
                [examples[index].model_text for index in validation_indexes],
                unknown_threshold=unknown_threshold,
            )
            for local_index, dataset_index in enumerate(validation_indexes):
                raw_predictions[dataset_index] = fold_raw[local_index]
                predictions[dataset_index] = fold_predictions[local_index]
                confidences[dataset_index] = fold_confidences[local_index]
            fold_reports.append(
                {
                    "fold": fold_number,
                    "train_sample_count": len(train_indexes),
                    "validation_sample_count": len(validation_indexes),
                    "train_channel_count": len(train_groups),
                    "validation_channel_count": len(validation_groups),
                    "channel_overlap_count": 0,
                    "train_label_counts": dict(
                        sorted(
                            Counter(str(y[index]) for index in train_indexes).items()
                        )
                    ),
                    "validation_label_counts": dict(
                        sorted(
                            Counter(
                                str(y[index]) for index in validation_indexes
                            ).items()
                        )
                    ),
                }
            )
    except ValueError as exc:
        raise ClassificationTrainingError(
            f"grouped cross-validation could not create valid folds: {exc}"
        ) from exc

    if any(not value for value in predictions):
        raise ClassificationTrainingError(
            "grouped cross-validation did not produce an out-of-fold prediction "
            "for every development row"
        )
    evaluations = _evaluation_by_language_from_predictions(
        examples,
        predictions,
        confidences,
        labels=labels,
    )
    hard_cases = _hard_case_rows(
        examples,
        raw_predictions,
        predictions,
        confidences,
    )
    confusion_pairs = Counter(
        f"{item.leaf_key}->{raw_prediction}"
        for item, raw_prediction in zip(examples, raw_predictions)
        if raw_prediction != item.leaf_key
    )
    return {
        "protocol": "stratified_group_k_fold_out_of_fold",
        "group_key": "source_channel_id_sha256",
        "requested_fold_count": requested_folds,
        "fold_count": fold_count,
        "development_sample_count": len(examples),
        "development_channel_count": len(set(groups)),
        "folds": fold_reports,
        "evaluations": evaluations,
        "hard_cases": hard_cases,
        "confusion_pairs": [
            {"pair": pair, "count": count}
            for pair, count in sorted(
                confusion_pairs.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ],
    }


def _evaluate_out_of_scope(
    estimator: Any,
    examples: Sequence[TrainingExample],
    *,
    unknown_threshold: float,
    scope_policy: dict | None = None,
) -> dict[str, Any]:
    if not examples:
        return {
            "sample_size": 0,
            "unknown_recall": None,
            "false_accept_rate": None,
            "accepted_as_in_scope_count": 0,
            "mean_confidence": None,
            "accepted_by_leaf": {},
            "false_accept_cases": [],
            "usage": "evaluation_only_not_fitted",
        }
    raw_predictions, predictions, confidences = _prediction_details(
        estimator,
        [item.model_text for item in examples],
        unknown_threshold=unknown_threshold,
    )
    if scope_policy is not None:
        predictions, _decisions = apply_acceptance_policy(
            scope_policy, [r.model_text for r in examples], raw_predictions, confidences)
    unknown_count = sum(
        1 for prediction in predictions if prediction == UNKNOWN_LEAF_KEY
    )
    accepted_by_leaf = Counter(
        prediction
        for prediction in predictions
        if prediction != UNKNOWN_LEAF_KEY
    )
    false_accept_cases = [
        {
            "dataset_id": item.dataset_id,
            "source_youtube_id": item.source_youtube_id,
            "channel_id": item.source_channel_id,
            "title": item.title,
            "raw_predicted_leaf_key": raw_prediction,
            "predicted_leaf_key": prediction,
            "confidence": round(float(confidence), 6),
        }
        for item, raw_prediction, prediction, confidence in zip(
            examples,
            raw_predictions,
            predictions,
            confidences,
        )
        if prediction != UNKNOWN_LEAF_KEY
    ]
    return {
        "sample_size": len(examples),
        "status": "evaluated" if scope_policy is None or is_validated_acceptance_policy(scope_policy) else "withheld_unvalidated_policy",
        "unknown_recall": round(unknown_count / len(examples), 6)
        if scope_policy is None or is_validated_acceptance_policy(scope_policy) else None,
        "false_accept_rate": round(
            (len(examples) - unknown_count) / len(examples),
            6,
        ) if scope_policy is None or is_validated_acceptance_policy(scope_policy) else None,
        "accepted_as_in_scope_count": len(examples) - unknown_count,
        "mean_confidence": round(float(np.mean(confidences)), 6),
        "accepted_by_leaf": dict(sorted(accepted_by_leaf.items())),
        "false_accept_cases": sorted(
            false_accept_cases,
            key=lambda item: (-item["confidence"], item["dataset_id"]),
        ),
        "usage": "evaluation_only_not_fitted",
    }


def _metric_rows(
    *,
    model_id: int,
    dataset_split: str,
    evaluations: dict[str, dict[str, Any]],
) -> list[ModelEvaluationMetric]:
    rows: list[ModelEvaluationMetric] = []
    scalar_names = (
        "accuracy",
        "precision_macro",
        "recall_macro",
        "f1_macro",
        "mean_confidence",
        "unknown_rate",
    )
    for language, result in evaluations.items():
        sample_size = int(result["sample_size"])
        for metric_name in scalar_names:
            rows.append(
                ModelEvaluationMetric(
                    model_id=model_id,
                    dataset_split=dataset_split,
                    language=language,
                    taxonomy_level=3,
                    taxonomy_leaf_key=OVERALL_LEAF_KEY,
                    metric_name=metric_name,
                    metric_value=float(result[metric_name]),
                    sample_size=sample_size,
                    details=None,
                )
            )
        rows.append(
            ModelEvaluationMetric(
                model_id=model_id,
                dataset_split=dataset_split,
                language=language,
                taxonomy_level=3,
                taxonomy_leaf_key=OVERALL_LEAF_KEY,
                metric_name="confusion_matrix",
                metric_value=float(result["accuracy"]),
                sample_size=sample_size,
                details=json.dumps(
                    {
                        "labels": result["labels"],
                        "matrix": result["confusion_matrix"],
                        "unknown_prediction_count": result[
                            "unknown_prediction_count"
                        ],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )
        )

    overall = evaluations[OVERALL_LANGUAGE]
    for leaf_key, metrics in overall["per_class"].items():
        for metric_name in ("precision", "recall", "f1"):
            rows.append(
                ModelEvaluationMetric(
                    model_id=model_id,
                    dataset_split=dataset_split,
                    language=OVERALL_LANGUAGE,
                    taxonomy_level=3,
                    taxonomy_leaf_key=leaf_key,
                    metric_name=metric_name,
                    metric_value=float(metrics[metric_name]),
                    sample_size=int(metrics["support"]),
                    details=None,
                )
            )
    return rows


def _out_of_scope_metric_rows(
    *,
    model_id: int,
    evaluation: dict[str, Any],
) -> list[ModelEvaluationMetric]:
    sample_size = int(evaluation["sample_size"])
    details = json.dumps(
        {
            "usage": evaluation["usage"],
            "accepted_by_leaf": evaluation["accepted_by_leaf"],
            "false_accept_cases": evaluation["false_accept_cases"],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    values: dict[str, float] = {
        "sample_count": float(sample_size),
        "accepted_as_in_scope_count": float(
            evaluation["accepted_as_in_scope_count"]
        ),
    }
    for metric_name in ("unknown_recall", "false_accept_rate", "mean_confidence"):
        value = evaluation.get(metric_name)
        if value is not None:
            values[metric_name] = float(value)
    return [
        ModelEvaluationMetric(
            model_id=model_id,
            dataset_split="out_of_scope",
            language=OVERALL_LANGUAGE,
            taxonomy_level=3,
            taxonomy_leaf_key=UNKNOWN_LEAF_KEY,
            metric_name=metric_name,
            metric_value=value,
            sample_size=sample_size,
            details=details if metric_name == "sample_count" else None,
        )
        for metric_name, value in values.items()
    ]


def _dataset_version_for_model(report: dict[str, Any]) -> str:
    versions = list(report.get("dataset_versions") or [])
    if len(versions) == 1:
        return str(versions[0])[:100]
    fingerprint = str(report["dataset_fingerprint"])
    return f"mixed-{fingerprint[:16]}"


def _qualification(
    grouped_cv: dict[str, Any],
    test: dict[str, Any],
    out_of_scope: dict[str, Any],
    *,
    promotion_threshold: float,
    phase22_ready: bool,
    enforce_phase22_gate: bool,
) -> dict[str, Any]:
    grouped_cv_class_recalls = {
        leaf_key: float(metrics["recall"])
        for leaf_key, metrics in grouped_cv["per_class"].items()
    }
    test_class_recalls = {
        leaf_key: float(metrics["recall"])
        for leaf_key, metrics in test["per_class"].items()
    }
    checks = {
        "grouped_cv_accuracy": float(grouped_cv["accuracy"]),
        "grouped_cv_macro_f1": float(grouped_cv["f1_macro"]),
        "grouped_cv_minimum_class_recall": min(
            grouped_cv_class_recalls.values(),
            default=0.0,
        ),
        "test_accuracy": float(test["accuracy"]),
        "test_macro_f1": float(test["f1_macro"]),
        "test_minimum_class_recall": min(
            test_class_recalls.values(),
            default=0.0,
        ),
    }
    numeric_gate_passed = all(
        value >= promotion_threshold for value in checks.values()
    )
    unknown_sample_count = int(out_of_scope["sample_size"])
    unknown_recall = out_of_scope.get("unknown_recall")
    phase22_checks = {
        "collection_ready": bool(phase22_ready),
        "out_of_scope_sample_count": unknown_sample_count,
        "minimum_out_of_scope_sample_count": PHASE22_MINIMUM_OUT_OF_SCOPE_SAMPLES,
        "unknown_recall": unknown_recall,
        "minimum_unknown_recall": promotion_threshold,
    }
    blocked_reasons = []
    if not numeric_gate_passed:
        blocked_reasons.append("classification_metrics_below_threshold")
    if enforce_phase22_gate and not phase22_ready:
        blocked_reasons.append("phase22_collection_not_ready")
    if (
        enforce_phase22_gate
        and unknown_sample_count < PHASE22_MINIMUM_OUT_OF_SCOPE_SAMPLES
    ):
        blocked_reasons.append("insufficient_out_of_scope_evaluation_samples")
    if (
        enforce_phase22_gate
        and unknown_recall is not None
        and float(unknown_recall) < promotion_threshold
    ):
        blocked_reasons.append("unknown_recall_below_threshold")
    passed = not blocked_reasons
    return {
        "passed": passed,
        "numeric_gate_passed": numeric_gate_passed,
        "threshold": promotion_threshold,
        "checks": checks,
        "phase22_gate_enforced": enforce_phase22_gate,
        "phase22_checks": phase22_checks,
        "per_class_recall": {
            "grouped_cv": grouped_cv_class_recalls,
            "test": test_class_recalls,
        },
        "blocked_reasons": blocked_reasons,
        "blocked_reason": blocked_reasons[0] if blocked_reasons else None,
        "policy": (
            "grouped-CV accuracy/Macro F1/minimum per-class recall and untouched-"
            "test accuracy/Macro F1/minimum per-class recall must meet the "
            "threshold; the Phase 22 gate also requires collection coverage and "
            "an out-of-scope rejection evaluation"
        ),
        "activation": "manual_after_runtime_integration" if passed else "blocked",
    }


def train_and_evaluate_classification_models(
    db: Session,
    *,
    artifact_root: str | Path,
    model_version: str | None = None,
    required_leaf_keys: Sequence[str] | None = None,
    minimum_samples_per_leaf: int = MIN_VERIFIED_SAMPLES,
    unknown_threshold: float = UNKNOWN_CONFIDENCE_THRESHOLD,
    promotion_threshold: float = MODEL_PROMOTION_THRESHOLD,
    model_specs: Sequence[ClassificationModelSpec] | None = None,
    prepare_only: bool = False,
    smoke_test: bool = False,
    grouped_cv_folds: int = DEFAULT_GROUPED_CV_FOLDS,
    embedding_model: str = DEFAULT_MULTILINGUAL_EMBEDDING_MODEL,
    embedding_cache_folder: str | Path | None = None,
    allow_embedding_download: bool = False,
    enforce_phase22_gate: bool = True,
    progress_callback: Callable[[str, str | None], None] | None = None,
) -> dict[str, Any]:
    if not 0.0 < promotion_threshold <= 1.0:
        raise ClassificationTrainingError(
            "promotion_threshold must be greater than 0 and at most 1"
        )
    if not 0.0 < unknown_threshold < 1.0:
        raise ClassificationTrainingError("unknown_threshold must be between 0 and 1")
    if prepare_only and smoke_test:
        raise ClassificationTrainingError(
            "prepare_only and smoke_test cannot be enabled together"
        )
    if grouped_cv_folds < 2:
        raise ClassificationTrainingError("grouped_cv_folds must be at least 2")

    version = _safe_version(
        model_version or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    run_root = Path(artifact_root) / version
    if progress_callback:
        progress_callback("preparing", None)
    prepared = prepare_classification_dataset(
        db,
        artifact_root=run_root / "dataset",
        required_leaf_keys=required_leaf_keys,
        minimum_samples_per_leaf=minimum_samples_per_leaf,
    )
    base_result: dict[str, Any] = {
        "status": "prepared" if prepared.report["ready"] else "not_ready",
        "model_family": MODEL_FAMILY,
        "model_version": version,
        "dataset": prepared.report,
        "promotion_threshold": promotion_threshold,
        "unknown_threshold": unknown_threshold,
        "grouped_cv_folds_requested": grouped_cv_folds,
        "phase22_gate_enforced": enforce_phase22_gate,
        "models": [],
        "model_catalog": [],
        "skipped_models": [],
        "best_model": None,
        "database_models_created": 0,
        "active_model_changed": False,
        "smoke_test": smoke_test,
    }
    if smoke_test:
        base_result["warning"] = (
            "SMOKE TEST ONLY: this run verifies the training machinery with an "
            "incomplete dataset. It is not a final or production model."
        )
    if (prepare_only or not prepared.report["partition_integrity_passed"]
            or (not prepared.report["ready"] and not smoke_test)):
        report_path = run_root / "training_report.json"
        base_result["report_path"] = str(report_path.resolve())
        _write_json(report_path, base_result)
        return base_result

    configured_labels = tuple(prepared.report["required_leaf_keys"])
    development_label_counts = Counter(
        item.leaf_key
        for item in prepared.examples
        if item.split == "train"
    )
    labels = (
        tuple(
            leaf_key
            for leaf_key in configured_labels
            if development_label_counts[leaf_key] >= 2
        )
        if smoke_test
        else configured_labels
    )
    if len(labels) < 2:
        raise ClassificationTrainingError(
            "smoke test requires at least two labels with two training rows each"
        )
    development_rows = [
        item
        for item in prepared.examples
        if item.split == "train" and item.leaf_key in labels
    ]
    validation_rows = [item for item in prepared.examples
                       if item.split == "validation" and item.leaf_key in labels]
    unknown_validation = [item for item in prepared.out_of_scope_examples if item.split == "validation"]
    unknown_test = [item for item in prepared.out_of_scope_examples if item.split == "test"]
    test_rows = [
        item
        for item in prepared.examples
        if item.split == "test" and item.leaf_key in labels
    ]
    if not development_rows or not test_rows:
        raise ClassificationTrainingError(
            "training requires a non-empty development pool and untouched test split"
        )
    if smoke_test:
        base_result["smoke_test_scope"] = {
            "included_leaf_keys": list(labels),
            "excluded_leaf_keys": [
                leaf_key for leaf_key in configured_labels if leaf_key not in labels
            ],
            "dataset_sample_count": len(development_rows) + len(validation_rows) + len(test_rows),
            "split_counts": {
                "train": len(development_rows),
                "validation": len(validation_rows),
                "test": len(test_rows),
            },
            "promotion_eligible": False,
        }
    specs = tuple(
        model_specs
        or default_classification_model_specs(
            embedding_model=embedding_model,
            embedding_cache_folder=embedding_cache_folder,
            allow_embedding_download=allow_embedding_download,
        )
    )
    if len(specs) < 2:
        raise ClassificationTrainingError("at least two model specifications are required")

    available_specs: list[ClassificationModelSpec] = []
    for spec in specs:
        available = True
        unavailable_reason = None
        if spec.availability is not None:
            try:
                available, unavailable_reason = spec.availability()
            except Exception as exc:
                available = False
                unavailable_reason = f"availability check failed: {exc}"
        catalog_item = {
            "model_key": spec.model_key,
            "model_type": spec.model_type,
            "description": spec.description,
            "tuning_candidates": [
                parameters for parameters, _factory in spec.tuning_factories
            ],
            "status": "available" if available else "skipped_unavailable",
            "reason": unavailable_reason,
        }
        base_result["model_catalog"].append(catalog_item)
        if available:
            available_specs.append(spec)
        else:
            base_result["skipped_models"].append(catalog_item)
    if len(available_specs) < 2:
        raise ClassificationTrainingError(
            "at least two available model specifications are required"
        )

    existing = (
        db.query(ClassificationModel)
        .filter(
            ClassificationModel.model_version == version,
            ClassificationModel.model_key.in_(
                [item.model_key for item in available_specs]
            ),
        )
        .count()
    )
    if existing:
        raise ClassificationTrainingError(
            f"model_version '{version}' already exists; choose a new version"
        )

    trained_results: list[dict[str, Any]] = []
    estimators: dict[str, Any] = {}
    scope_policies: dict[str, dict] = {}
    for spec in available_specs:
        if progress_callback:
            progress_callback("cross_validation", spec.model_key)
        try:
            tuning_report: dict[str, Any] | None = None
            selected_factory = spec.factory
            if spec.tuning_factories:
                candidate_results = []
                for parameters, candidate_factory in spec.tuning_factories:
                    candidate_spec = ClassificationModelSpec(
                        model_key=spec.model_key,
                        model_type=spec.model_type,
                        description=spec.description,
                        factory=candidate_factory,
                    )
                    candidate_grouped_cv = _grouped_cross_validation(
                        candidate_spec,
                        development_rows,
                        labels=labels,
                        requested_folds=grouped_cv_folds,
                        unknown_threshold=unknown_threshold,
                    )
                    overall = candidate_grouped_cv["evaluations"][OVERALL_LANGUAGE]
                    candidate_results.append(
                        {
                            "parameters": dict(parameters),
                            "factory": candidate_factory,
                            "grouped_cv": candidate_grouped_cv,
                            "accuracy": float(overall["accuracy"]),
                            "macro_f1": float(overall["f1_macro"]),
                            "minimum_class_recall": min(
                                (
                                    float(metrics["recall"])
                                    for metrics in overall["per_class"].values()
                                ),
                                default=0.0,
                            ),
                        }
                    )
                selected_candidate = max(
                    candidate_results,
                    key=lambda item: (
                        item["macro_f1"],
                        item["accuracy"],
                        item["minimum_class_recall"],
                    ),
                )
                selected_factory = selected_candidate["factory"]
                grouped_cv = selected_candidate["grouped_cv"]
                tuning_report = {
                    "selection_protocol": (
                        "grouped_cv_macro_f1_then_accuracy_then_minimum_class_recall"
                    ),
                    "selected_parameters": selected_candidate["parameters"],
                    "candidates": [
                        {
                            "parameters": item["parameters"],
                            "grouped_cv_accuracy": item["accuracy"],
                            "grouped_cv_macro_f1": item["macro_f1"],
                            "grouped_cv_minimum_class_recall": item[
                                "minimum_class_recall"
                            ],
                        }
                        for item in candidate_results
                    ],
                }
            else:
                grouped_cv = _grouped_cross_validation(
                    spec,
                    development_rows,
                    labels=labels,
                    requested_folds=grouped_cv_folds,
                    unknown_threshold=unknown_threshold,
                )
            estimator = selected_factory()
            if progress_callback:
                progress_callback("fitting", spec.model_key)
            estimator.fit(
                [item.model_text for item in development_rows],
                [item.leaf_key for item in development_rows],
            )
            if progress_callback:
                progress_callback("evaluating", spec.model_key)
            policy = fit_acceptance_policy(
                estimator, development_rows, validation_rows, unknown_validation,
                labels=labels, confidence_threshold=unknown_threshold,
                required_recall=promotion_threshold,
                policy_version=spec.scope_policy_version,
            )
            validation_result = evaluate_acceptance_policy(policy, estimator, validation_rows, labels=labels)
            test_raw = _evaluation_by_language(
                estimator,
                test_rows,
                labels=labels,
                unknown_threshold=unknown_threshold,
            )
            test_result = evaluate_acceptance_policy(policy, estimator, test_rows, labels=labels)
            test = _evaluation_by_language_from_predictions(
                test_rows, test_result["predictions"], test_result["confidences"], labels=labels)
            out_of_scope = _evaluate_out_of_scope(
                estimator,
                unknown_test,
                unknown_threshold=unknown_threshold,
                scope_policy=policy,
            )
        except Exception as exc:
            failure = {
                "model_key": spec.model_key,
                "model_type": spec.model_type,
                "description": spec.description,
                "status": "failed_during_benchmark",
                "reason": f"{type(exc).__name__}: {exc}",
            }
            base_result["skipped_models"].append(failure)
            for catalog_item in base_result["model_catalog"]:
                if catalog_item["model_key"] == spec.model_key:
                    catalog_item.update(
                        status=failure["status"],
                        reason=failure["reason"],
                    )
                    break
            continue
        gate = _qualification(
            grouped_cv["evaluations"][OVERALL_LANGUAGE],
            test[OVERALL_LANGUAGE],
            out_of_scope,
            promotion_threshold=promotion_threshold,
            phase22_ready=bool(prepared.report["phase22_ready"]),
            enforce_phase22_gate=enforce_phase22_gate and not smoke_test,
        )
        if policy["status"] != "validated":
            gate["blocked_reasons"].append("scope_validation_not_passed")
        gate["scope_validation_status"] = policy["status"]
        gate["scope_policy_version"] = policy["version"]
        if (len(unknown_test) < MIN_UNKNOWN_TEST
                or len({r.source_channel_id for r in unknown_test if r.source_channel_id}) < MIN_UNKNOWN_CHANNELS):
            gate["blocked_reasons"].append("insufficient_unknown_test")
        if out_of_scope["unknown_recall"] is None or out_of_scope["unknown_recall"] < promotion_threshold:
            gate["blocked_reasons"].append("unknown_test_not_passed")
        gate["passed"] = not gate["blocked_reasons"]
        gate["blocked_reason"] = next(iter(gate["blocked_reasons"]), None)
        gate["activation"] = "manual_after_runtime_integration" if gate["passed"] else "blocked"
        if smoke_test:
            gate.update(
                {
                    "passed": False,
                    "eligible_for_promotion": False,
                    "blocked_reason": "smoke_test_incomplete_dataset",
                    "blocked_reasons": ["smoke_test_incomplete_dataset"],
                    "activation": "blocked_smoke_test",
                }
            )
        else:
            gate["eligible_for_promotion"] = bool(gate["passed"])
        trained_results.append(
            {
                "model_key": spec.model_key,
                "model_type": spec.model_type,
                "description": spec.description,
                "tuning": tuning_report,
                "grouped_cv": grouped_cv,
                "validation": _evaluation_by_language_from_predictions(
                    validation_rows, validation_result["predictions"], validation_result["confidences"],
                    labels=labels) if validation_rows else {},
                "scope_policy": acceptance_summary(policy),
                "scope_validation": validation_result,
                "test_raw": test_raw,
                "test": test,
                "out_of_scope": out_of_scope,
                "qualification": gate,
            }
        )
        estimators[spec.model_key] = estimator
        scope_policies[spec.model_key] = policy

    if len(trained_results) < 2:
        base_result["status"] = "benchmark_failed"
        report_path = run_root / "training_report.json"
        base_result["report_path"] = str(report_path.resolve())
        _write_json(report_path, base_result)
        raise ClassificationTrainingError(
            "fewer than two classifiers completed the benchmark; inspect "
            f"{report_path.resolve()}"
        )

    ranked = sorted(
        trained_results,
        key=lambda item: (
            -int(item["scope_policy"]["status"] == "validated"),
            -float(
                item["grouped_cv"]["evaluations"][OVERALL_LANGUAGE]["f1_macro"]
            ),
            -float(
                item["grouped_cv"]["evaluations"][OVERALL_LANGUAGE]["accuracy"]
            ),
            -min(
                (
                    float(metrics["recall"])
                    for metrics in item["grouped_cv"]["evaluations"][
                        OVERALL_LANGUAGE
                    ]["per_class"].values()
                ),
                default=0.0,
            ),
            str(item["model_key"]),
        ),
    )
    rank_by_key = {
        str(item["model_key"]): index
        for index, item in enumerate(ranked, start=1)
    }

    dataset_manifest_path = prepared.report["artifacts"].get("manifest_path")
    dataset_manifest_sha256 = prepared.report["artifacts"].get("manifest_sha256")
    now = _utc_now()
    if progress_callback:
        progress_callback("persisting", None)
    try:
        for result in trained_results:
            model_key = str(result["model_key"])
            model_dir = run_root / model_key
            model_dir.mkdir(parents=True, exist_ok=True)
            artifact_path = model_dir / "model.joblib"
            bundle = {
                "artifact_schema_version": 3,
                "model_family": MODEL_FAMILY,
                "model_key": model_key,
                "model_version": version,
                "model_type": result["model_type"],
                "selected_hyperparameters": dict(
                    (result.get("tuning") or {}).get(
                        "selected_parameters"
                    )
                    or {}
                ),
                "taxonomy_version": TAXONOMY_VERSION,
                "labels": list(labels),
                "unknown_leaf_key": UNKNOWN_LEAF_KEY,
                "unknown_threshold": unknown_threshold,
                "dataset_fingerprint": prepared.report["dataset_fingerprint"],
                "dataset_manifest_path": dataset_manifest_path,
                "dataset_manifest_sha256": dataset_manifest_sha256,
                "smoke_test_only": smoke_test,
                "training_dataset_ready": bool(prepared.report["ready"]),
                "phase22_collection_ready": bool(
                    prepared.report["phase22_ready"]
                ),
                "evaluation_protocol": result["grouped_cv"]["protocol"],
                "grouped_cv_fold_count": result["grouped_cv"]["fold_count"],
                "development_sample_count": len(development_rows),
                "fit_split": "train",
                "scope_policy": scope_policies[model_key],
                "scope_test_passed": bool(result["qualification"]["passed"]),
                "out_of_scope_evaluation_sample_count": len(
                    prepared.out_of_scope_examples
                ),
                "estimator": estimators[model_key],
            }
            _write_joblib(artifact_path, bundle)
            probe = test_rows[0]
            reloaded_prediction = classify_with_artifact(
                artifact_path,
                title=probe.title,
                text=probe.transcript,
            )
            reload_check = {
                "passed": True,
                "probe_dataset_id": probe.dataset_id,
                "expected_leaf_key": probe.leaf_key,
                "raw_predicted_leaf_key": reloaded_prediction[
                    "raw_taxonomy_leaf_key"
                ],
                "predicted_leaf_key": reloaded_prediction["taxonomy_leaf_key"],
                "confidence": reloaded_prediction["confidence"],
            }
            result["artifact_reload_check"] = reload_check
            evaluation_path = model_dir / "evaluation.json"
            evaluation_payload = {
                key: value
                for key, value in result.items()
                if key not in {"model_id", "artifact_path", "evaluation_path"}
            }
            evaluation_payload.update(
                {
                    "model_version": version,
                    "selection_rank": rank_by_key[model_key],
                    "dataset_fingerprint": prepared.report["dataset_fingerprint"],
                    "artifact_sha256": _sha256_file(artifact_path),
                    "is_active": False,
                }
            )
            _write_json(evaluation_path, evaluation_payload)

            model = ClassificationModel(
                model_key=model_key,
                model_version=version,
                taxonomy_version=TAXONOMY_VERSION,
                model_type=str(result["model_type"]),
                artifact_path=str(artifact_path.resolve()),
                training_dataset_source=YOUTUBE_PUBLIC_DATASET_SOURCE,
                training_dataset_version=_dataset_version_for_model(
                    prepared.report
                ),
                training_sample_count=len(development_rows),
                status=(
                    "smoke_test_only"
                    if smoke_test
                    else "qualified"
                    if result["qualification"]["passed"]
                    else "evaluated_below_threshold"
                ),
                is_active=False,
                trained_at=now,
            )
            db.add(model)
            db.flush()
            db.add_all(
                _metric_rows(
                    model_id=model.model_id,
                    dataset_split="grouped_cv",
                    evaluations=result["grouped_cv"]["evaluations"],
                )
            )
            db.add(
                ModelEvaluationMetric(
                    model_id=model.model_id,
                    dataset_split="grouped_cv",
                    language=OVERALL_LANGUAGE,
                    taxonomy_level=3,
                    taxonomy_leaf_key=OVERALL_LEAF_KEY,
                    metric_name="hard_case_count",
                    metric_value=float(len(result["grouped_cv"]["hard_cases"])),
                    sample_size=len(development_rows),
                    details=json.dumps(
                        {
                            "protocol": result["grouped_cv"]["protocol"],
                            "fold_count": result["grouped_cv"]["fold_count"],
                            "folds": result["grouped_cv"]["folds"],
                            "confusion_pairs": result["grouped_cv"][
                                "confusion_pairs"
                            ],
                            "hard_cases": result["grouped_cv"]["hard_cases"],
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                )
            )
            db.add_all(
                _metric_rows(
                    model_id=model.model_id,
                    dataset_split="validation",
                    evaluations=result["validation"],
                )
            )
            db.add_all(
                _metric_rows(
                    model_id=model.model_id,
                    dataset_split="test",
                    evaluations=result["test"],
                )
            )
            db.add_all(
                _out_of_scope_metric_rows(
                    model_id=model.model_id,
                    evaluation=result["out_of_scope"],
                )
            )
            db.add(
                ModelEvaluationMetric(
                    model_id=model.model_id,
                    dataset_split="promotion_gate",
                    language=OVERALL_LANGUAGE,
                    taxonomy_level=3,
                    taxonomy_leaf_key=OVERALL_LEAF_KEY,
                    metric_name="passed",
                    metric_value=(1.0 if result["qualification"]["passed"] else 0.0),
                    sample_size=(
                        len(development_rows)
                        + len(test_rows)
                        + len(prepared.out_of_scope_examples)
                    ),
                    details=json.dumps(
                        {
                            **result["qualification"],
                            "selection_rank": rank_by_key[model_key],
                            "unknown_threshold": unknown_threshold,
                            "dataset_fingerprint": prepared.report[
                                "dataset_fingerprint"
                            ],
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                )
            )
            db.add(
                ModelEvaluationMetric(
                    model_id=model.model_id,
                    dataset_split="artifact_check",
                    language=OVERALL_LANGUAGE,
                    taxonomy_level=3,
                    taxonomy_leaf_key=OVERALL_LEAF_KEY,
                    metric_name="reload_classify_passed",
                    metric_value=1.0,
                    sample_size=1,
                    details=json.dumps(
                        reload_check,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                )
            )
            result["model_id"] = model.model_id
            result["selection_rank"] = rank_by_key[model_key]
            result["artifact_path"] = str(artifact_path.resolve())
            result["artifact_sha256"] = _sha256_file(artifact_path)
            result["evaluation_path"] = str(evaluation_path.resolve())
            result["status"] = model.status
            result["is_active"] = False

        db.add(
            SystemLog(
                action=(
                    "classification_model_smoke_test"
                    if smoke_test
                    else "classification_model_benchmark"
                ),
                status="success",
                detail=json.dumps(
                    {
                        "model_version": version,
                        "dataset_fingerprint": prepared.report[
                            "dataset_fingerprint"
                        ],
                        "models": [
                            {
                                "model_key": item["model_key"],
                                "qualified": item["qualification"]["passed"],
                                "selection_rank": item["selection_rank"],
                            }
                            for item in trained_results
                        ],
                        "active_model_changed": False,
                        "smoke_test": smoke_test,
                        "evaluation_protocol": (
                            "stratified_group_k_fold_out_of_fold_plus_test_holdout"
                        ),
                        "phase22_collection_ready": bool(
                            prepared.report["phase22_ready"]
                        ),
                        "skipped_models": base_result["skipped_models"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    best = ranked[0]
    base_result.update(
        {
            "status": "smoke_test_evaluated" if smoke_test else "evaluated",
            "models": sorted(
                trained_results, key=lambda item: int(item["selection_rank"])
            ),
            "best_model": {
                "model_key": best["model_key"],
                "model_id": next(
                    item["model_id"]
                    for item in trained_results
                    if item["model_key"] == best["model_key"]
                ),
                "qualified": bool(best["qualification"]["passed"]),
                "smoke_test_only": smoke_test,
                "selection_basis": (
                    "scope_validation_then_grouped_cv_macro_f1_then_accuracy_then_"
                    "minimum_class_recall"
                ),
            },
            "database_models_created": len(trained_results),
            "active_model_changed": False,
        }
    )
    report_path = run_root / "training_report.json"
    base_result["report_path"] = str(report_path.resolve())
    _write_json(report_path, base_result)
    return base_result


@lru_cache(maxsize=8)
def _load_classification_artifact_cached(
    resolved_path: str,
    modified_ns: int,
) -> dict[str, Any]:
    del modified_ns
    return joblib.load(Path(resolved_path))


@lru_cache(maxsize=16)
def _artifact_digest_cached(path: str, modified_ns: int, size: int) -> str:
    del modified_ns, size
    return _sha256_file(Path(path))


def classification_artifact_sha256(path: str | Path) -> str:
    artifact_path = Path(path).resolve()
    stat = artifact_path.stat()
    return _artifact_digest_cached(str(artifact_path), stat.st_mtime_ns, stat.st_size)


def load_classification_artifact(path: str | Path) -> dict[str, Any]:
    artifact_path = Path(path).resolve()
    if not artifact_path.is_file():
        raise ClassificationTrainingError(
            f"classification artifact not found: {artifact_path}"
        )
    payload = _load_classification_artifact_cached(
        str(artifact_path),
        artifact_path.stat().st_mtime_ns,
    )
    required = {
        "artifact_schema_version",
        "model_key",
        "model_version",
        "labels",
        "unknown_leaf_key",
        "unknown_threshold",
        "estimator",
    }
    if not isinstance(payload, dict) or not required.issubset(payload):
        raise ClassificationTrainingError("invalid classification model artifact")
    return payload


def classify_with_artifact(
    path: str | Path,
    *,
    text: str,
    title: str | None = None,
    require_scope_validation: bool = True,
    allow_presentation: bool = False,
) -> dict[str, Any]:
    payload = load_classification_artifact(path)
    from app.services.classification_presentation import presentation_authorization
    grant = presentation_authorization(payload) if allow_presentation else {"authorized": False}
    # Keep title for API compatibility, but user filenames are never model features.
    del title
    merged_text = str(text or "").strip()
    estimator = payload["estimator"]
    raw_prediction = str(estimator.predict([merged_text])[0])
    probability_values = np.asarray(
        estimator.predict_proba([merged_text])[0],
        dtype=float,
    )
    probability_by_leaf = {
        str(leaf_key): round(float(probability), 6)
        for leaf_key, probability in zip(estimator.classes_, probability_values)
    }
    predictions, confidences = predict_with_unknown(
        estimator,
        [merged_text],
        unknown_threshold=float(payload["unknown_threshold"]),
    )
    policy = payload.get("scope_policy")
    acceptance_labels = [raw_prediction] if isinstance(policy, dict) and (
        policy.get("status") == "validated" or grant["authorized"]
    ) else predictions
    predictions, acceptance = apply_acceptance_policy(
        policy, [merged_text], acceptance_labels, confidences,
        require_validation=require_scope_validation,
        allow_presentation=grant["authorized"],
    )
    if allow_presentation:
        acceptance[0].update(presentation_authorization=grant)
        if not grant["authorized"]:
            predictions = [UNKNOWN_LEAF_KEY]
            acceptance[0].update(accepted=False, enforced=True, reason=grant["reason"])
    return {
        "model_key": str(payload["model_key"]),
        "model_version": str(payload["model_version"]),
        "model_type": str(payload.get("model_type") or "unknown"),
        "raw_taxonomy_leaf_key": raw_prediction,
        "taxonomy_leaf_key": predictions[0],
        "confidence": confidences[0],
        "probabilities": dict(
            sorted(
                probability_by_leaf.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ),
        "is_unknown": predictions[0] == str(payload["unknown_leaf_key"]),
        "unknown_threshold": float(payload["unknown_threshold"]),
        "smoke_test_only": bool(payload.get("smoke_test_only", False)),
        "acceptance": acceptance[0],
    }


def activate_classification_model(db: Session, model_id: int, *, user_id: int | None = None) -> dict[str, Any]:
    model = (
        db.query(ClassificationModel)
        .filter(ClassificationModel.model_id == model_id)
        .first()
    )
    if model is None:
        raise ClassificationTrainingError(f"classification model {model_id} not found")
    if model.status != "qualified":
        raise ClassificationTrainingError(
            f"classification model {model_id} is not qualified (status={model.status})"
        )
    payload = load_classification_artifact(str(model.artifact_path or ""))
    if bool(payload.get("smoke_test_only", False)):
        raise ClassificationTrainingError("smoke-test models cannot be activated")
    if (not is_validated_acceptance_policy(payload.get("scope_policy"))
            or not payload.get("scope_test_passed")):
        raise ClassificationTrainingError("model has not passed validation-selected scope rejection and its test gate")
    if str(payload["model_key"]) != str(model.model_key):
        raise ClassificationTrainingError("artifact model key does not match database row")
    if str(payload["model_version"]) != str(model.model_version):
        raise ClassificationTrainingError(
            "artifact model version does not match database row"
        )

    db.query(ClassificationModel).filter(
        ClassificationModel.is_active.is_(True)
    ).update({ClassificationModel.is_active: False}, synchronize_session=False)
    model.is_active = True
    db.add(
        SystemLog(
            action="classification_model_activate",
            user_id=user_id,
            status="success",
            detail=json.dumps(
                {
                    "model_id": model.model_id,
                    "model_key": model.model_key,
                    "model_version": model.model_version,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
    )
    db.commit()
    return {
        "model_id": int(model.model_id),
        "model_key": str(model.model_key),
        "model_version": str(model.model_version),
        "status": str(model.status),
        "is_active": True,
    }
