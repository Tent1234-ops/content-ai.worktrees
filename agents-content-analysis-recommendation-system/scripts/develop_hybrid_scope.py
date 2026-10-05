"""Bounded Train/Validation hybrid experiment; no Test queries or registration."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import joblib
import numpy as np
from scipy.sparse import hstack
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import FeatureUnion, Pipeline
from threadpoolctl import threadpool_limits

from app.database.db import SessionLocal
from app.services.classification_acceptance import (
    POLICY_VERSION, CONTRAST_POLICY_VERSION, _raw_predictions, acceptance_summary,
    evaluate_acceptance_policy, fit_acceptance_policy,
)
from app.services.classification_features import thai_transcript_features
from app.services.classification_training import (
    DEFAULT_MULTILINGUAL_EMBEDDING_MODEL, SentenceEmbeddingTransformer,
    _dataset_fingerprint, _evaluate_predictions,
)
from scripts.develop_classification_scope import LABELS, load_development_rows


def run(out):
    out.mkdir(parents=True, exist_ok=False)
    with SessionLocal() as db:
        train, validation, unknown = load_development_rows(db)
    rows = [*validation, *unknown]
    texts = [r.model_text for r in train]
    validation_texts = [r.model_text for r in rows]
    y = np.array([r.leaf_key for r in train])
    groups = np.array([r.creator_group_key for r in train])
    embedding = SentenceEmbeddingTransformer(DEFAULT_MULTILINGUAL_EMBEDDING_MODEL,
        cache_folder=str(ROOT / "models_cache/sentence_transformers"), local_files_only=True)
    print("Encoding frozen local embeddings for Train/Validation only", flush=True)
    encoded = embedding.transform(texts)
    validation_encoded = embedding.transform(validation_texts)
    folds = []
    for ti, vi in StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42).split(texts, y, groups):
        assert not set(groups[ti]) & set(groups[vi])
        lexical = thai_transcript_features()
        xtrain = hstack([lexical.fit_transform([texts[i] for i in ti]), encoded[ti]], format="csr")
        xval = hstack([lexical.transform([texts[i] for i in vi]), encoded[vi]], format="csr")
        folds.append((ti, vi, xtrain, xval))
    candidates = []
    for c in (0.5, 1, 2, 4, 8, 16):
        predictions, confidences = [""] * len(train), [0.0] * len(train)
        for ti, vi, xtrain, xval in folds:
            classifier = LogisticRegression(C=c, class_weight="balanced", max_iter=4000, random_state=42)
            classifier.fit(xtrain, y[ti])
            probabilities = classifier.predict_proba(xval)
            for index, p in zip(vi, probabilities):
                confidence = float(p.max())
                predictions[index] = str(classifier.classes_[p.argmax()]) if confidence >= 0.6 else "unknown"
                confidences[index] = confidence
        metrics = _evaluate_predictions(train, predictions, confidences, labels=LABELS)
        candidates.append({"C": c, "grouped_cv": metrics})
        print(json.dumps(candidates[-1]), flush=True)
    selected = max(candidates, key=lambda r: (
        r["grouped_cv"]["f1_macro"], r["grouped_cv"]["accuracy"],
        min(m["recall"] for m in r["grouped_cv"]["per_class"].values()), -r["C"],
    ))
    lexical = thai_transcript_features()
    matrix = hstack([lexical.fit_transform(texts), encoded], format="csr")
    classifier = LogisticRegression(C=selected["C"], class_weight="balanced", max_iter=4000, random_state=42).fit(matrix, y)
    estimator = Pipeline([("features", FeatureUnion([("lexical", lexical), ("embeddings", embedding)])),
                          ("classifier", classifier)])
    # Check cached development math against the actual serialized runtime pipeline.
    cached = classifier.predict_proba(hstack([lexical.transform(validation_texts), validation_encoded], format="csr"))
    np.testing.assert_allclose(cached, estimator.predict_proba(validation_texts), atol=1e-8)
    report = {"protocol": "laptop-scope-20261004-hybrid", "test_accessed": False,
              "active_model_changed": False, "development_fingerprint": _dataset_fingerprint([*train, *validation, *unknown]),
              "cv_candidates": candidates, "selected": selected,
              "train_ids": [r.dataset_id for r in train], "validation_ids": [r.dataset_id for r in rows],
              "policies": []}
    for version in (POLICY_VERSION, CONTRAST_POLICY_VERSION):
        policy = fit_acceptance_policy(estimator, train, validation, unknown, labels=LABELS,
                                      confidence_threshold=0.6, policy_version=version)
        result = evaluate_acceptance_policy(policy, estimator, rows, labels=LABELS)
        report["policies"].append({"policy": acceptance_summary(policy), "validation": result})
        joblib.dump({"estimator": estimator, "scope_policy": policy, "development_only": True}, out / f"{version}.joblib")
        print(json.dumps({"policy": version, "status": policy["status"], "selected": policy.get("selected_validation")}), flush=True)
    raw, confidences = _raw_predictions(estimator, validation_texts)
    report["rows"] = [{"dataset_id": r.dataset_id, "title": r.title, "gold": r.leaf_key,
                       "raw": p, "confidence": c} for r, p, c in zip(rows, raw, confidences)]
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    import torch
    torch.set_num_threads(2)
    with threadpool_limits(limits=2):
        run(parser.parse_args().out)
