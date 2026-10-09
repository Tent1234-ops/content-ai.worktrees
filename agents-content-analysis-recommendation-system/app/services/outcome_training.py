"""Outcome Prediction Phase 3 training and validation infrastructure.

Independent-test outcomes are never read here.  The highest real status this
module can produce is ``validation_passed``; qualification belongs to Phase 6.
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import joblib
import numpy as np
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    log_loss,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.services.outcome_dataset import (
    FEATURE_SCHEMA_VERSION,
    feature_schema as build_feature_schema,
    fit_benchmarks,
    label_records,
    validate_feature_vector,
    verify_manifest,
)
from app.services.outcome_prediction_readiness import (
    data_use_gate,
    validate_protocol,
)


ARTIFACT_SCHEMA_VERSION = "outcome-model-artifact-v1"
CALIBRATION_VERSION = "weighted-platt-sigmoid-v1"
TRAINING_REPORT_VERSION = "outcome-validation-report-v1"
MODEL_VERSION_PREFIX = "outcome-reference-relative-views"
TRAINING_SUPPORT_VERSION = "outcome-training-support-v1"


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False, default=str,
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class ConstantProbabilityModel:
    def __init__(self, probability: float):
        if not 0 < probability < 1:
            raise ValueError("Constant prior requires both labels")
        self.probability = float(probability)
        self.classes_ = np.asarray([0, 1])

    def predict_proba(self, values):
        count = len(values)
        positive = np.full(count, self.probability, dtype=float)
        return np.column_stack([1.0 - positive, positive])


class WeightedSigmoidCalibrator:
    def __init__(self, seed: int):
        self.seed = int(seed)
        self.estimator = LogisticRegression(
            C=1_000_000.0, solver="lbfgs", random_state=self.seed,
            max_iter=1000,
        )

    @staticmethod
    def _logits(probabilities) -> np.ndarray:
        values = np.clip(np.asarray(probabilities, dtype=float), 1e-6, 1 - 1e-6)
        return np.log(values / (1.0 - values)).reshape(-1, 1)

    def fit(self, probabilities, labels, sample_weight):
        labels = np.asarray(labels, dtype=int)
        if len(np.unique(labels)) != 2:
            raise ValueError("Calibration requires both labels")
        self.estimator.fit(
            self._logits(probabilities), labels,
            sample_weight=np.asarray(sample_weight, dtype=float),
        )
        return self

    def predict(self, probabilities) -> np.ndarray:
        return self.estimator.predict_proba(self._logits(probabilities))[:, 1]


def _positive_probability(estimator, values) -> np.ndarray:
    result = np.asarray(estimator.predict_proba(values), dtype=float)
    if result.shape != (len(values), 2):
        raise ValueError("Estimator returned invalid binary probabilities")
    if not np.isfinite(result).all() or (result < 0).any() or (result > 1).any():
        raise ValueError("Estimator returned non-finite probabilities")
    if not np.allclose(result.sum(axis=1), 1.0):
        raise ValueError("Estimator probabilities do not sum to one")
    return result[:, 1]


def _channel_weights(rows: list[dict[str, Any]]) -> np.ndarray:
    counts = Counter(str(row["source_channel_id"]) for row in rows)
    return np.asarray([
        1.0 / counts[str(row["source_channel_id"])] for row in rows
    ], dtype=float)


def _metric_values(labels, probabilities, weights) -> dict[str, Any]:
    y = np.asarray(labels, dtype=int)
    p = np.asarray(probabilities, dtype=float)
    w = np.asarray(weights, dtype=float)
    if not len(y) or len(y) != len(p) or len(y) != len(w) or w.sum() <= 0:
        return {"status": "not_evaluable", "reason": "empty_or_invalid_input"}
    if not np.isfinite(p).all() or (p < 0).any() or (p > 1).any():
        return {"status": "not_evaluable", "reason": "invalid_probabilities"}
    result = {
        "status": "evaluated", "sample_count": len(y),
        "positive_count": int(y.sum()), "negative_count": int((1 - y).sum()),
        "brier_score": float(np.average((p - y) ** 2, weights=w)),
        "log_loss": float(log_loss(y, p, labels=[0, 1], sample_weight=w)),
    }
    if len(np.unique(y)) == 2:
        result["roc_auc"] = float(roc_auc_score(y, p, sample_weight=w))
        result["pr_auc"] = float(average_precision_score(y, p, sample_weight=w))
    else:
        result.update(roc_auc=None, pr_auc=None, status="partially_evaluable",
                      reason="single_class")
    return result


def _calibration_bins(
    rows: list[dict[str, Any]], labels, probabilities, weights,
    protocol: dict[str, Any],
) -> dict[str, Any]:
    policy = (protocol.get("evaluation") or {}).get("calibration") or {}
    requested_bins = int(policy.get("bins", 3))
    minimum_videos = int(policy.get("minimum_videos_per_bin", 10))
    minimum_channels = int(policy.get("minimum_channels_per_bin", 3))
    maximum_gap = float(policy.get("maximum_absolute_gap", 0.15))
    y = np.asarray(labels, dtype=int)
    p = np.asarray(probabilities, dtype=float)
    w = np.asarray(weights, dtype=float)
    if not len(rows) or len(rows) != len(y):
        return {"status": "not_evaluable", "reason": "empty_or_invalid_input", "bins": []}

    # Keep exact probability ties together; stable dataset_id breaks ordering only
    # between distinct scores and never manufactures extra bins.
    ordered = sorted(range(len(rows)), key=lambda index: (
        float(p[index]), int(rows[index]["dataset_id"])
    ))
    groups: list[list[int]] = []
    for index in ordered:
        if not groups or float(p[groups[-1][0]]) != float(p[index]):
            groups.append([])
        groups[-1].append(index)
    target = len(rows) / requested_bins
    bins: list[list[int]] = []
    current: list[int] = []
    for group in groups:
        if current and len(bins) < requested_bins - 1 and len(current) >= target:
            bins.append(current)
            current = []
        current.extend(group)
    if current:
        bins.append(current)

    output = []
    for number, indexes in enumerate(bins, start=1):
        local_weights = w[indexes]
        mean_prediction = float(np.average(p[indexes], weights=local_weights))
        observed_rate = float(np.average(y[indexes], weights=local_weights))
        channels = len({rows[index]["source_channel_id"] for index in indexes})
        output.append({
            "bin": number, "video_count": len(indexes), "channel_count": channels,
            "mean_prediction": mean_prediction, "observed_rate": observed_rate,
            "absolute_gap": abs(mean_prediction - observed_rate),
            "minimums_met": len(indexes) >= minimum_videos and channels >= minimum_channels,
        })
    evaluable = len(output) == requested_bins and all(item["minimums_met"] for item in output)
    max_gap = max((item["absolute_gap"] for item in output), default=None)
    return {
        "status": "evaluated" if evaluable else "not_evaluable",
        "reason": None if evaluable else "bin_support_not_met_or_ties_collapsed",
        "requested_bins": requested_bins, "actual_bins": len(output),
        "minimum_videos_per_bin": minimum_videos,
        "minimum_channels_per_bin": minimum_channels,
        "maximum_allowed_gap": maximum_gap, "maximum_observed_gap": max_gap,
        "passed": bool(evaluable and max_gap is not None and max_gap <= maximum_gap),
        "bins": output,
    }


def _evaluation(
    rows: list[dict[str, Any]], probabilities, protocol: dict[str, Any],
) -> dict[str, Any]:
    labels = [row["label"] for row in rows]
    channel_weights = _channel_weights(rows)
    video_weights = np.ones(len(rows), dtype=float)
    result: dict[str, Any] = {
        "coverage": {"eligible": len(rows), "abstained": 0, "rate": 1.0 if rows else 0.0},
        "overall": {
            "channel_balanced": _metric_values(labels, probabilities, channel_weights),
            "video_weighted": _metric_values(labels, probabilities, video_weights),
        },
        "calibration": _calibration_bins(
            rows, labels, probabilities, channel_weights, protocol
        ),
        "by_scope": {},
    }
    for field in ("accepted_category", "confirmed_format", "frozen_age_context"):
        scopes = {}
        for value in sorted({str(row[field]) for row in rows}):
            indexes = [index for index, row in enumerate(rows) if str(row[field]) == value]
            subset = [rows[index] for index in indexes]
            scopes[value] = {
                "channel_balanced": _metric_values(
                    [row["label"] for row in subset],
                    np.asarray(probabilities)[indexes], _channel_weights(subset),
                ),
                "video_weighted": _metric_values(
                    [row["label"] for row in subset],
                    np.asarray(probabilities)[indexes], np.ones(len(subset)),
                ),
            }
        result["by_scope"][field] = scopes
    return result


def paired_channel_bootstrap(
    rows: list[dict[str, Any]], candidate_probabilities, baseline_probabilities,
    *, resamples: int, confidence: float, seed: int,
) -> dict[str, Any]:
    by_channel: defaultdict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        by_channel[str(row["source_channel_id"])].append(index)
    channels = sorted(by_channel)
    if len(channels) < 2:
        return {"status": "not_evaluable", "reason": "insufficient_channels"}
    labels = np.asarray([row["label"] for row in rows], dtype=float)
    candidate = np.asarray(candidate_probabilities, dtype=float)
    baseline = np.asarray(baseline_probabilities, dtype=float)
    differences = np.asarray([
        float(np.mean((candidate[indexes] - labels[indexes]) ** 2)
              - np.mean((baseline[indexes] - labels[indexes]) ** 2))
        for indexes in (by_channel[channel] for channel in channels)
    ])
    if not np.isfinite(differences).all() or np.allclose(differences, differences[0]):
        return {"status": "not_evaluable", "reason": "degenerate_channel_differences",
                "channel_count": len(channels)}
    rng = np.random.default_rng(seed)
    draws = np.empty(resamples, dtype=float)
    duplicate_draws = 0
    for index in range(resamples):
        sampled = rng.integers(0, len(channels), size=len(channels))
        duplicate_draws += int(len(set(sampled.tolist())) < len(channels))
        draws[index] = float(np.mean(differences[sampled]))
    alpha = (1.0 - confidence) / 2.0
    return {
        "status": "evaluated", "metric": "candidate_minus_baseline_brier",
        "point_difference": float(np.mean(differences)),
        "ci_low": float(np.quantile(draws, alpha)),
        "ci_high": float(np.quantile(draws, 1.0 - alpha)),
        "confidence": confidence, "resamples": resamples, "seed": seed,
        "channel_count": len(channels),
        "resampled_channel_count_per_draw": len(channels),
        "draws_with_duplicate_channels": duplicate_draws,
        "duplicates_preserved": True,
    }


def _feature_layout(feature_schema: dict[str, Any], *, include_topics: bool) -> dict[str, Any]:
    base = ["accepted_category", "confirmed_format", "duration_seconds", "frozen_age_context"]
    topics = []
    if include_topics:
        for category in sorted(feature_schema["canonical_topics"]):
            topics.extend(
                f"topic::{category}::{topic}"
                for topic in feature_schema["canonical_topics"][category]
            )
    return {
        "columns": [*base, *topics], "categorical_indexes": [0, 1, 3],
        "numeric_indexes": [2], "topic_indexes": list(range(4, 4 + len(topics))),
        "topic_columns": topics,
    }


def _topic_signature(model_input: dict[str, Any]) -> list[str]:
    topics = model_input.get("canonical_topic_presence") or {}
    return sorted(str(key) for key, value in topics.items() if value is True)


def _training_support(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: defaultdict[tuple[str, str, str, tuple[str, ...]], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        model_input = row["model_input"]
        key = (
            str(model_input["accepted_category"]),
            str(model_input["confirmed_format"]),
            str(model_input["frozen_age_context"]),
            tuple(_topic_signature(model_input)),
        )
        grouped[key].append(row)
    signatures = []
    for key, members in sorted(grouped.items()):
        signatures.append({
            "accepted_category": key[0],
            "confirmed_format": key[1],
            "frozen_age_context": key[2],
            "topic_signature": list(key[3]),
            "video_count": len(members),
            "channel_count": len({str(row["source_channel_id"]) for row in members}),
        })
    return {
        "version": TRAINING_SUPPORT_VERSION,
        "source_partition": "fit",
        "exact_topic_signature_required": True,
        "minimum_signature_videos": 2,
        "minimum_signature_channels": 2,
        "signatures": signatures,
    }


def _matrix(rows: list[dict[str, Any]], layout: dict[str, Any]) -> np.ndarray:
    matrix = []
    for row in rows:
        values = row["model_input"]
        category = values["accepted_category"]
        topics = values["canonical_topic_presence"]
        base = [category, values["confirmed_format"], float(values["duration_seconds"]),
                values["frozen_age_context"]]
        base.extend(
            float(bool(topics.get(column.split("::", 2)[2])))
            if column.split("::", 2)[1] == category else 0.0
            for column in layout["topic_columns"]
        )
        matrix.append(base)
    return np.asarray(matrix, dtype=object)


def _pipeline(layout: dict[str, Any], *, c_value: float, seed: int) -> Pipeline:
    transformers = [
        ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False),
         layout["categorical_indexes"]),
        ("numeric", StandardScaler(), layout["numeric_indexes"]),
    ]
    if layout["topic_indexes"]:
        transformers.append(("topics", "passthrough", layout["topic_indexes"]))
    preprocessor = ColumnTransformer(transformers, remainder="drop")
    return Pipeline([
        ("preprocessor", preprocessor),
        ("classifier", LogisticRegression(
            l1_ratio=0.0, C=float(c_value), solver="lbfgs",
            random_state=int(seed), max_iter=1000,
        )),
    ])


def _split_hash(rows: list[dict[str, Any]]) -> str:
    members = sorted({
        (int(row["dataset_id"]), str(row["source_youtube_id"]),
         str(row["source_channel_id"]), str(row["source_record_sha256"]))
        for row in rows
    })
    return _sha256([list(member) for member in members])


def _feature_record_sha256(feature: dict[str, Any]) -> str:
    return _sha256({
        "schema": feature.get("feature_schema_sha256"),
        "transcript": feature.get("source_transcript_sha256"),
        "model_input": feature.get("model_input"),
        "evidence": feature.get("evidence"),
    })


def load_training_inputs(
    *, manifest_path: Path, features_path: Path, protocol: dict[str, Any],
    data_use_record: dict[str, Any], trusted_root: Path,
) -> dict[str, Any]:
    trusted = trusted_root.resolve()
    manifest_path = manifest_path.resolve()
    features_path = features_path.resolve()
    if trusted not in manifest_path.parents or trusted not in features_path.parents:
        return {"ready": False, "reason_codes": ["artifact_outside_trusted_root"]}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    features = json.loads(features_path.read_text(encoding="utf-8"))
    reasons = []
    validation = validate_protocol(protocol)
    expected_feature_schema = build_feature_schema(protocol)
    rights = data_use_gate(data_use_record, "training")
    if not validation["valid"]:
        reasons.extend(validation["errors"])
    if not rights["allowed"]:
        reasons.extend(rights["reason_codes"])
    if not verify_manifest(manifest):
        reasons.append("manifest_integrity_failed")
    if manifest.get("protocol_sha256") != validation["protocol_sha256"]:
        reasons.append("manifest_protocol_mismatch")
    if manifest.get("feature_schema_sha256") != expected_feature_schema["feature_schema_sha256"]:
        reasons.append("manifest_feature_schema_mismatch")
    if not isinstance(features, list):
        reasons.append("feature_artifact_invalid")
        features = []
    by_feature = {}
    for feature in features:
        try:
            dataset_id = int(feature["dataset_id"])
            if dataset_id in by_feature:
                raise ValueError("duplicate")
            if feature.get("status") != "usable":
                raise ValueError("unusable")
            validate_feature_vector(feature["model_input"])
            if feature.get("schema_version") != FEATURE_SCHEMA_VERSION:
                raise ValueError("version")
            if feature.get("feature_schema_sha256") != manifest.get("feature_schema_sha256"):
                raise ValueError("schema")
            model_input = feature["model_input"]
            category = model_input.get("accepted_category")
            expected_topics = set(expected_feature_schema["canonical_topics"].get(category, []))
            topics = model_input.get("canonical_topic_presence")
            if not isinstance(topics, dict) or set(topics) != expected_topics:
                raise ValueError("topic_order")
            if any(type(value) is not bool for value in topics.values()):
                raise ValueError("topic_type")
            if feature.get("feature_sha256") != _feature_record_sha256(feature):
                raise ValueError("hash")
            by_feature[dataset_id] = feature
        except (KeyError, TypeError, ValueError):
            reasons.append("feature_artifact_invalid")
            break

    records = list(manifest.get("records") or [])
    roles = defaultdict(list)
    identity_roles: defaultdict[str, set[str]] = defaultdict(set)
    rows = []
    test_outcome_open = False
    for record in records:
        role = str(record.get("outcome_role") or "")
        roles[role].append(record)
        for field in ("source_channel_id", "creator_group_key", "source_youtube_id", "transcript_sha256"):
            if record.get(field):
                identity_roles[f"{field}:{record[field]}"].add(role)
        if role == "independent_test" and "views" in (record.get("observation") or {}):
            test_outcome_open = True
        feature = by_feature.get(int(record.get("dataset_id", -1)))
        if feature:
            if record.get("feature_sha256") != feature.get("feature_sha256"):
                reasons.append("manifest_feature_hash_mismatch")
            if record.get("transcript_sha256") != feature.get("source_transcript_sha256"):
                reasons.append("manifest_transcript_hash_mismatch")
            rows.append({**record, "model_input": feature["model_input"]})
    if any(len(value) > 1 for value in identity_roles.values()):
        reasons.append("identity_partition_overlap")
    if test_outcome_open:
        reasons.append("independent_test_outcome_exposed")
    if len(rows) != len(records):
        reasons.append("feature_record_count_mismatch")

    minimums = (protocol.get("split_policy") or {}).get("minimums", {})
    for role in ("fit", "tuning", "calibration", "independent_test"):
        members = roles[role]
        required = minimums.get(role, {})
        if len({item.get("source_youtube_id") for item in members}) < int(required.get("videos", 0)):
            reasons.append(f"{role}_minimum_videos_not_met")
        if len({item.get("source_channel_id") for item in members}) < int(required.get("channels", 0)):
            reasons.append(f"{role}_minimum_channels_not_met")

    development = [row for row in rows if row.get("outcome_role") != "independent_test"]
    benchmarks = fit_benchmarks(development, protocol)
    labels = label_records(development, benchmarks)
    label_by_id = {int(item["dataset_id"]): int(item["label"]) for item in labels["labels"]}
    prepared = []
    for row in development:
        if int(row["dataset_id"]) in label_by_id:
            prepared.append({**row, "label": label_by_id[int(row["dataset_id"])]})
    label_exclusions = labels["exclusions"]
    if label_exclusions:
        reasons.append("development_label_exclusions_present")
    prepared_roles = {role: [row for row in prepared if row["outcome_role"] == role]
                      for role in ("fit", "tuning", "calibration")}
    for role, members in prepared_roles.items():
        if {row["label"] for row in members} != {0, 1}:
            reasons.append(f"{role}_both_labels_required")
    calibration_minimum = int((protocol.get("split_policy") or {}).get(
        "calibration_and_test_minimum_per_label", 0
    ))
    calibration_counts = Counter(row["label"] for row in prepared_roles["calibration"])
    if any(calibration_counts[label] < calibration_minimum for label in (0, 1)):
        reasons.append("calibration_minimum_per_label_not_met")
    split_hashes = {role: _split_hash(members) for role, members in prepared_roles.items()}
    split_hashes["independent_test"] = _split_hash(roles["independent_test"])
    return {
        "ready": not reasons,
        "reason_codes": sorted(set(reasons)),
        "rights": rights, "protocol_validation": validation,
        "manifest": manifest, "manifest_path": str(manifest_path),
        "features_path": str(features_path), "rows": prepared_roles,
        "test_records": roles["independent_test"],
        "benchmarks": benchmarks, "label_report": labels,
        "split_hashes": split_hashes,
        "independent_test_outcome_opened": test_outcome_open,
        "counts": {
            role: {"videos": len(members),
                   "channels": len({row["source_channel_id"] for row in members}),
                   "labels": dict(sorted(Counter(row.get("label") for row in members
                                                  if "label" in row).items()))}
            for role, members in {**prepared_roles, "independent_test": roles["independent_test"]}.items()
        },
    }


def _fit_models(preflight: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    fit_rows = preflight["rows"]["fit"]
    tuning_rows = preflight["rows"]["tuning"]
    calibration_rows = preflight["rows"]["calibration"]
    seed = int((protocol.get("model_policy") or {}).get("random_seed", 261008))
    schema = json.loads(Path(__file__).resolve().parents[2].joinpath(
        "docs/implementation/outcome-feature-schema-v1.json"
    ).read_text(encoding="utf-8"))
    metadata_layout = _feature_layout(schema, include_topics=False)
    topic_layout = _feature_layout(schema, include_topics=True)
    fit_weight = _channel_weights(fit_rows)
    tuning_weight = _channel_weights(tuning_rows)

    fit_y = np.asarray([row["label"] for row in fit_rows], dtype=int)
    constant = ConstantProbabilityModel(float(np.average(fit_y, weights=fit_weight)))
    constant_tuning = _positive_probability(constant, tuning_rows)

    metadata = _pipeline(metadata_layout, c_value=1.0, seed=seed)
    metadata.fit(_matrix(fit_rows, metadata_layout), fit_y, classifier__sample_weight=fit_weight)
    metadata_tuning = _positive_probability(metadata, _matrix(tuning_rows, metadata_layout))

    candidates = []
    c_values = next(item["C"] for item in (protocol.get("model_policy") or {}).get("candidates", [])
                    if item.get("name") == "metadata_topics_logistic_regression")
    for c_value in c_values:
        estimator = _pipeline(topic_layout, c_value=float(c_value), seed=seed)
        estimator.fit(_matrix(fit_rows, topic_layout), fit_y,
                      classifier__sample_weight=fit_weight)
        probabilities = _positive_probability(estimator, _matrix(tuning_rows, topic_layout))
        metrics = _metric_values(
            [row["label"] for row in tuning_rows], probabilities, tuning_weight
        )
        candidates.append({"C": float(c_value), "estimator": estimator,
                           "probabilities": probabilities, "metrics": metrics})
    selected = min(candidates, key=lambda item: (item["metrics"]["brier_score"], item["C"]))

    models = {
        "constant_prior": {"estimator": constant, "layout": None,
                           "tuning_probabilities": constant_tuning},
        "metadata_logistic_regression": {"estimator": metadata, "layout": metadata_layout,
                                         "tuning_probabilities": metadata_tuning},
        "metadata_topics_logistic_regression": {
            "estimator": selected["estimator"], "layout": topic_layout,
            "tuning_probabilities": selected["probabilities"],
            "selected_C": selected["C"],
        },
    }
    for name, item in models.items():
        estimator = item["estimator"]
        layout = item["layout"]
        raw_calibration = _positive_probability(
            estimator,
            calibration_rows if layout is None else _matrix(calibration_rows, layout),
        )
        calibrator = WeightedSigmoidCalibrator(seed).fit(
            raw_calibration, [row["label"] for row in calibration_rows],
            _channel_weights(calibration_rows),
        )
        item.update(
            raw_calibration_probabilities=raw_calibration,
            calibrator=calibrator,
            calibrated_probabilities=calibrator.predict(raw_calibration),
            calibrated_tuning_probabilities=calibrator.predict(
                item["tuning_probabilities"]
            ),
        )
    return {
        "models": models, "candidate_search": [
            {"C": item["C"], "metrics": item["metrics"]} for item in candidates
        ], "selected_C": selected["C"], "feature_schema": schema,
    }


def _coefficient_table(estimator: Pipeline) -> list[dict[str, Any]]:
    preprocessor = estimator.named_steps["preprocessor"]
    classifier = estimator.named_steps["classifier"]
    names = preprocessor.get_feature_names_out().tolist()
    values = classifier.coef_[0].tolist()
    return [
        {"feature": str(name), "coefficient": float(value),
         "interpretation": "association_not_causal_effect"}
        for name, value in sorted(zip(names, values), key=lambda pair: (-abs(pair[1]), pair[0]))
    ]


def _qualification(
    evaluations: dict[str, Any], calibration: dict[str, Any],
    bootstrap: dict[str, Any], protocol: dict[str, Any],
) -> dict[str, Any]:
    policy = protocol.get("qualification") or {}
    candidate = evaluations["metadata_topics_logistic_regression"]["overall"]["channel_balanced"]
    baselines = [
        evaluations[name]["overall"]["channel_balanced"]
        for name in ("constant_prior", "metadata_logistic_regression")
    ]
    margin = float(policy.get("validation_brier_improvement_over_each_baseline", 0.01))
    max_log_regression = float(policy.get("maximum_log_loss_regression_from_best_baseline", 0.02))
    max_category_regression = float(policy.get("maximum_category_brier_regression_from_metadata_baseline", 0.02))
    checks = {
        "brier_improves_over_each_baseline": all(
            baseline["brier_score"] - candidate["brier_score"] >= margin
            for baseline in baselines
        ),
        "log_loss_not_worse_than_best_baseline": (
            candidate["log_loss"] - min(item["log_loss"] for item in baselines)
            <= max_log_regression
        ),
        "calibration_bins_pass": calibration.get("passed") is True,
    }
    candidate_categories = evaluations["metadata_topics_logistic_regression"]["by_scope"]["accepted_category"]
    metadata_categories = evaluations["metadata_logistic_regression"]["by_scope"]["accepted_category"]
    regressions = []
    for category in sorted(set(candidate_categories) & set(metadata_categories)):
        left = candidate_categories[category]["channel_balanced"]
        right = metadata_categories[category]["channel_balanced"]
        if left.get("brier_score") is not None and right.get("brier_score") is not None:
            regressions.append(left["brier_score"] - right["brier_score"])
    checks["no_category_brier_regression"] = bool(regressions) and max(regressions) <= max_category_regression
    passed = all(checks.values())
    return {
        "status": "validation_passed" if passed else "experimental",
        "checks": checks,
        "thresholds": {
            "brier_improvement": margin,
            "maximum_log_loss_regression": max_log_regression,
            "maximum_category_brier_regression": max_category_regression,
        },
        "bootstrap_is_descriptive_until_independent_test": bootstrap,
        "independent_test_required_for_qualification": True,
        "qualified": False,
    }


def train_and_validate_outcome_model(
    *,
    manifest_path: Path,
    features_path: Path,
    protocol_path: Path,
    data_use_path: Path,
    output_dir: Path,
    trusted_phase2_root: Path,
    source_kind: str = "real",
) -> dict[str, Any]:
    started = time.monotonic()
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    data_use = json.loads(data_use_path.read_text(encoding="utf-8"))
    preflight = load_training_inputs(
        manifest_path=manifest_path, features_path=features_path,
        protocol=protocol, data_use_record=data_use,
        trusted_root=trusted_phase2_root,
    )
    if not preflight["ready"]:
        return {"status": "blocked", "preflight": preflight,
                "artifact_created": False, "independent_test_opened": False}
    if output_dir.exists():
        raise ValueError("Outcome model artifact directory already exists")
    output_dir.mkdir(parents=True)

    fit_result = _fit_models(preflight, protocol)
    models = fit_result["models"]
    tuning_rows = preflight["rows"]["tuning"]
    calibration_rows = preflight["rows"]["calibration"]
    tuning_evaluations = {
        name: {
            "before": _evaluation(tuning_rows, item["tuning_probabilities"], protocol),
            "after": _evaluation(
                tuning_rows, item["calibrated_tuning_probabilities"], protocol
            ),
            "interpretation": "tuning_selected_candidate_not_independent_test",
        }
        for name, item in models.items()
    }
    calibration_evaluations = {
        name: {
            "before": _evaluation(calibration_rows, item["raw_calibration_probabilities"], protocol),
            "after": _evaluation(calibration_rows, item["calibrated_probabilities"], protocol),
            "interpretation": "calibrator_fit_partition_diagnostic_not_independent_test",
        }
        for name, item in models.items()
    }
    bootstrap_policy = (protocol.get("evaluation") or {}).get("bootstrap") or {}
    bootstrap = paired_channel_bootstrap(
        tuning_rows,
        models["metadata_topics_logistic_regression"]["tuning_probabilities"],
        models["metadata_logistic_regression"]["tuning_probabilities"],
        resamples=int(bootstrap_policy.get("resamples", 2000)),
        confidence=float(bootstrap_policy.get("confidence", 0.95)),
        seed=int(bootstrap_policy.get("seed", 261008)),
    )
    qualification = _qualification(
        {name: values["before"] for name, values in tuning_evaluations.items()},
        calibration_evaluations["metadata_topics_logistic_regression"]["after"]["calibration"],
        bootstrap, protocol,
    )
    public_status = (
        f"fixture_{qualification['status']}" if source_kind == "synthetic_fixture"
        else qualification["status"]
    )
    coefficients = {
        name: _coefficient_table(item["estimator"])
        for name, item in models.items() if item["layout"] is not None
    }
    protocol_validation = validate_protocol(protocol)
    versions = {
        "python": platform.python_version(), "numpy": np.__version__,
        "scikit_learn": sklearn.__version__, "joblib": joblib.__version__,
    }
    payload = {
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "target_version": (protocol.get("target") or {}).get("version"),
        "protocol_sha256": protocol_validation["protocol_sha256"],
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_schema_sha256": preflight["manifest"]["feature_schema_sha256"],
        "manifest_sha256": preflight["manifest"]["manifest_sha256"],
        "split_hashes": preflight["split_hashes"],
        "observation_cutoff": preflight["manifest"]["cutoff_utc"],
        "benchmarks": preflight["benchmarks"],
        "label_report": preflight["label_report"],
        "support_policy": protocol.get("context_support"),
        "calibration_version": CALIBRATION_VERSION,
        "random_seed": int((protocol.get("model_policy") or {}).get("random_seed", 261008)),
        "feature_layout": fit_result["feature_schema"],
        "training_support": _training_support(preflight["rows"]["fit"]),
        "category_vocabulary": sorted({row["accepted_category"] for row in preflight["rows"]["fit"]}),
        "format_vocabulary": sorted({row["confirmed_format"] for row in preflight["rows"]["fit"]}),
        "models": {
            name: {"estimator": item["estimator"], "calibrator": item["calibrator"],
                   "layout": item["layout"], "selected_C": item.get("selected_C")}
            for name, item in models.items()
        },
        "selected_model": "metadata_topics_logistic_regression",
        "qualification": qualification,
        "evaluated_scopes": ["overall", "category", "confirmed_format", "frozen_age_context"],
        "intended_population": (protocol.get("sampling") or {}).get("probability_population"),
        "limitations": [
            "observational_association_not_causal_uplift",
            "not_a_seven_day_forecast", "independent_test_not_opened",
            "convenience_reference_frame_not_all_youtube",
        ],
        "library_versions": versions, "source_kind": source_kind,
        "production_eligible": False,
    }
    artifact_path = output_dir / "model.joblib"
    joblib.dump(payload, artifact_path)
    artifact_sha = file_sha256(artifact_path)
    elapsed = time.monotonic() - started
    report = {
        "schema_version": TRAINING_REPORT_VERSION,
        "status": public_status, "source_kind": source_kind,
        "artifact_sha256": artifact_sha,
        "artifact_path": str(artifact_path),
        "target_version": payload["target_version"],
        "protocol_sha256": payload["protocol_sha256"],
        "feature_schema_sha256": payload["feature_schema_sha256"],
        "manifest_sha256": payload["manifest_sha256"],
        "split_hashes": preflight["split_hashes"],
        "partition_counts": preflight["counts"],
        "support_policy": protocol.get("context_support"),
        "label_exclusions": preflight["label_report"].get("exclusions", []),
        "candidate_search": fit_result["candidate_search"],
        "selected_C": fit_result["selected_C"],
        "tuning_metrics": tuning_evaluations,
        "calibration_metrics": calibration_evaluations,
        "paired_channel_bootstrap": bootstrap,
        "qualification": qualification,
        "independent_test_opened": False,
        "independent_test_metrics": None,
        "production_eligible": False,
        "active_model_changed": False,
        "elapsed_seconds": elapsed,
        "resource_budget_seconds": int((protocol.get("resources") or {}).get(
            "training_wall_clock_minutes", 30
        )) * 60,
        "resource_budget_passed": elapsed <= int((protocol.get("resources") or {}).get(
            "training_wall_clock_minutes", 30
        )) * 60,
        "library_versions": versions,
    }
    (output_dir / "validation-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    (output_dir / "coefficients.json").write_text(
        json.dumps(coefficients, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    plot_data = {
        name: values["after"]["calibration"]
        for name, values in calibration_evaluations.items()
    }
    (output_dir / "calibration-plot-data.json").write_text(
        json.dumps(plot_data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    integrity = {
        "model.joblib": artifact_sha,
        "validation-report.json": file_sha256(output_dir / "validation-report.json"),
        "coefficients.json": file_sha256(output_dir / "coefficients.json"),
        "calibration-plot-data.json": file_sha256(output_dir / "calibration-plot-data.json"),
    }
    (output_dir / "integrity.json").write_text(
        json.dumps(integrity, indent=2, sort_keys=True), encoding="utf-8"
    )
    model_card = f"""# Outcome model card

- Status: `{public_status}`
- Source: `{source_kind}`
- Target: `{payload['target_version']}`
- Selected model: `metadata_topics_logistic_regression`, C=`{fit_result['selected_C']}`
- Independent Test opened: **false**
- Production eligible: **false**

`x` คือหัวข้อที่ตรวจพบร่วมกับหมวด รูปแบบ ความยาว และบริบทอายุคลิป
Logistic Regression คำนวณ `score = intercept + sum(weight * feature)` แล้วแปลงด้วย sigmoid
เป็นค่าระหว่าง 0 ถึง 1 ส่วน Calibration ใช้ข้อมูลคนละช่องกับ Fit เพื่อปรับความสอดคล้อง
ของค่าประเมินกับสัดส่วนที่พบจริง

`y` มาจากยอดวิว ณ Observation เทียบ weighted median ที่เรียนจาก Fit cell เท่านั้น
ไม่ใช่ Label ที่ AI ตั้งเอง ไม่ใช่ผลเพิ่มยอดวิว และไม่ใช่การรับประกันว่าการเพิ่มหัวข้อจะทำให้คลิปดีขึ้น

การทดลองเปิด/ปิด Topic feature เป็น hypothetical model-score difference เท่านั้น ไม่ใช่ causal uplift
"""
    (output_dir / "model-card.md").write_text(model_card, encoding="utf-8")
    integrity["model-card.md"] = file_sha256(output_dir / "model-card.md")
    (output_dir / "integrity.json").write_text(
        json.dumps(integrity, indent=2, sort_keys=True), encoding="utf-8"
    )
    return {**report, "artifact_created": True, "output_dir": str(output_dir)}


def load_outcome_artifact(
    artifact_path: Path, *, trusted_root: Path, expected_sha256: str,
    expected_protocol_sha256: str, expected_feature_schema_sha256: str,
) -> dict[str, Any]:
    path = artifact_path.resolve()
    trusted = trusted_root.resolve()
    if trusted not in path.parents:
        raise ValueError("Artifact is outside trusted local storage")
    if file_sha256(path) != expected_sha256:
        raise ValueError("Outcome artifact checksum mismatch")
    payload = joblib.load(path)
    if not isinstance(payload, dict) or payload.get("artifact_schema_version") != ARTIFACT_SCHEMA_VERSION:
        raise ValueError("Outcome artifact schema mismatch")
    if payload.get("protocol_sha256") != expected_protocol_sha256:
        raise ValueError("Outcome artifact protocol mismatch")
    if payload.get("feature_schema_sha256") != expected_feature_schema_sha256:
        raise ValueError("Outcome artifact feature schema mismatch")
    candidate = (payload.get("models") or {}).get("metadata_topics_logistic_regression") or {}
    if not isinstance(candidate.get("layout"), dict) or not candidate["layout"].get("columns"):
        raise ValueError("Outcome artifact feature order missing")
    embedded_schema = payload.get("feature_layout")
    if not isinstance(embedded_schema, dict):
        raise ValueError("Outcome artifact feature schema missing")
    expected_columns = _feature_layout(embedded_schema, include_topics=True)["columns"]
    if candidate["layout"].get("columns") != expected_columns:
        raise ValueError("Outcome artifact feature order mismatch")
    return payload


def activation_validation(model_record: dict[str, Any], data_use_record: dict[str, Any]) -> dict[str, Any]:
    reasons = []
    rights = data_use_gate(data_use_record, "serving")
    reasons.extend(rights["reason_codes"])
    if model_record.get("status") != "qualified":
        reasons.append("model_not_independent_test_qualified")
    if model_record.get("independent_test_passed") is not True:
        reasons.append("independent_test_not_passed")
    if model_record.get("production_eligible") is not True:
        reasons.append("production_eligibility_false")
    return {"can_activate": not reasons, "reason_codes": sorted(set(reasons)),
            "force_override_supported": False}
