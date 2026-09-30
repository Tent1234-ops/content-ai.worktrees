"""Validation-selected rejection, never an alternative category classifier."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter, defaultdict

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer


POLICY_VERSION = "validation-scope-v1"
MIN_VALIDATION_PER_LABEL = 3
MIN_UNKNOWN_VALIDATION = 10
MIN_UNKNOWN_CHANNELS = 3
MIN_UNKNOWN_TEST = 10
SIMILARITY_THRESHOLDS = tuple(round(i / 20, 2) for i in range(20))


def transcript_identity(text: str) -> str:
    normalized = re.sub(r"\s+", "", unicodedata.normalize("NFKC", text).casefold())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def partition_conflicts(examples) -> list[dict]:
    """Check identity across all labels, including rejection-only examples."""
    indexes = {key: defaultdict(list) for key in (
        "dataset_id", "source_youtube_id", "source_channel_id", "creator_group_key", "transcript",
    )}
    for row in examples:
        for key, lookup in indexes.items():
            value = (transcript_identity(row.transcript) if row.transcript.strip() else "") if key == "transcript" else getattr(row, key)
            if value:
                lookup[value].append(row)
    conflicts = []
    for key, lookup in indexes.items():
        for rows in lookup.values():
            splits = {r.split for r in rows}
            if len(splits) > 1:
                conflicts.append({"field": key, "dataset_ids": sorted({r.dataset_id for r in rows}),
                                  "splits": sorted(splits)})
    return conflicts


def _raw_predictions(estimator, texts):
    probabilities = np.asarray(estimator.predict_proba(list(texts)), dtype=float)
    classes = np.asarray(estimator.classes_)
    if (probabilities.shape != (len(texts), len(classes))
            or not np.isfinite(probabilities).all()
            or (probabilities < 0).any() or (probabilities > 1).any()
            or not np.allclose(probabilities.sum(axis=1), 1)):
        raise ValueError("Classifier returned invalid probabilities")
    indexes = probabilities.argmax(axis=1)
    return classes[indexes].astype(str).tolist(), probabilities[np.arange(len(texts)), indexes].tolist()


def _similarities(policy, texts, predictions):
    vectors = policy["vectorizer"].transform(texts)
    references = policy["train_vectors"]
    labels = np.asarray(policy["train_labels"])
    scores = []
    for vector, label in zip(vectors, predictions):
        subset = references[labels == label]
        scores.append(float((vector @ subset.T).max()) if subset.shape[0] else 0.0)
    return scores


def _metrics(gold, predicted, labels):
    from sklearn.metrics import accuracy_score, f1_score
    in_scope = [i for i, value in enumerate(gold) if value in labels]
    outside = [i for i, value in enumerate(gold) if value == "unknown"]
    recalls = {label: sum(predicted[i] == label for i in in_scope if gold[i] == label)
               / sum(gold[i] == label for i in in_scope)
               for label in labels if label in gold}
    return {
        "in_scope_sample_count": len(in_scope), "unknown_sample_count": len(outside),
        "in_scope_accuracy": float(accuracy_score([gold[i] for i in in_scope],
                                                  [predicted[i] for i in in_scope])) if in_scope else None,
        "in_scope_macro_f1": float(f1_score([gold[i] for i in in_scope], [predicted[i] for i in in_scope],
                                           labels=list(labels), average="macro", zero_division=0)) if in_scope else None,
        "per_class_recall": recalls,
        "minimum_class_recall": min(recalls.values()) if len(recalls) == len(labels) else None,
        "unknown_recall": sum(predicted[i] == "unknown" for i in outside) / len(outside) if outside else None,
        "unknown_false_accept_count": sum(predicted[i] != "unknown" for i in outside),
        "in_scope_abstention_count": sum(predicted[i] == "unknown" for i in in_scope),
    }


def fit_acceptance_policy(estimator, train_rows, validation_rows, unknown_validation_rows, *,
                          labels, confidence_threshold: float, required_recall: float = 0.8):
    """Fit text similarity on train only; choose the cutoff on validation only."""
    if not 0 < required_recall <= 1 or not 0 < confidence_threshold < 1:
        raise ValueError("Invalid acceptance requirements")
    if (any(r.split != "train" or r.leaf_key not in labels for r in train_rows)
            or any(r.split != "validation" or r.leaf_key not in labels for r in validation_rows)
            or any(r.split != "validation" or r.leaf_key != "unknown" for r in unknown_validation_rows)):
        raise ValueError("Scope calibration accepts train and validation only; never test rows")
    if partition_conflicts([*train_rows, *validation_rows, *unknown_validation_rows]):
        raise ValueError("Scope calibration data overlaps across partitions")
    counts = Counter(r.leaf_key for r in validation_rows)
    channels = {r.source_channel_id for r in unknown_validation_rows if r.source_channel_id}
    reasons = []
    if set(r.leaf_key for r in train_rows) != set(labels):
        reasons.append("missing_training_label")
    if any(counts[label] < MIN_VALIDATION_PER_LABEL for label in labels):
        reasons.append("insufficient_in_scope_validation")
    if len(unknown_validation_rows) < MIN_UNKNOWN_VALIDATION:
        reasons.append("insufficient_unknown_validation")
    if len(channels) < MIN_UNKNOWN_CHANNELS:
        reasons.append("insufficient_unknown_validation_channels")
    policy = {"version": POLICY_VERSION, "status": "not_ready", "labels": list(labels),
              "confidence_threshold": confidence_threshold, "similarity_threshold": None,
              "selection_split": "validation", "fit_split": "train",
              "required_recall": required_recall, "reasons": reasons,
              "validation_counts": dict(counts), "unknown_validation_count": len(unknown_validation_rows),
              "unknown_validation_channels": len(channels),
              "fit_dataset_ids": [r.dataset_id for r in train_rows],
              "validation_dataset_ids": [r.dataset_id for r in [*validation_rows, *unknown_validation_rows]],
              "selection_candidates": []}
    if reasons:
        return policy
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(3, 5), sublinear_tf=True,
                                 max_features=30000, dtype=np.float32)
    policy.update(vectorizer=vectorizer,
                  train_vectors=vectorizer.fit_transform([r.model_text for r in train_rows]),
                  train_labels=[r.leaf_key for r in train_rows])
    rows = [*validation_rows, *unknown_validation_rows]
    texts = [r.model_text for r in rows]
    predictions, confidences = _raw_predictions(estimator, texts)
    scores = _similarities(policy, texts, predictions)
    gold = [r.leaf_key for r in rows]
    for threshold in SIMILARITY_THRESHOLDS:
        accepted = [label if confidence >= confidence_threshold and score >= threshold else "unknown"
                    for label, confidence, score in zip(predictions, confidences, scores)]
        metrics = _metrics(gold, accepted, labels)
        passes = all(metrics[name] >= required_recall for name in (
            "minimum_class_recall", "unknown_recall", "in_scope_macro_f1"))
        policy["selection_candidates"].append({"threshold": threshold, "passes": passes, **metrics})
    feasible = [r for r in policy["selection_candidates"] if r["passes"]]
    if not feasible:
        policy.update(status="failed_validation", reasons=["no_validation_cutoff_passed"])
        return policy
    selected = max(feasible, key=lambda r: (
        (r["in_scope_macro_f1"] + r["unknown_recall"]) / 2,
        r["minimum_class_recall"], r["unknown_recall"], -r["threshold"],
    ))
    policy.update(status="validated", similarity_threshold=selected["threshold"], selected_validation=selected)
    return policy


def acceptance_summary(policy) -> dict:
    if not isinstance(policy, dict):
        return {"version": POLICY_VERSION, "status": "not_available", "reasons": ["scope_policy_missing"]}
    return {k: v for k, v in policy.items() if k not in {"vectorizer", "train_vectors", "train_labels"}}


def is_validated_acceptance_policy(policy) -> bool:
    return (isinstance(policy, dict) and policy.get("version") == POLICY_VERSION
             and policy.get("status") == "validated" and policy.get("selection_split") == "validation"
             and policy.get("fit_split") == "train"
             and all(k in policy for k in ("vectorizer", "train_vectors", "train_labels"))
             and isinstance(policy.get("labels"), (list, tuple)) and bool(policy["labels"])
             and all(isinstance(label, str) and label != "unknown" for label in policy["labels"])
             and isinstance(policy.get("confidence_threshold"), (float, int))
             and 0 < policy["confidence_threshold"] < 1
             and isinstance(policy.get("similarity_threshold"), (float, int))
             and 0 <= policy["similarity_threshold"] <= 1)


def apply_acceptance_policy(policy, texts, predictions, confidences, *, require_validation=True):
    if not (len(texts) == len(predictions) == len(confidences)):
        raise ValueError("Acceptance input counts do not match")
    if not is_validated_acceptance_policy(policy):
        final = ["unknown"] * len(texts) if require_validation else list(predictions)
        return final, [{"accepted": False, "enforced": require_validation,
                        "reason": "scope_validation_unavailable", "policy_version": POLICY_VERSION}
                       for _ in texts]
    try:
        scores = _similarities(policy, texts, predictions)
    except (ValueError, KeyError, TypeError, AttributeError, IndexError):
        return ["unknown"] * len(texts), [
            {"accepted": False, "enforced": True, "reason": "scope_policy_invalid",
             "policy_version": POLICY_VERSION} for _ in texts]
    final, decisions = [], []
    for text, label, confidence, score in zip(texts, predictions, confidences, scores):
        reason = "accepted"
        if not str(text).strip():
            reason = "no_transcript"
        elif label not in policy["labels"]:
            reason = "unsupported_label"
        elif not np.isfinite(confidence) or not 0 <= confidence <= 1 or confidence < policy["confidence_threshold"]:
            reason = "low_confidence"
        elif not np.isfinite(score) or score < policy["similarity_threshold"]:
            reason = "outside_training_support"
        accepted = reason == "accepted"
        final.append(label if accepted else "unknown")
        decisions.append({"accepted": accepted, "enforced": True, "reason": reason,
                          "policy_version": POLICY_VERSION,
                          "support_similarity": round(score, 6) if np.isfinite(score) else None,
                          "similarity_threshold": policy["similarity_threshold"],
                          "selection_split": "validation"})
    return final, decisions


def evaluate_acceptance_policy(policy, estimator, rows, *, labels):
    if not rows:
        return {"sample_size": 0, "metrics": None, "predictions": [], "decisions": []}
    texts = [r.model_text for r in rows]
    raw, confidences = _raw_predictions(estimator, texts)
    predictions, decisions = apply_acceptance_policy(policy, texts, raw, confidences)
    return {"sample_size": len(rows), "metrics": _metrics([r.leaf_key for r in rows], predictions, labels),
            "raw_predictions": raw, "predictions": predictions, "confidences": confidences,
            "decisions": decisions}
