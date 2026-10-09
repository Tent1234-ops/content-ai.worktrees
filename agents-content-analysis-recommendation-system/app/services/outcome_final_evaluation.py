"""Fail-closed Outcome Prediction Phase 6 release evaluation reports."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PHASE6_SCHEMA_VERSION = "outcome-final-evaluation-v1"
UTILITY_SCHEMA_VERSION = "outcome-prediction-utility-study-v1"
TARGET_CATEGORIES = ("phone", "camera", "laptop")
UTILITY_FIELDS = (
    "relevance",
    "non_redundancy",
    "evidence_correctness",
    "clarity",
    "actionability",
)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=str,
    )


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_utility_protocol(protocol: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if protocol.get("schema_version") != UTILITY_SCHEMA_VERSION:
        errors.append("utility_schema_version_invalid")
    if protocol.get("minimum_real_reviewers") != 3:
        errors.append("minimum_real_reviewers_must_equal_three")
    in_scope = ((protocol.get("case_manifest") or {}).get("in_scope") or {})
    for category in TARGET_CATEGORIES:
        if in_scope.get(category) != 4:
            errors.append(f"in_scope_{category}_must_equal_four")
    if (protocol.get("case_manifest") or {}).get("refusal_or_out_of_scope") != 3:
        errors.append("refusal_case_count_must_equal_three")
    fields = [item.get("field") for item in protocol.get("questions_th") or []]
    if fields != list(UTILITY_FIELDS):
        errors.append("utility_question_fields_invalid")
    criteria = protocol.get("pass_criteria_frozen_before_ratings") or {}
    expected_criteria = {
        "median_clarity_at_least": 4,
        "median_actionability_at_least": 4,
        "correct_non_guarantee_interpretation_ratio_at_least": 0.8,
        "fabricated_evidence_count": 0,
    }
    for key, expected in expected_criteria.items():
        if criteria.get(key) != expected:
            errors.append(f"{key}_invalid")
    if (protocol.get("interpretation_check") or {}).get("correct_answer") is not False:
        errors.append("interpretation_check_must_reject_guarantee")
    if (protocol.get("variant_c_gate") or {}).get("requires_prediction_qualified") is not True:
        errors.append("variant_c_must_require_qualified_prediction")
    if (protocol.get("variant_c_gate") or {}).get("synthetic_fixture_is_forbidden") is not True:
        errors.append("variant_c_must_forbid_synthetic_fixture")
    return {
        "valid": not errors,
        "errors": errors,
        "protocol_sha256": sha256_json(protocol),
    }


def _readiness_gate(
    readiness: dict[str, Any],
    phase5_freeze: dict[str, Any],
    outcome_overview: dict[str, Any],
) -> dict[str, Any]:
    dataset = readiness.get("dataset") or {}
    data_use = readiness.get("data_use") or {}
    holdout = readiness.get("holdout") or {}
    candidate = phase5_freeze.get("candidate") or {}
    models = outcome_overview.get("models") or {}
    if isinstance(models, list):
        model_count = len(models)
    else:
        model_count = int(models.get("total") or 0)
    active_model = outcome_overview.get("active_model")

    checks = [
        {
            "gate": "protocol_valid",
            "passed": bool((readiness.get("protocol") or {}).get("valid")),
            "observed": (readiness.get("protocol") or {}).get("valid"),
        },
        {
            "gate": "database_unchanged_during_readiness_audit",
            "passed": readiness.get("database_unchanged") is True,
            "observed": readiness.get("database_unchanged"),
        },
        {
            "gate": "frozen_protocol_hash_matches_readiness",
            "passed": bool(phase5_freeze.get("protocol_sha256"))
            and phase5_freeze.get("protocol_sha256")
            == (readiness.get("protocol") or {}).get("protocol_sha256"),
            "observed": {
                "freeze": phase5_freeze.get("protocol_sha256"),
                "readiness": (readiness.get("protocol") or {}).get("protocol_sha256"),
            },
        },
        {
            "gate": "training_rights_confirmed",
            "passed": bool((data_use.get("training") or {}).get("allowed")),
            "observed": (data_use.get("training") or {}).get("allowed"),
        },
        {
            "gate": "serving_rights_confirmed",
            "passed": bool((data_use.get("serving") or {}).get("allowed")),
            "observed": (data_use.get("serving") or {}).get("allowed"),
        },
        {
            "gate": "structurally_ready_rows_available",
            "passed": int(dataset.get("structurally_ready_without_rights_or_outcome_split") or 0) > 0,
            "observed": int(dataset.get("structurally_ready_without_rights_or_outcome_split") or 0),
        },
        {
            "gate": "training_allowed_rows_available",
            "passed": int(dataset.get("training_allowed_rows") or 0) > 0,
            "observed": int(dataset.get("training_allowed_rows") or 0),
        },
        {
            "gate": "fresh_independent_test_demonstrated",
            "passed": int(holdout.get("fresh_outcome_test_count") or 0) > 0,
            "observed": int(holdout.get("fresh_outcome_test_count") or 0),
        },
        {
            "gate": "real_candidate_frozen",
            "passed": candidate.get("status") == "frozen_real_candidate" and candidate.get("model_id") is not None,
            "observed": candidate.get("status"),
        },
        {
            "gate": "registered_candidate_exists",
            "passed": model_count > 0,
            "observed": model_count,
        },
        {
            "gate": "no_active_model_before_qualification",
            "passed": active_model is None,
            "observed": None if active_model is None else active_model.get("model_id"),
        },
        {
            "gate": "independent_test_remains_sealed",
            "passed": outcome_overview.get("independent_test_opened") is False,
            "observed": outcome_overview.get("independent_test_opened"),
        },
    ]
    blocker_codes = [item["gate"] for item in checks if not item["passed"]]
    can_open_test = not blocker_codes
    return {
        "can_open_independent_test": can_open_test,
        "checks": checks,
        "blocker_codes": blocker_codes,
    }


def build_phase6_reports(
    *,
    readiness: dict[str, Any],
    phase5_freeze: dict[str, Any],
    data_use: dict[str, Any],
    utility_protocol: dict[str, Any],
    outcome_overview: dict[str, Any],
    browser_evidence: dict[str, Any] | None,
    software_evidence: dict[str, Any],
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    utility_check = validate_utility_protocol(utility_protocol)
    gate = _readiness_gate(readiness, phase5_freeze, outcome_overview)
    if not utility_check["valid"]:
        gate["checks"].append({
            "gate": "utility_protocol_valid",
            "passed": False,
            "observed": utility_check["errors"],
        })
        gate["blocker_codes"].append("utility_protocol_valid")
        gate["can_open_independent_test"] = False
    if gate["can_open_independent_test"]:
        raise ValueError(
            "All gates are open. Use the explicit one-shot independent evaluator; "
            "this fail-closed report builder never opens Test data."
        )

    candidate = phase5_freeze.get("candidate") or {}
    browser_passed = bool(browser_evidence and browser_evidence.get("passed") is True)
    software_passed = bool(
        software_evidence.get("backend_tests", {}).get("passed")
        and software_evidence.get("flutter_tests", {}).get("passed")
        and software_evidence.get("flutter_analyze", {}).get("passed")
        and software_evidence.get("web_build", {}).get("passed")
        and browser_passed
    )
    independent = {
        "schema_version": "outcome-independent-evaluation-report-v1",
        "generated_at": generated_at,
        "status": "not_run",
        "target_version": readiness.get("target_version"),
        "candidate": {
            "status": candidate.get("status"),
            "model_id": candidate.get("model_id"),
            "model_version": candidate.get("model_version"),
            "reason_codes": candidate.get("reason_codes") or [],
        },
        "frozen_hashes": {
            "protocol_sha256": phase5_freeze.get("protocol_sha256"),
            "readiness_audit_sha256": readiness.get("audit_sha256"),
            "phase5_freeze_sha256": sha256_json(phase5_freeze),
            "utility_protocol_sha256": utility_check["protocol_sha256"],
            "candidate_artifact_sha256": None,
            "feature_schema_sha256": None,
            "preprocessing_sha256": None,
            "calibrator_sha256": None,
            "baseline_sha256": None,
            "context_selection_sha256": None,
        },
        "independence_gate": gate,
        "test_access": {
            "test_data_access_performed": False,
            "independent_test_opened": False,
            "unlocked_at": None,
            "unlocked_by": None,
            "evaluated_sample_ids": [],
        },
        "evaluation": {
            "candidate_metrics": None,
            "constant_baseline_metrics": None,
            "metadata_baseline_metrics": None,
            "calibration": None,
            "channel_bootstrap": None,
            "coverage": None,
            "scope_results": {category: {"status": "not_run"} for category in TARGET_CATEGORIES},
        },
        "reason_codes": gate["blocker_codes"],
        "statement": (
            "Independent Test was not opened because prerequisite gates failed. "
            "Missing metrics are null and are not zero-valued results."
        ),
    }
    qualification = {
        "schema_version": "outcome-qualification-decision-v1",
        "generated_at": generated_at,
        "decision": "not_qualified",
        "prediction_qualified": False,
        "activation_authorized": False,
        "production_activation_performed": False,
        "independent_evaluation_status": "not_run",
        "reason_codes": gate["blocker_codes"],
        "scopes": {
            category: {
                "status": "not_run",
                "qualified": False,
                "reason": "independent_evaluation_not_run",
            }
            for category in TARGET_CATEGORIES
        },
    }
    utility_raw = {
        "schema_version": "outcome-utility-raw-ratings-v1",
        "generated_at": generated_at,
        "protocol_sha256": utility_check["protocol_sha256"],
        "status": "not_started",
        "source": "human_reviewers_only",
        "reviewer_ids": [],
        "case_ids": [],
        "ratings": [],
        "variant_c_status": "unavailable_prediction_not_qualified",
        "synthetic_or_ai_ratings_used": False,
    }
    utility_summary = {
        "schema_version": "outcome-utility-summary-v1",
        "generated_at": generated_at,
        "status": "not_evaluated",
        "protocol_valid": utility_check["valid"],
        "protocol_errors": utility_check["errors"],
        "real_reviewer_count": 0,
        "in_scope_case_count": 0,
        "refusal_case_count": 0,
        "rating_count": 0,
        "median_clarity": None,
        "median_actionability": None,
        "correct_non_guarantee_interpretation_ratio": None,
        "fabricated_evidence_count": None,
        "paired_b_vs_c": None,
        "passed": None,
        "note": "Missing ratings are missing values, not zero scores.",
    }
    workflow_statuses = [
        (1, "upload_to_assessment_or_abstention", "NOT RUN", "no_fresh_live_clip_and_classifier_not_accepted"),
        (2, "copy_select_save_reopen", "NOT RUN", "no_separate_live_acceptance_session"),
        (3, "historical_snapshot_immutability", "PASS" if software_passed else "NOT RUN", "automated_regression"),
        (4, "revision_comparison", "PASS" if software_passed else "NOT RUN", "automated_regression"),
        (5, "admin_preflight_and_reject_unqualified", "PASS" if software_passed else "NOT RUN", "live_read_and_automated_regression"),
        (6, "qualified_activate_new_analysis_rollback", "NOT RUN", "no_qualified_model"),
        (7, "restart_persistence_and_job_recovery", "NOT RUN", "not_exercised_in_phase6"),
        (8, "failure_modes", "PASS" if software_passed else "NOT RUN", "automated_regression"),
        (9, "ownership_and_role_isolation", "PASS" if software_passed else "NOT RUN", "automated_regression"),
        (10, "responsive_browser_1440_1000_390", "PASS" if browser_passed else "NOT RUN", "browser_evidence"),
    ]
    live_acceptance = {
        "schema_version": "outcome-live-acceptance-v1",
        "generated_at": generated_at,
        "overall_status": "NOT RUN",
        "reason": "positive_live_end_to_end_requires_a_fresh_clip_and_qualified_outcome_model",
        "fixture_positive_claim_used": False,
        "workflows": [
            {"workflow": number, "name": name, "status": status, "evidence_mode": mode}
            for number, name, status, mode in workflow_statuses
        ],
    }
    performance = {
        "schema_version": "outcome-performance-evaluation-v1",
        "generated_at": generated_at,
        "status": "NOT RUN",
        "latency_ms": None,
        "sample_count": 0,
        "reason": "no_qualified_real_model_available",
    }
    rights_passed = (
        (data_use.get("decision") or {}).get("real_training_allowed") is True
        and (data_use.get("decision") or {}).get("real_serving_allowed") is True
        and bool(data_use.get("confirmation_evidence"))
    )
    matrix = [
        {"area": "Software/Regression", "status": "PASS" if software_passed else "NOT RUN", "artifact": "software-evidence.json"},
        {"area": "Data rights/Retention", "status": "PASS" if rights_passed else "FAIL", "artifact": "data-use-decision.json"},
        {"area": "Data independence/readiness", "status": "FAIL", "artifact": "independent-evaluation-report.json"},
        {"area": "Prediction qualification", "status": "NOT RUN", "artifact": "qualification-decision.json"},
        {"area": "Human utility", "status": "NOT RUN", "artifact": "utility-summary.json"},
        {"area": "Live end-to-end", "status": "NOT RUN", "artifact": "live-acceptance.json"},
        {"area": "Performance/Latency", "status": "NOT RUN", "artifact": "performance.json"},
    ]
    release = {
        "schema_version": PHASE6_SCHEMA_VERSION,
        "generated_at": generated_at,
        "release_freeze_status": "pending_not_backdated",
        "target_release_freeze_date": "2026-10-17",
        "decision": "NO_GO",
        "qualification": "not_qualified",
        "activation": "not_authorized",
        "phase7_started": False,
        "matrix": matrix,
        "blocker_codes": gate["blocker_codes"],
    }
    model_card = _model_card(generated_at, readiness, phase5_freeze, gate)
    summary = _summary_markdown(release, readiness, independent, utility_summary)
    return {
        "independent-evaluation-report.json": independent,
        "qualification-decision.json": qualification,
        "utility-raw-ratings.json": utility_raw,
        "utility-summary.json": utility_summary,
        "live-acceptance.json": live_acceptance,
        "performance.json": performance,
        "software-evidence.json": software_evidence,
        "data-use-decision.json": data_use,
        "release-decision.json": release,
        "model-card.md": model_card,
        "summary.md": summary,
    }


def _model_card(
    generated_at: str,
    readiness: dict[str, Any],
    freeze: dict[str, Any],
    gate: dict[str, Any],
) -> str:
    dataset = readiness.get("dataset") or {}
    candidate = freeze.get("candidate") or {}
    blockers = "`, `".join(gate["blocker_codes"])
    return f"""# Outcome model card: no qualified candidate

- Generated: `{generated_at}`
- Candidate status: `{candidate.get('status')}`
- Model ID: `{candidate.get('model_id')}`
- Qualification: **not qualified**
- Activation: **not authorized**

## Intended target

Estimate the probability that a video is above its frozen reference-group median for the protocol-defined observation window. This is not a prediction of exact views and is not evidence that following a recommendation causes engagement to increase.

## Evaluation status

Independent evaluation was **not run**. Test data remained sealed and no Test sample IDs or outcomes were read.

Frozen protocol SHA-256: `{freeze.get('protocol_sha256')}`. No candidate artifact, preprocessing, calibrator, baseline or context-selection hash exists because no real candidate was trained.

## Current data snapshot

- Active target rows: {dataset.get('active_target_rows', 0)}
- Structurally ready rows: {dataset.get('structurally_ready_without_rights_or_outcome_split', 0)}
- Training-allowed rows: {dataset.get('training_allowed_rows', 0)}
- Fresh independent Test rows demonstrated: {(readiness.get('holdout') or {}).get('fresh_outcome_test_count', 0)}

## Blocking gates

`{blockers}`

## Metrics and limitations

No model metrics, calibration result, bootstrap interval, scope qualification, or latency measurement exists for a real candidate. Synthetic fixtures are UI test data only and are not model evidence. Data selection is currently biased toward the available project dataset, and data-use/retention permission remains unverified.
"""


def _summary_markdown(
    release: dict[str, Any],
    readiness: dict[str, Any],
    independent: dict[str, Any],
    utility: dict[str, Any],
) -> str:
    rows = [
        "# Outcome Prediction Phase 6 evaluation snapshot",
        "",
        f"- Generated: `{release['generated_at']}`",
        f"- Decision: **{release['decision']}**",
        "- Independent Test opened: **false**",
        "- Phase 7 started: **false**",
        "",
        "## Acceptance matrix",
        "",
        "| Area | Status | Artifact |",
        "|---|---|---|",
    ]
    for item in release["matrix"]:
        rows.append(f"| {item['area']} | **{item['status']}** | `{item['artifact']}` |")
    rows.extend([
        "",
        "## Honest current result",
        "",
        f"- Active source rows: **{(readiness.get('dataset') or {}).get('active_target_rows', 0)}**",
        f"- Structurally ready: **{(readiness.get('dataset') or {}).get('structurally_ready_without_rights_or_outcome_split', 0)}**",
        f"- Training allowed: **{(readiness.get('dataset') or {}).get('training_allowed_rows', 0)}**",
        f"- Independent evaluation: **{independent['status']}**",
        f"- Human utility: **{utility['status']}** ({utility['real_reviewer_count']} reviewers)",
        "",
        "The missing prediction and utility values are recorded as null/not run, not as zero. The 17 October release freeze is still pending and was not backdated.",
    ])
    return "\n".join(rows) + "\n"


def write_phase6_bundle(output_dir: Path | str, reports: dict[str, Any]) -> dict[str, Any]:
    target = Path(output_dir).resolve()
    target.mkdir(parents=True, exist_ok=False)
    written: list[Path] = []
    for name, value in reports.items():
        path = target / name
        if isinstance(value, str):
            path.write_text(value, encoding="utf-8")
        else:
            path.write_text(
                json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
                encoding="utf-8",
            )
        written.append(path)
    integrity = {
        "schema_version": "outcome-phase6-integrity-v1",
        "files": {path.name: file_sha256(path) for path in sorted(written)},
    }
    integrity["bundle_sha256"] = sha256_json(integrity["files"])
    (target / "integrity.json").write_text(
        json.dumps(integrity, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "output_dir": str(target),
        "file_count": len(written) + 1,
        "bundle_sha256": integrity["bundle_sha256"],
    }
