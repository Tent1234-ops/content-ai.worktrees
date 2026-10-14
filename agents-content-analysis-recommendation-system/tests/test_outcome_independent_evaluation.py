import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import joblib
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.db import Base
from app.database.models import OutcomeModel, OutcomeModelMetric
from app.services import outcome_independent_evaluation as evaluation
from app.services.outcome_training import train_and_validate_outcome_model
from app.services.outcome_training_fixture import write_synthetic_fixture, build_synthetic_records

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "docs/implementation/outcome-prediction-protocol-v1.json"


class OutcomeIndependentEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
        cls.fixture = write_synthetic_fixture(cls.root / "input", cls.protocol, varied_laptop_fit_channels=True)
        cls.report = train_and_validate_outcome_model(
            manifest_path=cls.fixture["manifest_path"], features_path=cls.fixture["features_path"],
            protocol_path=PROTOCOL_PATH, data_use_path=cls.fixture["data_use_path"],
            output_dir=cls.root / "trained", trusted_phase2_root=cls.root / "input", source_kind="synthetic_fixture",
        )
        cls.outcomes = {row["dataset_id"]: row["observation"]["views"]
                        for row in build_synthetic_records(cls.protocol, varied_laptop_fit_channels=True)}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.local = tempfile.TemporaryDirectory(dir=self.root)
        self.directory = Path(self.local.name)
        self.registry = self.directory / "registry"
        shutil.copytree(self.root / "trained", self.registry / "candidate")
        self.engine = create_engine(f"sqlite:///{self.directory / 'db.sqlite3'}")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        report = self.report
        self.model = OutcomeModel(
            model_version="synthetic-independent-eval", target_version=report["target_version"],
            protocol_sha256=report["protocol_sha256"], feature_schema_sha256=report["feature_schema_sha256"],
            manifest_sha256=report["manifest_sha256"], split_hashes_json=json.dumps(report["split_hashes"]),
            calibration_version=report["calibration_version"], source_kind="synthetic_fixture",
            status=report["status"], is_active=False,
            artifact_path=str(self.registry / "candidate/model.joblib"), artifact_sha256=report["artifact_sha256"],
            metrics_json="{}", evaluated_scopes_json="{}", library_versions_json="{}",
            independent_test_passed=False, production_eligible=False,
        )
        self.db.add(self.model)
        self.db.commit()
        self.inputs = dict(model_id=self.model.model_id, manifest_path=self.fixture["manifest_path"],
                           features_path=self.fixture["features_path"], protocol_path=PROTOCOL_PATH,
                           data_use_path=self.fixture["data_use_path"], trusted_root=self.registry,
                           phase2_root=self.root / "input", repo_root=self.directory, allow_synthetic_fixture=True)
        self.freeze = self.directory / "freeze.json"
        self.loader = Mock(side_effect=lambda records: [dict(row, observation=dict(
            row["observation"], views=self.outcomes[row["dataset_id"]])) for row in records])

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.local.cleanup()

    def freeze_candidate(self):
        self.assertEqual(self.report["status"], "fixture_validation_passed")
        return evaluation.freeze_candidate(self.db, output_path=self.freeze, actor="synthetic-reviewer", **self.inputs)

    def run_evaluation(self, **changes):
        args = dict(freeze_path=self.freeze, output_dir=self.registry / "evaluated",
                    ledger_root=self.directory / "ledger", actor="synthetic-reviewer", confirm_open_test=True,
                    outcome_loader=self.loader, **self.inputs)
        args.update(changes)
        return evaluation.evaluate_candidate(self.db, **args)

    def test_real_path_evaluates_without_fit_and_persists_honest_failure(self):
        plan = self.freeze_candidate()
        self.assertFalse(plan["test_opened"])
        with patch("app.services.outcome_training._fit_models", side_effect=AssertionError("must not train")), \
             patch("app.services.outcome_training.WeightedSigmoidCalibrator.fit", side_effect=AssertionError("must not calibrate")):
            report = self.run_evaluation()
        self.loader.assert_called_once()
        self.assertTrue(report["independent_test_opened"])
        self.assertEqual(report["status"], "experimental")
        self.assertEqual(report["evaluation"]["metrics"][evaluation.MODEL_NAMES[-1]]["coverage"]["abstained"], 0)
        self.assertFalse(report["production_eligible"])
        self.assertFalse(self.model.is_active)
        self.assertGreater(self.db.query(OutcomeModelMetric).count(), 0)
        self.assertTrue((self.registry / "candidate/model.joblib").is_file())
        with self.assertRaises(ValueError):
            self.run_evaluation(output_dir=self.registry / "second")
        self.assertEqual(self.loader.call_count, 1)

    def test_no_confirmation_no_test_access(self):
        self.freeze_candidate()
        with self.assertRaisesRegex(ValueError, "confirmation"):
            self.run_evaluation(confirm_open_test=False)
        self.loader.assert_not_called()
        self.assertFalse((self.directory / "ledger").exists())

    def test_changed_candidate_hash_is_rejected_before_access(self):
        self.freeze_candidate()
        self.model.artifact_sha256 = "0" * 64
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.run_evaluation()
        self.loader.assert_not_called()

    def test_data_denial_and_synthetic_source_do_not_pass_real_mode(self):
        with self.assertRaisesRegex(ValueError, "Synthetic"):
            evaluation.freeze_candidate(self.db, output_path=self.freeze, actor="test",
                                        **dict(self.inputs, allow_synthetic_fixture=False))
        self.loader.assert_not_called()

    def test_failed_open_is_durable_and_shared_test_cannot_be_reused(self):
        plan = self.freeze_candidate()
        self.loader.side_effect = ValueError("missing observation")
        with self.assertRaisesRegex(ValueError, "missing observation"):
            self.run_evaluation()
        self.assertEqual(self.model.status, "evaluation_failed")
        self.assertTrue((self.registry / "evaluated/evaluation-error.json").exists())
        records = json.loads(self.fixture["manifest_path"].read_text(encoding="utf-8"))["records"]
        tests = [row for row in records if row["outcome_role"] == "independent_test"]
        with self.assertRaisesRegex(ValueError, "already accessed"):
            evaluation._claim_test(self.directory / "ledger", plan=plan, records=tests,
                                   actor="different-model", run_id="second-run")

    def test_test_commitment_mismatch_is_not_silently_relabeled(self):
        self.freeze_candidate()
        self.loader.side_effect = lambda records: [dict(row, observation=dict(row["observation"], views=999999))
                                                  for row in records]
        with self.assertRaisesRegex(ValueError, "commitment"):
            self.run_evaluation()


class _SyntheticEstimator:
    def __init__(self, candidate):
        self.candidate = candidate

    def predict_proba(self, rows):
        p = np.asarray([row["synthetic_probability"] if self.candidate else 0.5 for row in rows])
        return np.column_stack([1 - p, p])


class _IdentityCalibrator:
    def predict(self, probabilities):
        return probabilities


class IndependentDecisionTests(unittest.TestCase):
    def test_positive_and_negative_decisions_use_frozen_numeric_gates(self):
        protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
        rows, contexts, signatures = [], [], []
        for category in ("phone", "camera", "laptop"):
            context = [category, "long_form", "age_30_90d", "youtube_play_start_view_v2"]
            contexts.append(context)
            signatures.append(dict(zip(evaluation.CONTEXT_FIELDS[:3], context[:3]),
                                   topic_signature=[], video_count=20, channel_count=5))
            for index in range(40):
                label = int(index >= 20)
                p = 0.02 + index * 0.003 if label == 0 else 0.87 + (index - 20) * 0.004
                rows.append(dict(zip(evaluation.CONTEXT_FIELDS[:3], context[:3]), dataset_id=len(rows) + 1,
                                 label=label, source_channel_id=f"{category}-{index % 10}",
                                 observation={"view_metric_version": context[3]}, synthetic_probability=p,
                                 model_input=dict(zip(evaluation.CONTEXT_FIELDS[:3], context[:3]),
                                                  canonical_topic_presence={})))
        artifact = {"training_support": {"version": "outcome-training-support-v1", "minimum_signature_videos": 2,
                    "minimum_signature_channels": 2, "signatures": signatures}, "models": {
                    name: {"estimator": _SyntheticEstimator(name == evaluation.MODEL_NAMES[-1]),
                           "calibrator": _IdentityCalibrator(), "layout": None} for name in evaluation.MODEL_NAMES}}
        result = evaluation.evaluate_predictions(rows, artifact=artifact, protocol=protocol, contexts=contexts)
        self.assertTrue(result["passed"], result["checks"])
        self.assertTrue(all(item["qualified"] for item in result["evaluated_scopes"]["contexts"]))
        sparse = copy.deepcopy(rows)
        sparse[0]["model_input"]["canonical_topic_presence"] = {"unseen": True}
        sparse_result = evaluation.evaluate_predictions(sparse, artifact=artifact, protocol=protocol, contexts=contexts)
        scope = sparse_result["evaluated_scopes"]["contexts"][0]
        for values in scope["metrics"].values():
            self.assertEqual(values["coverage"]["eligible"], 40)
            self.assertEqual(values["coverage"]["assessed"], 39)
            self.assertEqual(values["coverage"]["abstained"], 1)
        poor = copy.deepcopy(rows)
        for row in poor:
            row["synthetic_probability"] = 1 - row["synthetic_probability"]
        failed = evaluation.evaluate_predictions(poor, artifact=artifact, protocol=protocol, contexts=contexts)
        self.assertFalse(failed["passed"])
        self.assertTrue(all(not item["qualified"] for item in failed["evaluated_scopes"]["contexts"]))


if __name__ == "__main__":
    unittest.main()
