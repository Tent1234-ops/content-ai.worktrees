import copy
import json
import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np

from app.services import outcome_training as training
from app.services.outcome_training_fixture import write_synthetic_fixture


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "docs/implementation/outcome-prediction-protocol-v1.json"


class OutcomeTrainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
        cls.fixture = write_synthetic_fixture(cls.root / "input", cls.protocol)
        cls.model_dir = cls.root / "model"
        cls.report = training.train_and_validate_outcome_model(
            manifest_path=cls.fixture["manifest_path"],
            features_path=cls.fixture["features_path"],
            protocol_path=PROTOCOL_PATH,
            data_use_path=cls.fixture["data_use_path"],
            output_dir=cls.model_dir,
            trusted_phase2_root=cls.root / "input",
            source_kind="synthetic_fixture",
        )

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def preflight(self, fixture=None):
        fixture = fixture or self.fixture
        return training.load_training_inputs(
            manifest_path=fixture["manifest_path"],
            features_path=fixture["features_path"],
            protocol=self.protocol,
            data_use_record=json.loads(fixture["data_use_path"].read_text(encoding="utf-8")),
            trusted_root=fixture["manifest_path"].parent,
        )

    def test_fixture_pipeline_is_validation_only_and_test_stays_sealed(self):
        self.assertEqual(self.report["status"], "fixture_validation_passed")
        self.assertTrue(self.report["artifact_created"])
        self.assertFalse(self.report["independent_test_opened"])
        self.assertFalse(self.report["production_eligible"])
        self.assertFalse(self.report["qualification"]["qualified"])
        self.assertEqual(self.report["selected_C"], 10.0)
        manifest = json.loads(self.fixture["manifest_path"].read_text(encoding="utf-8"))
        tests = [row for row in manifest["records"] if row["outcome_role"] == "independent_test"]
        self.assertEqual(len(tests), 30)
        self.assertTrue(all("views" not in row["observation"] for row in tests))
        self.assertTrue(all(row["outcome_access"] == "sealed_until_phase_6_evaluation" for row in tests))

    def test_partitions_are_channel_disjoint_and_use_same_evaluation_support(self):
        preflight = self.preflight()
        self.assertTrue(preflight["ready"], preflight["reason_codes"])
        channel_sets = {
            role: {row["source_channel_id"] for row in rows}
            for role, rows in preflight["rows"].items()
        }
        channel_sets["independent_test"] = {
            row["source_channel_id"] for row in preflight["test_records"]
        }
        roles = list(channel_sets)
        for index, left in enumerate(roles):
            for right in roles[index + 1:]:
                self.assertFalse(channel_sets[left] & channel_sets[right])
        tuning = self.report["tuning_metrics"]
        counts = {
            values["before"]["overall"]["channel_balanced"]["sample_count"]
            for values in tuning.values()
        }
        self.assertEqual(counts, {30})

    def test_heldout_outcome_changes_do_not_change_fit_or_model_choice(self):
        second = write_synthetic_fixture(
            self.root / "heldout-mutated", self.protocol,
            independent_test_view_offset=999_999,
        )
        second_report = training.train_and_validate_outcome_model(
            manifest_path=second["manifest_path"], features_path=second["features_path"],
            protocol_path=PROTOCOL_PATH, data_use_path=second["data_use_path"],
            output_dir=self.root / "heldout-mutated-model",
            trusted_phase2_root=self.root / "heldout-mutated",
            source_kind="synthetic_fixture",
        )
        self.assertEqual(self.report["selected_C"], second_report["selected_C"])
        original_coefficients = json.loads(
            (self.model_dir / "coefficients.json").read_text(encoding="utf-8")
        )
        changed_coefficients = json.loads(
            (self.root / "heldout-mutated-model/coefficients.json").read_text(encoding="utf-8")
        )
        self.assertEqual(original_coefficients, changed_coefficients)
        self.assertNotEqual(
            self.report["split_hashes"]["independent_test"],
            second_report["split_hashes"]["independent_test"],
        )

    def test_artifact_round_trip_and_integrity_guards(self):
        artifact = self.model_dir / "model.joblib"
        loaded = training.load_outcome_artifact(
            artifact, trusted_root=self.model_dir,
            expected_sha256=self.report["artifact_sha256"],
            expected_protocol_sha256=self.report["protocol_sha256"],
            expected_feature_schema_sha256=self.report["feature_schema_sha256"],
        )
        direct = joblib.load(artifact)
        preflight = self.preflight()
        rows = preflight["rows"]["tuning"]
        left = direct["models"]["metadata_topics_logistic_regression"]
        right = loaded["models"]["metadata_topics_logistic_regression"]
        matrix = training._matrix(rows, left["layout"])
        np.testing.assert_allclose(
            left["estimator"].predict_proba(matrix),
            right["estimator"].predict_proba(matrix),
        )
        with self.assertRaisesRegex(ValueError, "checksum"):
            training.load_outcome_artifact(
                artifact, trusted_root=self.model_dir,
                expected_sha256="0" * 64,
                expected_protocol_sha256=self.report["protocol_sha256"],
                expected_feature_schema_sha256=self.report["feature_schema_sha256"],
            )
        with self.assertRaisesRegex(ValueError, "protocol"):
            training.load_outcome_artifact(
                artifact, trusted_root=self.model_dir,
                expected_sha256=self.report["artifact_sha256"],
                expected_protocol_sha256="0" * 64,
                expected_feature_schema_sha256=self.report["feature_schema_sha256"],
            )
        tampered = copy.deepcopy(direct)
        layout = tampered["models"]["metadata_topics_logistic_regression"]["layout"]
        layout["columns"] = list(reversed(layout["columns"]))
        tampered_path = self.root / "tampered-order.joblib"
        joblib.dump(tampered, tampered_path)
        with self.assertRaisesRegex(ValueError, "feature order mismatch"):
            training.load_outcome_artifact(
                tampered_path, trusted_root=self.root,
                expected_sha256=training.file_sha256(tampered_path),
                expected_protocol_sha256=self.report["protocol_sha256"],
                expected_feature_schema_sha256=self.report["feature_schema_sha256"],
            )

    def test_feature_hash_tampering_blocks_preflight(self):
        folder = self.root / "tampered"
        folder.mkdir()
        manifest = json.loads(self.fixture["manifest_path"].read_text(encoding="utf-8"))
        features = json.loads(self.fixture["features_path"].read_text(encoding="utf-8"))
        features[0]["model_input"]["duration_seconds"] += 1
        (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (folder / "features.json").write_text(json.dumps(features), encoding="utf-8")
        result = training.load_training_inputs(
            manifest_path=folder / "manifest.json", features_path=folder / "features.json",
            protocol=self.protocol,
            data_use_record=json.loads(self.fixture["data_use_path"].read_text(encoding="utf-8")),
            trusted_root=folder,
        )
        self.assertFalse(result["ready"])
        self.assertIn("feature_artifact_invalid", result["reason_codes"])

    def test_degenerate_metrics_and_bootstrap_are_explicitly_not_evaluable(self):
        metrics = training._metric_values([1, 1], [0.6, 0.7], [1, 1])
        self.assertEqual(metrics["status"], "partially_evaluable")
        self.assertIsNone(metrics["roc_auc"])
        one_channel = [
            {"source_channel_id": "only", "label": 0},
            {"source_channel_id": "only", "label": 1},
        ]
        result = training.paired_channel_bootstrap(
            one_channel, [0.2, 0.8], [0.5, 0.5],
            resamples=20, confidence=0.95, seed=1,
        )
        self.assertEqual(result["status"], "not_evaluable")
        rows = [
            {"source_channel_id": f"c{i}", "label": i % 2}
            for i in range(8)
        ]
        result = training.paired_channel_bootstrap(
            rows,
            [0.15 if row["label"] == 0 else 0.85 for row in rows],
            [0.4 + 0.02 * i for i in range(8)],
            resamples=100, confidence=0.95, seed=4,
        )
        self.assertTrue(result["duplicates_preserved"])
        self.assertGreater(result["draws_with_duplicate_channels"], 0)
        self.assertEqual(result["resampled_channel_count_per_draw"], 8)

    def test_activation_gate_cannot_be_forced_before_phase_6(self):
        gate = training.activation_validation(
            {"status": "validation_passed", "independent_test_passed": False,
             "production_eligible": False},
            json.loads(self.fixture["data_use_path"].read_text(encoding="utf-8")),
        )
        self.assertFalse(gate["can_activate"])
        self.assertFalse(gate["force_override_supported"])
        self.assertIn("model_not_independent_test_qualified", gate["reason_codes"])


if __name__ == "__main__":
    unittest.main()
