import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services import classification_readiness as service
from app.services.classification_acceptance import apply_acceptance_policy
from tests import test_classification_acceptance as fixtures


class ClassificationReadinessTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.ClassificationAcceptanceTests()
        fixture.setUp()
        self.policy = fixture.fit()
        self.model = SimpleNamespace(model_id=14, model_key="test", model_version="v1",
            model_type="tfidf", training_sample_count=100, taxonomy_version="v1", status="qualified",
            artifact_path="private/model.joblib")
        self.artifact = {"model_key": "test", "model_version": "v1", "unknown_threshold": 0.6}
        patch.object(service.settings, "classification_require_scope_validation", True).start()
        self.loader = patch.object(service, "load_classification_artifact", return_value=self.artifact).start()
        patch.object(service, "classification_artifact_sha256", return_value="abc").start()
        self.addCleanup(patch.stopall)

    def snapshot(self):
        return service.classification_model_snapshot(self.model)

    def test_missing_policy_matches_runtime_withholding_even_if_qualified(self):
        result = self.snapshot()
        self.assertEqual(result["status"], "qualified")
        self.assertTrue(result["readiness"]["artifact_loadable"])
        self.assertEqual(result["readiness"]["reason_codes"], ["scope_policy_missing"])
        self.assertFalse(result["readiness"]["can_accept_predictions"])
        labels, _ = apply_acceptance_policy(None, ["test"], ["phone"], [0.99])
        self.assertEqual(labels, ["unknown"])

    def test_invalid_failed_or_old_policies_are_not_ready(self):
        for policy in ({"status": "insufficient_validation"}, {"status": "validated"},
                       {**self.policy, "version": "old"}):
            self.artifact["scope_policy"] = policy
            self.assertEqual(self.snapshot()["readiness"]["status"], "blocked")
            self.assertIn("scope_policy_not_validated", self.snapshot()["readiness"]["reason_codes"])

    def test_valid_policy_is_ready_but_does_not_pretend_test_passed(self):
        self.artifact["scope_policy"] = self.policy
        result = self.snapshot()
        self.assertEqual(result["readiness"]["status"], "ready")
        self.assertFalse(result["readiness"]["scope_test_passed"])
        self.assertNotIn("train_vectors", result["scope_validation"])
        self.assertNotIn("vectorizer", result["scope_validation"])
        self.model.status = "evaluated_below_threshold"
        self.assertFalse(self.snapshot()["readiness"]["can_accept_predictions"])

    def test_corrupt_mismatched_and_smoke_artifacts_are_blocked_without_path_leak(self):
        for updates in ({"model_version": "other"}, {"smoke_test_only": True}):
            self.loader.return_value = {**self.artifact, **updates}
            self.assertEqual(self.snapshot()["status"], "artifact_unavailable")
        self.loader.side_effect = EOFError("private/model.joblib")
        result = self.snapshot()
        self.assertFalse(result["readiness"]["artifact_loadable"])
        self.assertNotIn("private", str(result))

    def test_disabling_enforcement_is_never_reported_as_validated(self):
        with patch.object(service.settings, "classification_require_scope_validation", False):
            result = self.snapshot()["readiness"]
        self.assertTrue(result["can_accept_predictions"])
        self.assertEqual(result["status"], "unvalidated")
        self.assertIn("scope_validation_disabled", result["reason_codes"])

    def test_no_active_is_explicit_and_does_not_load_an_artifact(self):
        result = service.classification_model_snapshot(None)
        self.assertIsNone(result["model_id"])
        self.assertEqual(result["readiness"]["reason_codes"], ["no_active_model"])
        self.loader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
