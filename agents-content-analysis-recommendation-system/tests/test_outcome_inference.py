import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import joblib
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.db import Base
from app.database.models import AnalysisResult, OutcomeModel, User, UserContent
from app.services import outcome_inference as inference
from app.services.outcome_evidence import attach_outcome_evidence_explanations
from app.services.outcome_scenarios import simulate_outcome_scenario
from app.services.outcome_training import file_sha256, train_and_validate_outcome_model
from app.services.outcome_training_fixture import build_synthetic_records, write_synthetic_fixture
from app.services.persistence import save_video_analysis_result
from app.services.contents import get_user_content_detail
from app.services.recommendation_evidence import fingerprint
from app.services.revision_comparisons import _outcome_revision_comparison


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "docs/implementation/outcome-prediction-protocol-v1.json"


class OutcomeInferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
        cls.fixture = write_synthetic_fixture(cls.root / "fixture", cls.protocol)
        cls.model_dir = cls.root / "registry" / "qualified-fixture"
        cls.report = train_and_validate_outcome_model(
            manifest_path=cls.fixture["manifest_path"],
            features_path=cls.fixture["features_path"],
            protocol_path=PROTOCOL_PATH,
            data_use_path=cls.fixture["data_use_path"],
            output_dir=cls.model_dir,
            trusted_phase2_root=cls.root / "fixture",
            source_kind="synthetic_fixture",
        )
        cls.artifact_path = cls.model_dir / "model.joblib"
        payload = joblib.load(cls.artifact_path)
        payload["qualification"] = {"status": "qualified", "qualified": True}
        payload["production_eligible"] = True
        joblib.dump(payload, cls.artifact_path)
        cls.artifact_sha = file_sha256(cls.artifact_path)
        cls.payload = payload

        cls.engine = create_engine(
            f"sqlite:///{cls.root / 'phase4.db'}", connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(cls.engine)
        cls.sessions = sessionmaker(bind=cls.engine)
        with cls.sessions() as db:
            db.add(OutcomeModel(
                model_version="qualified-fixture-v1",
                target_version=payload["target_version"],
                protocol_sha256=payload["protocol_sha256"],
                feature_schema_sha256=payload["feature_schema_sha256"],
                manifest_sha256=payload["manifest_sha256"],
                split_hashes_json=json.dumps(payload["split_hashes"]),
                calibration_version=payload["calibration_version"],
                source_kind="synthetic_fixture",
                status="qualified",
                is_active=True,
                artifact_path=str(cls.artifact_path),
                artifact_sha256=cls.artifact_sha,
                metrics_json="{}",
                evaluated_scopes_json=json.dumps(payload["evaluated_scopes"]),
                library_versions_json=json.dumps(payload["library_versions"]),
                training_sample_count=126,
                independent_test_passed=True,
                production_eligible=True,
            ))
            db.add_all([
                User(username="outcome-owner", email="outcome-owner@example.test", password_hash="x"),
                User(username="outcome-other", email="outcome-other@example.test", password_hash="x"),
            ])
            db.commit()
        cls.records = build_synthetic_records(cls.protocol)
        supported = [
            item for item in payload["training_support"]["signatures"]
            if item["video_count"] >= payload["training_support"]["minimum_signature_videos"]
            and item["channel_count"] >= payload["training_support"]["minimum_signature_channels"]
        ]
        cls.supported_signature = supported[0]
        cls.record = next(
            row for row in cls.records
            if row["outcome_role"] == "fit"
            and row["accepted_category"] == cls.supported_signature["accepted_category"]
            and row["confirmed_format"] == cls.supported_signature["confirmed_format"]
            and row["frozen_age_context"] == cls.supported_signature["frozen_age_context"]
            and sorted(key for key, value in cls._feature_for(row).items() if value)
                == cls.supported_signature["topic_signature"]
        )
        cls.original_paths = (inference.DATA_USE_PATH, inference.ARTIFACT_ROOT)
        inference.DATA_USE_PATH = cls.fixture["data_use_path"]
        inference.ARTIFACT_ROOT = cls.root / "registry"

    @classmethod
    def _feature_for(cls, row):
        from app.services.outcome_dataset import build_feature_record
        return build_feature_record(row, cls.protocol)["model_input"]["canonical_topic_presence"]

    @classmethod
    def tearDownClass(cls):
        inference.DATA_USE_PATH, inference.ARTIFACT_ROOT = cls.original_paths
        inference.clear_outcome_artifact_cache()
        cls.engine.dispose()
        cls.temp.cleanup()

    def setUp(self):
        inference.clear_outcome_artifact_cache()

    def context(self, record=None):
        record = record or self.record
        return {
            "raw_transcript": record["transcript"],
            "cleaned_transcript": record["transcript"],
            "availability": "available",
            "scope": "full_clip",
            "segments": [],
        }

    def classification(self, category=None):
        category = category or self.record["accepted_category"]
        return {
            "taxonomy_leaf_key": category,
            "domain": category,
            "is_unknown": False,
            "acceptance": {"accepted": True, "reason": "accepted"},
        }

    def metadata(self, record=None):
        record = record or self.record
        return {
            "confirmed_format": record["confirmed_format"],
            "duration_seconds": record["duration_seconds"],
            "reference_age_context": record["frozen_age_context"],
        }

    def assess(self, **changes):
        values = {
            "category": self.record["accepted_category"],
            "classification": self.classification(),
            "evidence_context": self.context(),
            "input_metadata": self.metadata(),
            "evidence_topic_ids": ["topic-fixture"],
            "evidence_pointers": [{"evidence_topic_id": "topic-fixture", "dataset_ids": [1]}],
            "allow_synthetic_fixture": True,
        }
        values.update(changes)
        with self.sessions() as db:
            return inference.assess_outcome(db, **values)

    def test_qualified_fixture_has_train_inference_parity_and_repeat_invariance(self):
        result = self.assess()
        self.assertEqual(result["status"], "available", result)
        self.assertIsNotNone(result["probability"])
        expected = self._feature_for(self.record)
        self.assertEqual(
            result["feature_snapshot"]["model_input"]["canonical_topic_presence"], expected
        )
        present = next((key for key, value in expected.items() if value), None)
        if present:
            repeated = copy.deepcopy(self.context())
            repeated["raw_transcript"] += f" {present} {present} {present}"
            repeated["cleaned_transcript"] = repeated["raw_transcript"]
            second = self.assess(evidence_context=repeated)
            self.assertEqual(second["status"], "available", second)
            self.assertEqual(second["probability"], result["probability"])

    def test_unknown_asr_context_rights_and_artifact_errors_fail_closed(self):
        unknown = self.assess(classification={
            "taxonomy_leaf_key": "unknown", "is_unknown": True,
            "acceptance": {"accepted": False, "reason": "outside_training_support"},
        })
        self.assertEqual(unknown["status"], "classification_withheld")
        self.assertIsNone(unknown["probability"])
        no_asr = self.assess(evidence_context={
            "raw_transcript": "", "availability": "unavailable", "scope": "full_clip",
            "reason": "empty_stt_transcript",
        })
        self.assertEqual(no_asr["status"], "unassessable_transcript")
        no_context = self.assess(input_metadata={})
        self.assertEqual(no_context["status"], "unsupported_context")

        blocked = self.root / "blocked-data-use.json"
        blocked.write_text(json.dumps({"schema_version": "outcome-data-use-decision-v1",
                                       "owner": "test", "status": "pending",
                                       "intended_uses": ["serving"]}), encoding="utf-8")
        with patch.object(inference, "DATA_USE_PATH", blocked):
            denied = self.assess()
        self.assertEqual(denied["status"], "data_use_unverified")

        with self.sessions() as db:
            model = db.query(OutcomeModel).filter_by(model_version="qualified-fixture-v1").one()
            original = model.artifact_sha256
            model.artifact_sha256 = "0" * 64
            db.commit()
        inference.clear_outcome_artifact_cache()
        broken = self.assess()
        self.assertEqual(broken["status"], "error")
        self.assertIsNone(broken["probability"])
        with self.sessions() as db:
            db.query(OutcomeModel).update({OutcomeModel.artifact_sha256: original})
            db.commit()

    def test_one_assessment_pins_one_model_even_if_active_switches_mid_request(self):
        with self.sessions() as db:
            first = db.query(OutcomeModel).filter_by(model_version="qualified-fixture-v1").one()
            second = OutcomeModel(
                model_version="qualified-fixture-v2", target_version=first.target_version,
                protocol_sha256=first.protocol_sha256,
                feature_schema_sha256=first.feature_schema_sha256,
                manifest_sha256=first.manifest_sha256,
                split_hashes_json=first.split_hashes_json,
                calibration_version=first.calibration_version,
                source_kind=first.source_kind, status="qualified", is_active=False,
                artifact_path=first.artifact_path, artifact_sha256=first.artifact_sha256,
                metrics_json="{}", evaluated_scopes_json=first.evaluated_scopes_json,
                library_versions_json=first.library_versions_json,
                training_sample_count=first.training_sample_count,
                independent_test_passed=True, production_eligible=True,
            )
            db.add(second)
            db.commit()
            first_id, second_id = first.model_id, second.model_id
            real_loader = inference._load_cached_artifact

            def switch_after_snapshot(model):
                payload = real_loader(model)
                db.query(OutcomeModel).filter_by(model_id=first_id).update({"is_active": False})
                db.query(OutcomeModel).filter_by(model_id=second_id).update({"is_active": True})
                db.commit()
                return payload

            values = {
                "category": self.record["accepted_category"],
                "classification": self.classification(),
                "evidence_context": self.context(),
                "input_metadata": self.metadata(),
                "allow_synthetic_fixture": True,
            }
            with patch.object(inference, "_load_cached_artifact", side_effect=switch_after_snapshot):
                result = inference.assess_outcome(db, **values)
            self.assertEqual(result["status"], "available", result)
            self.assertEqual(result["model_id"], first_id)
            db.delete(db.get(OutcomeModel, second_id))
            db.query(OutcomeModel).filter_by(model_id=first_id).update({"is_active": True})
            db.commit()

    def _scenario_record(self):
        empty = next(
            row for row in self.records
            if row["outcome_role"] == "fit" and row["accepted_category"] == "phone"
            and not any(self._feature_for(row).values())
        )
        first_topic = next(iter(self._feature_for(empty)))
        assessment = self.assess(
            category="phone", classification=self.classification("phone"),
            evidence_context=self.context(empty), input_metadata=self.metadata(empty),
        )
        self.assertEqual(assessment["status"], "available", assessment)
        recommendation = {
            "domain": "phone",
            "outcome_assessment": assessment,
            "evidence_bundle": {
                "action_topics": [{
                    "topic_id": "topic-fixture", "canonical_topic": first_topic,
                    "user": {"status": "not_detected"},
                }],
                "topic_comparisons": {"items": [{
                    "evidence_topic_id": "topic-fixture",
                    "metrics": {"views": {"status": "comparison_supported"}},
                }]},
            },
        }
        with self.sessions() as db:
            user = db.query(User).filter_by(username="outcome-owner").one()
            content = UserContent(
                user_id=user.user_id, title="scenario", raw_transcript=empty["transcript"],
                cleaned_transcript=empty["transcript"], transcript=empty["transcript"],
            )
            db.add(content)
            db.flush()
            analysis = AnalysisResult(
                content_id=content.content_id,
                summary=json.dumps({"recommendation": recommendation,
                                    "outcome_assessment": assessment}, ensure_ascii=False),
            )
            db.add(analysis)
            db.commit()
            return user.user_id, content.content_id, analysis.result_id, assessment

    def test_scenario_checks_owner_support_and_preserves_signed_delta(self):
        user_id, content_id, analysis_id, assessment = self._scenario_record()
        with self.sessions() as db:
            frozen_before = db.get(AnalysisResult, analysis_id).summary
            result = simulate_outcome_scenario(
                db, user_id=user_id, content_id=content_id, analysis_id=analysis_id,
                assessment_digest=fingerprint(assessment),
                selected_topic_ids=["topic-fixture"], allow_synthetic_fixture=True,
            )
            self.assertEqual(result["status"], "available", result)
            self.assertEqual(
                result["delta_percentage_points"],
                round((result["probability_after"] - result["probability_before"]) * 100, 6),
            )
            self.assertEqual(db.get(AnalysisResult, analysis_id).summary, frozen_before)
            other = db.query(User).filter_by(username="outcome-other").one()
            with self.assertRaises(HTTPException) as denied:
                simulate_outcome_scenario(
                    db, user_id=other.user_id, content_id=content_id, analysis_id=analysis_id,
                    assessment_digest=fingerprint(assessment), selected_topic_ids=["topic-fixture"],
                    allow_synthetic_fixture=True,
                )
            self.assertEqual(denied.exception.status_code, 404)

        with self.sessions() as db, patch(
            "app.services.outcome_scenarios.predict_frozen_model_input",
            side_effect=[
                {"status": "available", "reason_codes": [], "probability": assessment["probability"], "support_summary": {}},
                {"status": "available", "reason_codes": [], "probability": assessment["probability"] - 0.1, "support_summary": {}},
            ],
        ):
            result = simulate_outcome_scenario(
                db, user_id=user_id, content_id=content_id, analysis_id=analysis_id,
                assessment_digest=fingerprint(assessment), selected_topic_ids=["topic-fixture"],
                allow_synthetic_fixture=True,
            )
            self.assertAlmostEqual(result["delta_percentage_points"], -10.0)

        with self.sessions() as db, patch(
            "app.services.outcome_scenarios.predict_frozen_model_input",
            side_effect=[
                {"status": "available", "reason_codes": [], "probability": assessment["probability"], "support_summary": {}},
                {"status": "available", "reason_codes": [], "probability": assessment["probability"], "support_summary": {}},
            ],
        ):
            result = simulate_outcome_scenario(
                db, user_id=user_id, content_id=content_id, analysis_id=analysis_id,
                assessment_digest=fingerprint(assessment), selected_topic_ids=["topic-fixture"],
                allow_synthetic_fixture=True,
            )
            self.assertEqual(result["delta_percentage_points"], 0.0)

    def test_evidence_copy_preserves_negative_and_uncertain_results(self):
        assessment = self.assess()
        recommendation = {
            "actionable_recommendations": {"items": [{
                "evidence_topic_id": "t1", "support_count": 7, "channel_count": 4,
            }, {
                "evidence_topic_id": "t2", "support_count": 6, "channel_count": 3,
            }]},
            "evidence_bundle": {"topic_comparisons": {"items": [{
                "evidence_topic_id": "t1", "as_of": "2026-10-08T00:00:00Z",
                "metrics": {"views": {
                    "status": "comparison_supported", "direction": "lower", "unit": "views",
                    "detected": {"count": 7, "median": 1000},
                    "not_detected": {"count": 8, "median": 2000},
                    "paired_channel_count": 4, "within_channel_median_difference": -1000,
                    "uncertainty": {"low": -1500, "high": -200},
                }},
            }, {
                "evidence_topic_id": "t2", "as_of": "2026-10-08T00:00:00Z",
                "metrics": {"views": {
                    "status": "comparison_uncertain", "direction": "higher", "unit": "views",
                    "detected": {"count": 6, "median": 1500},
                    "not_detected": {"count": 6, "median": 1400},
                    "paired_channel_count": 3, "within_channel_median_difference": 100,
                    "uncertainty": {"low": -300, "high": 500},
                }},
            }]}}
        }
        attach_outcome_evidence_explanations(recommendation, assessment)
        first, second = recommendation["actionable_recommendations"]["items"]
        self.assertIn("ต่ำกว่า", first["evidence_explanation"]["message_th"])
        self.assertIn("ไม่ใช่เหตุ", first["evidence_explanation"]["message_th"])
        self.assertIn("ยังสรุปความต่างไม่ได้", second["evidence_explanation"]["message_th"])

    def test_snapshot_is_saved_once_legacy_is_stable_and_revision_is_guarded(self):
        assessment = self.assess()
        recommendation = {"domain": self.record["accepted_category"],
                          "missing_keywords": [], "hook_keywords": [],
                          "recommended_duration": {}, "classification": self.classification(),
                          "outcome_assessment": assessment}
        with self.sessions() as db:
            user = db.query(User).filter_by(username="outcome-owner").one()
            saved = save_video_analysis_result(
                db, user=user, filename="snapshot.mp4", file_path="snapshot.mp4",
                transcript=self.record["transcript"], analysis_payload={}, nlp_result={},
                recommendation_payload=recommendation,
            )
            first = get_user_content_detail(db, user_id=user.user_id, content_id=saved["content_id"])
            db.query(OutcomeModel).filter_by(model_version="qualified-fixture-v1").update({OutcomeModel.is_active: False})
            db.commit()
            second = get_user_content_detail(db, user_id=user.user_id, content_id=saved["content_id"])
            self.assertEqual(first["outcome_assessment"], assessment)
            self.assertEqual(second["outcome_assessment"], assessment)
            legacy_content = UserContent(user_id=user.user_id, title="legacy")
            db.add(legacy_content)
            db.flush()
            db.add(AnalysisResult(content_id=legacy_content.content_id, summary="{}"))
            db.commit()
            left = get_user_content_detail(db, user_id=user.user_id, content_id=legacy_content.content_id)
            right = get_user_content_detail(db, user_id=user.user_id, content_id=legacy_content.content_id)
            self.assertEqual(left["outcome_assessment"], right["outcome_assessment"])
            self.assertEqual(left["outcome_assessment"]["status"], "legacy_not_assessed")
            db.query(OutcomeModel).filter_by(model_version="qualified-fixture-v1").update({OutcomeModel.is_active: True})
            db.commit()

        child = copy.deepcopy(assessment)
        child["model_id"] = int(assessment["model_id"]) + 1
        comparison = _outcome_revision_comparison(
            assessment, child,
            parent_context={"availability": "available"},
            child_context={"availability": "available"},
        )
        self.assertEqual(comparison["status"], "not_comparable")
        self.assertIsNone(comparison["delta_percentage_points"])
        missing_asr = _outcome_revision_comparison(
            assessment, assessment,
            parent_context={"availability": "available"},
            child_context={"availability": "unavailable"},
        )
        self.assertIn("asr_or_transcript_unassessable", missing_asr["reason_codes"])


if __name__ == "__main__":
    unittest.main()
