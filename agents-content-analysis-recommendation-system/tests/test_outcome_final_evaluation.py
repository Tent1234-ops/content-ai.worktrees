import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.services.outcome_final_evaluation import (
    build_phase6_reports,
    validate_utility_protocol,
    write_phase6_bundle,
)


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


class OutcomeFinalEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.readiness = {
            "target_version": "reference_relative_views_v1",
            "protocol": {
                "valid": True,
                "protocol_sha256": "ef3a7475e2a005b5dda4f9311eec6740570277b82204847a32114d6bdae6e12b",
            },
            "database_unchanged": True,
            "data_use": {
                "training": {"allowed": False},
                "serving": {"allowed": False},
            },
            "dataset": {
                "active_target_rows": 308,
                "structurally_ready_without_rights_or_outcome_split": 0,
                "training_allowed_rows": 0,
            },
            "holdout": {"fresh_outcome_test_count": 0},
            "audit_sha256": "readiness-hash",
        }
        self.freeze = load("docs/implementation/outcome-prediction-phase-5-freeze.json")
        self.data_use = load("docs/implementation/outcome-prediction-data-use-v1.json")
        self.utility = load("docs/implementation/outcome-prediction-utility-study-v1.json")
        self.overview = {
            "models": {"total": 0, "items": []},
            "active_model": None,
            "independent_test_opened": False,
        }
        self.browser = {"passed": True, "screenshots": ["a.png"], "errors": []}
        self.software = {
            "backend_tests": {"passed": True},
            "flutter_tests": {"passed": True},
            "flutter_analyze": {"passed": True},
            "web_build": {"passed": True},
        }

    def reports(self):
        return build_phase6_reports(
            readiness=self.readiness,
            phase5_freeze=self.freeze,
            data_use=self.data_use,
            utility_protocol=self.utility,
            outcome_overview=self.overview,
            browser_evidence=self.browser,
            software_evidence=self.software,
            generated_at="2026-10-09T12:00:00Z",
        )

    def test_blocked_state_never_opens_or_exposes_test(self):
        self.readiness["records"] = [{"dataset_id": "must-not-leak"}]
        report = self.reports()["independent-evaluation-report.json"]
        self.assertEqual(report["status"], "not_run")
        self.assertFalse(report["test_access"]["test_data_access_performed"])
        self.assertFalse(report["test_access"]["independent_test_opened"])
        self.assertEqual(report["test_access"]["evaluated_sample_ids"], [])
        self.assertIsNone(report["evaluation"]["candidate_metrics"])
        self.assertEqual(report["frozen_hashes"]["readiness_audit_sha256"], "readiness-hash")
        self.assertEqual(
            report["frozen_hashes"]["protocol_sha256"],
            self.freeze["protocol_sha256"],
        )
        self.assertIsNone(report["frozen_hashes"]["candidate_artifact_sha256"])
        self.assertIn("training_rights_confirmed", report["reason_codes"])
        self.assertIn("fresh_independent_test_demonstrated", report["reason_codes"])
        self.assertNotIn("must-not-leak", json.dumps(report))

    def test_missing_human_ratings_remain_missing_not_zero(self):
        reports = self.reports()
        raw = reports["utility-raw-ratings.json"]
        summary = reports["utility-summary.json"]
        self.assertEqual(raw["ratings"], [])
        self.assertFalse(raw["synthetic_or_ai_ratings_used"])
        self.assertEqual(summary["status"], "not_evaluated")
        self.assertIsNone(summary["median_clarity"])
        self.assertIsNone(summary["fabricated_evidence_count"])
        self.assertIsNone(summary["passed"])

    def test_unqualified_candidate_cannot_activate_any_scope(self):
        decision = self.reports()["qualification-decision.json"]
        self.assertFalse(decision["prediction_qualified"])
        self.assertFalse(decision["activation_authorized"])
        self.assertTrue(all(
            item["status"] == "not_run" and not item["qualified"]
            for item in decision["scopes"].values()
        ))

    def test_current_utility_protocol_is_valid_and_strict(self):
        self.assertTrue(validate_utility_protocol(self.utility)["valid"])
        changed = json.loads(json.dumps(self.utility))
        changed["minimum_real_reviewers"] = 2
        result = validate_utility_protocol(changed)
        self.assertFalse(result["valid"])
        self.assertIn("minimum_real_reviewers_must_equal_three", result["errors"])

    def test_bundle_is_immutable_and_has_integrity_hashes(self):
        with TemporaryDirectory() as temp:
            target = Path(temp) / "run"
            result = write_phase6_bundle(target, self.reports())
            integrity = json.loads((target / "integrity.json").read_text(encoding="utf-8"))
            self.assertEqual(result["file_count"], 12)
            self.assertEqual(len(integrity["files"]), 11)
            self.assertEqual(result["bundle_sha256"], integrity["bundle_sha256"])
            with self.assertRaises(FileExistsError):
                write_phase6_bundle(target, self.reports())

    def test_builder_refuses_to_open_test_when_all_gates_pass(self):
        self.readiness["data_use"]["training"]["allowed"] = True
        self.readiness["data_use"]["serving"]["allowed"] = True
        self.readiness["dataset"]["structurally_ready_without_rights_or_outcome_split"] = 100
        self.readiness["dataset"]["training_allowed_rows"] = 100
        self.readiness["holdout"]["fresh_outcome_test_count"] = 30
        self.freeze["candidate"] = {
            "status": "frozen_real_candidate", "model_id": 7, "model_version": "v7",
        }
        self.overview["models"] = {"total": 1, "items": [{"model_id": 7}]}
        with self.assertRaisesRegex(ValueError, "explicit one-shot independent evaluator"):
            self.reports()


if __name__ == "__main__":
    unittest.main()
