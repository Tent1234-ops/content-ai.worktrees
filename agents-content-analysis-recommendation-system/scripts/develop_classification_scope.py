"""Train/Validation-only scope experiment. Does not query Test or activate models."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from app.database.db import SessionLocal
from app.database.models import DatasetContent
from app.services.classification_acceptance import (
    CONTRAST_POLICY_VERSION,
    _metrics, _raw_predictions, acceptance_summary, evaluate_acceptance_policy,
    fit_acceptance_policy, partition_conflicts,
)
from app.services.classification_features import FEATURE_VERSION, thai_transcript_features
from app.services.classification_training import (
    ClassificationModelSpec, _dataset_fingerprint, _dataset_row_to_example,
    _grouped_cross_validation, _word_char_features,
)
from app.services.dataset_eligibility import production_transcript_query, out_of_scope_evaluation_query

LABELS = ("phone", "camera", "laptop")
REGULARIZATION = (0.5, 1.0, 2.0, 4.0)


def load_development_rows(db):
    known = [_dataset_row_to_example(r) for r in production_transcript_query(db).filter(
        DatasetContent.taxonomy_leaf_key.in_(LABELS),
        DatasetContent.data_split.in_(("train", "validation")),
    ).order_by(DatasetContent.dataset_id).all()]
    unknown = [_dataset_row_to_example(r) for r in out_of_scope_evaluation_query(db).filter(
        DatasetContent.data_split == "validation",
    ).order_by(DatasetContent.dataset_id).all()]
    if partition_conflicts([*known, *unknown]):
        raise ValueError("Train/Validation overlap")
    return [r for r in known if r.split == "train"], [r for r in known if r.split == "validation"], unknown


def estimator_for(feature, c):
    features = _word_char_features() if feature == "legacy" else thai_transcript_features(words=feature == "thai_word_char")
    return Pipeline([("features", features), ("classifier", LogisticRegression(
        C=c, max_iter=4000, class_weight="balanced", solver="lbfgs", random_state=42,
    ))])


def run(out: Path):
    out.mkdir(parents=True, exist_ok=False)
    with SessionLocal() as db:
        train, validation, unknown = load_development_rows(db)
    report = {"protocol": "laptop-scope-20261004", "feature_version": FEATURE_VERSION,
              "development_fingerprint": _dataset_fingerprint([*train, *validation, *unknown]),
              "test_accessed": False, "active_model_changed": False,
              "train_ids": [r.dataset_id for r in train],
              "validation_ids": [r.dataset_id for r in [*validation, *unknown]], "candidates": []}
    for feature in ("legacy", "thai_char", "thai_word_char"):
        candidates = []
        for c in REGULARIZATION:
            spec = ClassificationModelSpec(feature, feature, feature, lambda: estimator_for(feature, c))
            cv = _grouped_cross_validation(spec, train, labels=LABELS, requested_folds=5, unknown_threshold=0.6)
            candidate = {"feature": feature, "C": c, "grouped_cv": cv}
            candidates.append(candidate)
            print(json.dumps({"feature": feature, "C": c, "cv": cv["evaluations"]["all"]}), flush=True)
        selected = max(candidates, key=lambda r: (
            r["grouped_cv"]["evaluations"]["all"]["f1_macro"],
            r["grouped_cv"]["evaluations"]["all"]["accuracy"], -r["C"],
        ))
        estimator = estimator_for(feature, selected["C"])
        estimator.fit([r.model_text for r in train], [r.leaf_key for r in train])
        policy = fit_acceptance_policy(estimator, train, validation, unknown,
                                       labels=LABELS, confidence_threshold=0.6)
        rows = [*validation, *unknown]
        raw, confidences = _raw_predictions(estimator, [r.model_text for r in rows])
        result = {"feature": feature, "C": selected["C"], "cv_candidates": candidates,
                  "scope_policy": acceptance_summary(policy),
                  "validation": evaluate_acceptance_policy(policy, estimator, rows, labels=LABELS),
                  "raw_validation_metrics": _metrics([r.leaf_key for r in rows], raw, LABELS),
                  "rows": [{"dataset_id": r.dataset_id, "title": r.title, "gold": r.leaf_key,
                            "channel": r.source_channel_id, "transcript_sha256": r.transcript_sha256,
                            "raw": pred, "confidence": conf, "characters": len(r.model_text)}
                           for r, pred, conf in zip(rows, raw, confidences)]}
        report["candidates"].append(result)
        joblib.dump({"estimator": estimator, "scope_policy": policy, "development_only": True}, out / f"{feature}.joblib")
        (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"feature": feature, "scope": policy["status"], "raw": result["raw_validation_metrics"]}), flush=True)
    return report


def recalibrate(source: Path, out: Path):
    """Reuse frozen Train-only fits; never fit a classifier on calibration data."""
    original = json.loads((source / "report.json").read_text(encoding="utf-8"))
    with SessionLocal() as db:
        train, validation, unknown = load_development_rows(db)
    if original["development_fingerprint"] != _dataset_fingerprint([*train, *validation, *unknown]):
        raise ValueError("Development data changed; do not reuse stale estimators")
    out.mkdir(parents=True, exist_ok=False)
    report = {"source": str(source), "development_fingerprint": original["development_fingerprint"],
              "policy_version": CONTRAST_POLICY_VERSION, "test_accessed": False, "candidates": []}
    for candidate in original["candidates"]:
        feature = candidate["feature"]
        estimator = joblib.load(source / f"{feature}.joblib")["estimator"]
        policy = fit_acceptance_policy(estimator, train, validation, unknown, labels=LABELS,
                                       confidence_threshold=0.6, policy_version=CONTRAST_POLICY_VERSION)
        result = {"feature": feature, "C": candidate["C"], "scope_policy": acceptance_summary(policy),
                  "validation": evaluate_acceptance_policy(policy, estimator, [*validation, *unknown], labels=LABELS)}
        report["candidates"].append(result)
        joblib.dump({"estimator": estimator, "scope_policy": policy, "development_only": True}, out / f"{feature}.joblib")
        print(json.dumps({"feature": feature, "scope": policy["status"], "selected": policy.get("selected_validation")}), flush=True)
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--recalibrate", type=Path, help="Completed development run; no classifier refit")
    args = parser.parse_args()
    from threadpoolctl import threadpool_limits
    with threadpool_limits(limits=2):
        recalibrate(args.recalibrate, args.out) if args.recalibrate else run(args.out)
