"""Frozen, one-shot independent evaluation. Never fit a model or activate one."""
from __future__ import annotations

import copy
import json
import sqlite3
from contextlib import closing
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import joblib
import numpy as np

from app.database.models import DatasetContent, OutcomeModel, OutcomeModelMetric, ReferenceVideoStatistic
from app.services.dataset_eligibility import reference_transcript_rows
from app.services.outcome_dataset import (
    _as_utc, _record_core, _sha256, identity_keys, label_records,
)
from app.services.outcome_independence import sealed_holdout_check
from app.services.outcome_prediction_readiness import data_use_gate, scan_prior_artifact_use
from app.services.outcome_support import CONTEXT_FIELDS, QUALIFIED_SCOPES_VERSION, training_support
from app.services.outcome_training import (
    CALIBRATION_VERSION, _evaluation, _matrix, _positive_probability, _qualification,
    file_sha256, load_outcome_artifact, load_training_inputs, paired_channel_bootstrap,
)
from app.services.persistence import log_system_event


PLAN_VERSION = "outcome-independent-evaluation-freeze-v1"
REPORT_VERSION = "outcome-independent-evaluation-report-v2"
MODEL_NAMES = ("constant_prior", "metadata_logistic_regression", "metadata_topics_logistic_regression")


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_new(path, payload):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False, default=str)


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def registered_evaluation_report(db, *, model_id, freeze, trusted_root):
    model = db.get(OutcomeModel, model_id)
    if model is None:
        raise ValueError("Evaluated model missing")
    report = json.loads(model.metrics_json or "{}").get("independent_test")
    if (not isinstance(report, dict) or report.get("schema_version") != REPORT_VERSION
            or report.get("freeze_sha256") != freeze.get("freeze_sha256")):
        raise ValueError("Registered independent report does not match freeze")
    artifact = load_outcome_artifact(
        Path(model.artifact_path), trusted_root=Path(trusted_root), expected_sha256=model.artifact_sha256,
        expected_protocol_sha256=model.protocol_sha256, expected_feature_schema_sha256=model.feature_schema_sha256,
    )
    if artifact.get("independent_evaluation_sha256") != _sha256(report):
        raise ValueError("Registered independent report integrity mismatch")
    return report


def _inputs(db, *, model_id, manifest_path, features_path, protocol_path, data_use_path,
            trusted_root, phase2_root, repo_root, allow_synthetic_fixture=False):
    model = db.get(OutcomeModel, model_id)
    if model is None or model.is_active or model.independent_test_passed:
        raise ValueError("Candidate missing, active, or already independently evaluated")
    if model.status not in {"validation_passed", "fixture_validation_passed"}:
        raise ValueError("Candidate has not passed Validation")
    synthetic = model.source_kind == "synthetic_fixture"
    if synthetic and not allow_synthetic_fixture:
        raise ValueError("Synthetic candidate cannot be evaluated as a real model")
    protocol, rights = _read(protocol_path), _read(data_use_path)
    for purpose in ("training", "serving"):
        gate = data_use_gate(rights, purpose, allow_synthetic_fixture=synthetic and allow_synthetic_fixture)
        if not gate["allowed"]:
            raise ValueError("Data use blocked: " + ", ".join(gate["reason_codes"]))
    prepared = load_training_inputs(
        manifest_path=Path(manifest_path), features_path=Path(features_path), protocol=protocol,
        data_use_record=rights, trusted_root=Path(phase2_root),
        allow_synthetic_fixture=synthetic and allow_synthetic_fixture,
    )
    if not prepared["ready"]:
        raise ValueError("Frozen input preflight failed: " + ", ".join(prepared["reason_codes"]))
    artifact = load_outcome_artifact(
        Path(model.artifact_path), trusted_root=Path(trusted_root), expected_sha256=model.artifact_sha256,
        expected_protocol_sha256=model.protocol_sha256, expected_feature_schema_sha256=model.feature_schema_sha256,
    )
    if artifact.get("source_kind") != model.source_kind:
        raise ValueError("Candidate source-kind mismatch")
    for field, expected in (
        ("manifest_sha256", prepared["manifest"]["manifest_sha256"]),
        ("split_hashes", prepared["split_hashes"]),
        ("protocol_sha256", prepared["protocol_validation"]["protocol_sha256"]),
        ("calibration_version", CALIBRATION_VERSION),
    ):
        registered = json.loads(model.split_hashes_json) if field == "split_hashes" else getattr(model, field)
        if artifact.get(field) != expected or registered != expected:
            raise ValueError(f"Candidate {field} mismatch")
    report_path = Path(model.artifact_path).parent / "validation-report.json"
    report = _read(report_path)
    if (report.get("artifact_sha256") != model.artifact_sha256
            or (report.get("qualification") or {}).get("status") != "validation_passed"
            or artifact.get("qualification", {}).get("status") != "validation_passed"
            or not artifact.get("qualification", {}).get("checks")
            or not all(value is True for value in artifact["qualification"]["checks"].values())):
        raise ValueError("Validation report is not the frozen candidate decision")
    if artifact.get("benchmarks") != prepared["benchmarks"]:
        raise ValueError("Frozen Fit benchmark mismatch")
    contexts = artifact.get("frozen_evaluation_contexts") or []
    expected_contexts = [cell["cell"] for cell in prepared["benchmarks"]["cells"] if cell["status"] == "supported"]
    if not contexts or contexts != expected_contexts:
        raise ValueError("Evaluation context list was not frozen from Fit")
    tests = prepared["test_records"]
    identity_hashes = {_sha256(key) for row in tests for key in identity_keys(row)}
    for previous in db.query(OutcomeModel).all():
        used = (json.loads(previous.metrics_json or "{}").get("independent_test") or {})
        access = used.get("test_access") or {}
        if used.get("independent_test_opened") and (
            identity_hashes.intersection(access.get("identity_sha256s") or [])
            or set(access.get("dataset_ids") or []).intersection(row["dataset_id"] for row in tests)
        ):
            raise ValueError("Independent Test was already accessed by a registered model")
    if synthetic:
        independence = sealed_holdout_check(prepared["manifest"])
    else:
        rows = db.query(DatasetContent).filter(DatasetContent.dataset_id.in_([row["dataset_id"] for row in tests])).all()
        independence = sealed_holdout_check(
            prepared["manifest"], current_rows={row.dataset_id: row for row in rows},
            prior_use=scan_prior_artifact_use(Path(repo_root)), reference_rows=reference_transcript_rows(db),
        )
    if not independence["valid"]:
        raise ValueError("Holdout independence failed: " + ", ".join(independence["reason_codes"]))
    hashes = {
        "candidate_artifact": model.artifact_sha256, "validation_report": file_sha256(report_path),
        "manifest": file_sha256(manifest_path), "features": file_sha256(features_path),
        "protocol": file_sha256(protocol_path), "data_use": file_sha256(data_use_path),
        "benchmark": _sha256(artifact["benchmarks"]), "context_selection": _sha256(contexts),
        "training_support": _sha256(artifact["training_support"]),
        "feature_schema": model.feature_schema_sha256,
    }
    return model, artifact, prepared, protocol, hashes


def freeze_candidate(db, *, output_path, actor, **inputs):
    if not str(actor).strip():
        raise ValueError("Freeze actor is required")
    model, artifact, prepared, protocol, hashes = _inputs(db, **inputs)
    plan = {
        "schema_version": PLAN_VERSION, "frozen_at": _now(), "frozen_by": actor,
        "model_id": model.model_id, "model_version": model.model_version, "source_kind": model.source_kind,
        "candidate": {"status": "frozen_real_candidate" if model.source_kind == "real" else "frozen_synthetic_candidate",
                      "model_id": model.model_id, "model_version": model.model_version},
        "protocol_sha256": model.protocol_sha256, "manifest_sha256": model.manifest_sha256,
        "hashes": hashes, "split_hashes": prepared["split_hashes"],
        "test_dataset_ids": sorted(row["dataset_id"] for row in prepared["test_records"]),
        "contexts": artifact["frozen_evaluation_contexts"],
        "categories": protocol["sampling"]["target_categories"],
        "example_selection": "lowest_dataset_id_per_correct_incorrect_abstained_first_three",
        "test_opened": False,
    }
    plan["freeze_sha256"] = _sha256(plan)
    _write_new(output_path, plan)
    return plan


def _claim_test(ledger_root, *, plan, records, actor, run_id):
    root = Path(ledger_root)
    root.mkdir(parents=True, exist_ok=True)
    keys = {key for row in records for key in identity_keys(row)}
    keys.add(f"candidate:{plan['hashes']['candidate_artifact']}")
    with closing(sqlite3.connect(root / "access.sqlite3", timeout=30)) as ledger:
        ledger.execute("CREATE TABLE IF NOT EXISTS test_access (identity_key TEXT PRIMARY KEY, run_id TEXT NOT NULL, actor TEXT NOT NULL, opened_at TEXT NOT NULL, freeze_sha256 TEXT NOT NULL)")
        try:
            ledger.execute("BEGIN IMMEDIATE")
            ledger.executemany("INSERT INTO test_access VALUES (?, ?, ?, ?, ?)", [
                (_sha256(key), run_id, actor, _now(), plan["freeze_sha256"]) for key in sorted(keys)
            ])
            ledger.commit()
        except sqlite3.IntegrityError as exc:
            ledger.rollback()
            raise ValueError("Independent Test or candidate already accessed; reuse is forbidden") from exc


def _database_outcomes(db, records):
    output = []
    for record in records:
        pinned = record["observation"]
        row = db.get(ReferenceVideoStatistic, pinned["observation_id"])
        if (row is None or row.dataset_id != record["dataset_id"] or row.video_id != record["source_youtube_id"]
                or row.status not in {"complete", "partial"} or row.views is None or row.views < 0
                or _as_utc(row.observed_at) != _as_utc(pinned["observed_at"])
                or row.view_metric_version != pinned["view_metric_version"]):
            raise ValueError("Pinned Test observation is missing or changed")
        output.append(dict(record, observation=dict(pinned, views=int(row.views))))
    return output


def evaluate_predictions(rows, *, artifact, protocol, contexts):
    """Pure evaluation using frozen estimators/calibrators and support only."""
    support = artifact["training_support"]
    probabilities = {}
    for name in MODEL_NAMES:
        model = artifact["models"][name]
        raw = _positive_probability(model["estimator"], rows if model["layout"] is None else _matrix(rows, model["layout"]))
        probabilities[name] = model["calibrator"].predict(raw)
    metrics = {name: _evaluation(rows, values, protocol, support=support) for name, values in probabilities.items()}
    indexes = [index for index, row in enumerate(rows) if not training_support(artifact, row["model_input"])[1]]
    supported = [rows[index] for index in indexes]
    policy = protocol["evaluation"]["bootstrap"]
    intervals = {name: paired_channel_bootstrap(
        supported, probabilities[MODEL_NAMES[-1]][indexes], probabilities[name][indexes],
        resamples=policy["resamples"], confidence=policy["confidence"], seed=policy["seed"],
    ) for name in MODEL_NAMES[:2]}
    decision = _qualification(metrics, metrics[MODEL_NAMES[-1]]["calibration"], intervals, protocol)
    checks = dict(decision["checks"])
    checks["paired_test_ci_better_than_each_baseline"] = all(
        value.get("status") == "evaluated" and value.get("ci_high", 1) < 0 for value in intervals.values())
    minima = protocol["split_policy"]
    counts = Counter(row["label"] for row in supported)
    minimum = minima["minimums"]["independent_test"]
    checks["supported_test_minimums"] = (len(supported) >= minimum["videos"] and
        len({row["source_channel_id"] for row in supported}) >= minimum["channels"] and
        all(counts[label] >= minima["calibration_and_test_minimum_per_label"] for label in (0, 1)))
    per_category = minima["minimum_test_per_qualified_category"]
    category_results = {}
    for category in protocol["sampling"]["target_categories"]:
        members = [row for row in supported if row["accepted_category"] == category]
        valid = (len(members) >= per_category["videos"] and
                 len({row["source_channel_id"] for row in members}) >= per_category["channels"] and
                 {row["label"] for row in members} == {0, 1})
        category_results[category] = {"supported": valid, "videos": len(members),
                                      "channels": len({row["source_channel_id"] for row in members})}
    checks["frozen_category_minimums"] = all(value["supported"] for value in category_results.values())
    scope_results = []
    assessed_indexes = set(indexes)
    for context in contexts:
        local = [index for index in range(len(rows)) if [rows[index][key] for key in CONTEXT_FIELDS[:3]] +
                 [rows[index]["observation"]["view_metric_version"]] == context]
        members = [rows[index] for index in local]
        assessed_members = [rows[index] for index in local if index in assessed_indexes]
        supported_context = (len(assessed_members) >= per_category["videos"] and
            len({row["source_channel_id"] for row in assessed_members}) >= per_category["channels"] and
            {row["label"] for row in assessed_members} == {0, 1})
        context_metrics = {name: _evaluation(members, values[local], protocol, support=support)
                           for name, values in probabilities.items()}
        candidate_metric = context_metrics[MODEL_NAMES[-1]]["overall"]["channel_balanced"]
        baseline_metric = context_metrics[MODEL_NAMES[1]]["overall"]["channel_balanced"]
        regression_passed = (candidate_metric.get("status") == "evaluated"
            and baseline_metric.get("status") == "evaluated"
            and candidate_metric["brier_score"] - baseline_metric["brier_score"] <=
            protocol["qualification"]["maximum_category_brier_regression_from_metadata_baseline"])
        scope_results.append(dict(zip(CONTEXT_FIELDS, context), qualified=False,
                                  support_passed=supported_context, no_regression=regression_passed,
                                  video_count=len(assessed_members), eligible_count=len(members), metrics=context_metrics))
    checks["frozen_contexts_supported"] = bool(scope_results) and all(
        item["support_passed"] and item["no_regression"] for item in scope_results)
    passed = all(checks.values())
    for scope in scope_results:
        scope["qualified"] = passed and scope["support_passed"]
    examples = {key: [] for key in ("correct", "incorrect", "abstained")}
    for index in sorted(range(len(rows)), key=lambda index: rows[index]["dataset_id"]):
        kind = "abstained" if index not in assessed_indexes else (
            "correct" if int(probabilities[MODEL_NAMES[-1]][index] >= 0.5) == rows[index]["label"] else "incorrect")
        if len(examples[kind]) < 3:
            examples[kind].append({"dataset_id": rows[index]["dataset_id"], "label": rows[index]["label"],
                                   "probability": float(probabilities[MODEL_NAMES[-1]][index]) if index in assessed_indexes else None})
    return {"metrics": metrics, "bootstrap": intervals, "checks": checks, "passed": passed,
            "categories": category_results, "examples": examples,
            "evaluated_scopes": {"schema_version": QUALIFIED_SCOPES_VERSION, "contexts": scope_results}}


def evaluate_candidate(db, *, freeze_path, output_dir, ledger_root, actor, confirm_open_test,
                       outcome_loader=None, **inputs):
    if not confirm_open_test or not str(actor).strip():
        raise ValueError("Explicit confirmation and actor are required before opening Test")
    plan = _read(freeze_path)
    if (plan.get("schema_version") != PLAN_VERSION or plan.get("freeze_sha256") != _sha256(
            {key: value for key, value in plan.items() if key != "freeze_sha256"})):
        raise ValueError("Candidate freeze integrity failed")
    model, artifact, prepared, protocol, hashes = _inputs(db, **inputs)
    if (plan.get("model_id") != model.model_id or plan.get("hashes") != hashes
            or plan.get("split_hashes") != prepared["split_hashes"]
            or plan.get("contexts") != artifact["frozen_evaluation_contexts"]
            or plan.get("test_dataset_ids") != sorted(row["dataset_id"] for row in prepared["test_records"])):
        raise ValueError("Candidate or input changed after freeze")
    if outcome_loader is not None and not (inputs.get("allow_synthetic_fixture") and model.source_kind == "synthetic_fixture"):
        raise ValueError("A custom outcome loader is permitted only for isolated synthetic tests")
    output = Path(output_dir).resolve()
    if Path(inputs["trusted_root"]).resolve() not in output.parents:
        raise ValueError("Evaluation output must be inside trusted model storage")
    output.mkdir(parents=True, exist_ok=False)
    run_id = str(uuid4())
    records = prepared["test_records"]
    _claim_test(ledger_root, plan=plan, records=records, actor=actor, run_id=run_id)
    access = {"run_id": run_id, "opened_at": _now(), "actor": actor, "freeze_sha256": plan["freeze_sha256"],
              "dataset_ids": plan["test_dataset_ids"], "status": "opened", "outcomes_read": False,
              "identity_sha256s": sorted({_sha256(key) for row in records for key in identity_keys(row)})}
    _write_new(output / "test-access.json", access)
    try:
        opened = outcome_loader(records) if outcome_loader else _database_outcomes(db, records)
        if sorted(row["dataset_id"] for row in opened) != plan["test_dataset_ids"]:
            raise ValueError("Test sample IDs differ from the frozen plan")
        by_id = {row["dataset_id"]: row for row in records}
        for row in opened:
            if _sha256(_record_core(row)) != by_id[row["dataset_id"]]["source_record_sha256"]:
                raise ValueError("Test observation/source commitment changed")
        labels = label_records(opened, artifact["benchmarks"], unlock_independent_test=True)
        if labels["exclusions"]:
            raise ValueError("Frozen Test labels not assessable: " + json.dumps(labels["exclusions"]))
        features = {row["dataset_id"]: row["model_input"] for row in _read(inputs["features_path"])}
        by_label = {row["dataset_id"]: row["label"] for row in labels["labels"]}
        rows = [dict(row, label=by_label[row["dataset_id"]], model_input=features[row["dataset_id"]]) for row in opened]
        evaluation = evaluate_predictions(rows, artifact=artifact, protocol=protocol, contexts=plan["contexts"])
        synthetic = model.source_kind == "synthetic_fixture"
        status = "qualified" if evaluation["passed"] else "experimental"
        report = {
            "schema_version": REPORT_VERSION, "status": status, "generated_at": _now(),
            "source_kind": model.source_kind, "model_id": model.model_id, "run_id": run_id,
            "freeze_sha256": plan["freeze_sha256"], "frozen_hashes": hashes,
            "independent_test_opened": True, "test_access": dict(access, status="evaluated", outcomes_read=True),
            "evaluation": evaluation, "production_eligible": evaluation["passed"] and not synthetic,
            "active_model_changed": False, "causal_claim": False,
            "limitations": ["observational_reference_association_not_causal_uplift", "convenience_sample_not_all_youtube"],
        }
        evaluated_artifact = copy.deepcopy(artifact)
        evaluated_artifact.update(
            qualification={"status": status, "qualified": evaluation["passed"], "independent_test_run_id": run_id},
            production_eligible=report["production_eligible"], evaluated_scopes=evaluation["evaluated_scopes"],
            independent_evaluation_sha256=_sha256(report),
        )
        evaluated_artifact["limitations"] = report["limitations"]
        artifact_path = output / "model.joblib"
        joblib.dump(evaluated_artifact, artifact_path)
        _write_new(output / "independent-evaluation-report.json", report)
        _write_new(output / "integrity.json", {"model.joblib": file_sha256(artifact_path),
                   "independent-evaluation-report.json": file_sha256(output / "independent-evaluation-report.json"),
                   "test-access.json": file_sha256(output / "test-access.json")})
        model.status = f"fixture_{status}" if synthetic else status
        model.independent_test_passed = evaluation["passed"] and not synthetic
        model.production_eligible = report["production_eligible"]
        model.evaluated_scopes_json = json.dumps(evaluation["evaluated_scopes"])
        model.artifact_path, model.artifact_sha256 = str(artifact_path), file_sha256(artifact_path)
        metrics = json.loads(model.metrics_json or "{}")
        metrics["independent_test"] = report
        model.metrics_json = json.dumps(metrics)
        for weighting, values in evaluation["metrics"][MODEL_NAMES[-1]]["overall"].items():
            for name in ("brier_score", "log_loss", "roc_auc", "pr_auc"):
                db.add(OutcomeModelMetric(
                    model_id=model.model_id, dataset_split="independent_test", phase="after",
                    scope_type="overall", scope_value="__overall__", weighting=weighting,
                    metric_name=name, metric_value=values.get(name), metric_status=values["status"],
                    sample_size=values.get("sample_count", 0), details=json.dumps({"run_id": run_id}),
                ))
        log_system_event(db, user_id=None, action="outcome_independent_evaluation", status="success",
                         detail=json.dumps({"model_id": model.model_id, "run_id": run_id, "actor": actor,
                                            "decision": status, "active_model_changed": False}))
        db.commit()
        return report
    except Exception as exc:
        db.rollback()
        error = {"run_id": run_id, "error": str(exc), "independent_test_opened": True,
                 "test_access_claimed": True, "test_access": access, "reuse_forbidden": True, "failed_at": _now()}
        _write_new(output / "evaluation-error.json", error)
        failed = db.get(OutcomeModel, inputs["model_id"])
        if failed is not None:
            failed.status = "evaluation_failed"
            failed.independent_test_passed = failed.production_eligible = False
            metrics = json.loads(failed.metrics_json or "{}")
            metrics["independent_test"] = error
            failed.metrics_json = json.dumps(metrics)
            db.commit()
        raise
