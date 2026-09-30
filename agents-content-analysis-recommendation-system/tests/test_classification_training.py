import hashlib
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.db import Base
from app.database.models import (
    ClassificationModel,
    DatasetCollectionRun,
    DatasetContent,
    ModelEvaluationMetric,
)
from app.services.classification_training import (
    UNKNOWN_LEAF_KEY,
    ClassificationModelSpec,
    ClassificationTrainingError,
    _resolve_sentence_transformer_model_path,
    activate_classification_model,
    classify_with_artifact,
    default_classification_model_specs,
    load_classification_artifact,
    predict_with_unknown,
    prepare_classification_dataset,
    train_and_evaluate_classification_models,
)
from app.services.classification import classify_text_domain
from app.services.dataset_contract import (
    SPLIT_STRATEGY,
    YOUTUBE_CC_LICENSE_NAME,
    YOUTUBE_CC_LICENSE_URL,
    channel_dataset_split,
)
from app.services.taxonomy import TAXONOMY_VERSION, taxonomy_path


HASH_A = hashlib.sha256(b"candidate artifact").hexdigest()
HASH_B = hashlib.sha256(b"review artifact").hexdigest()
HASH_C = hashlib.sha256(b"import batch").hexdigest()


class _ProbabilityEstimator:
    classes_ = np.asarray(["camera", "phone"], dtype=object)

    def predict_proba(self, texts):
        return np.asarray(
            [[0.55, 0.45] if "uncertain" in text else [0.05, 0.95] for text in texts]
        )


class ClassificationTrainingTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.run = DatasetCollectionRun(
            run_key=hashlib.sha256(b"training-run").hexdigest(),
            dataset_source="youtube_cc",
            dataset_version="youtube-cc-training-test-v1",
            status="reviewed",
            region_code="TH",
            languages_json='["th"]',
            query_config_json="{}",
        )
        self.db.add(self.run)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    @staticmethod
    def _channel_for_split(split, *, seed):
        index = 0
        while True:
            channel_id = f"channel-{seed}-{index}"
            actual, _group = channel_dataset_split(channel_id)
            if actual == split:
                return channel_id
            index += 1

    def _add_example(self, leaf_key, split, index, *, language="th"):
        path = taxonomy_path(leaf_key)
        channel_id = self._channel_for_split(split, seed=f"{leaf_key}-{split}-{index}")
        actual_split, creator_group_key = channel_dataset_split(channel_id)
        leaf_terms = {
            "phone": "smartphone mobile battery display camera android phone",
            "camera": "mirrorless camera lens photography sensor aperture camera",
            "unknown": "phone case charger cable tripod accessory protective cover",
        }
        transcript = " ".join([leaf_terms[leaf_key]] * 8) + f" sample {index}"
        youtube_id = f"{leaf_key}{split[:1]}{index:08d}"[:32]
        now = datetime.utcnow()
        self.db.add(
            DatasetContent(
                title=f"{leaf_key} review {index}",
                video_url=f"https://www.youtube.com/watch?v={youtube_id}",
                transcript=transcript,
                category=leaf_key,
                source_platform="youtube",
                dataset_source="youtube_cc",
                dataset_version="youtube-cc-training-test-v1",
                collection_run_id=self.run.collection_run_id,
                source_record_id=youtube_id,
                source_youtube_id=youtube_id,
                source_creator=f"Creator {channel_id}",
                source_channel_id=channel_id,
                source_category="28",
                source_subcategory=leaf_key,
                collection_query=f"{leaf_key} review",
                source_release_url=f"https://www.youtube.com/watch?v={youtube_id}",
                source_archive_sha256=HASH_A,
                source_annotation_path="data/reviews/training-test.csv",
                source_annotation_sha256=HASH_B,
                import_batch_id=HASH_C,
                taxonomy_version=TAXONOMY_VERSION,
                taxonomy_leaf_key=leaf_key,
                category_level_1=path["category_level_1"],
                category_level_2=path["category_level_2"],
                category_level_3=path["category_level_3"],
                language=language,
                verification_status="human_verified",
                label_source="human_review",
                license_name=YOUTUBE_CC_LICENSE_NAME,
                license_url=YOUTUBE_CC_LICENSE_URL,
                data_split=actual_split,
                split_strategy=SPLIT_STRATEGY,
                creator_group_key=creator_group_key,
                transcript_sha256=hashlib.sha256(transcript.encode()).hexdigest(),
                transcript_segment_count=8,
                transcript_start_seconds=0,
                transcript_end_seconds=180,
                transcript_window_seconds=300,
                transcript_source="youtube_public_caption",
                caption_type="manual",
                transcript_quality="good",
                reviewed_by="reviewer@example.test",
                reviewed_at=now,
                statistics_captured_at=now,
                license_verified_at=now,
                raw_metadata_json=json.dumps({"license": "creativeCommon"}),
                collection_strategy="classification_diverse",
                is_training_eligible=leaf_key != UNKNOWN_LEAF_KEY,
                is_keyword_recommendation_eligible=leaf_key != UNKNOWN_LEAF_KEY,
                is_duration_recommendation_eligible=leaf_key != UNKNOWN_LEAF_KEY,
                is_active=True,
                duration_seconds=180,
                published_at=now,
            )
        )

    def _seed_ready_two_leaf_dataset(self):
        for leaf_key in ("phone", "camera"):
            self._add_example(leaf_key, "train", 0, language="th")
            self._add_example(leaf_key, "train", 1, language="th")
            self._add_example(leaf_key, "validation", 2, language="th")
            self._add_example(leaf_key, "test", 3, language="th")
        self.db.commit()

    def _seed_covered_two_leaf_dataset(self):
        for leaf_key in ("phone", "camera"):
            for index in range(21):
                self._add_example(leaf_key, "train", index, language="th")
            for index in range(21, 26):
                self._add_example(leaf_key, "validation", index, language="th")
            for index in range(26, 30):
                self._add_example(leaf_key, "test", index, language="th")
        self.db.commit()

    def test_prepare_split_artifacts_group_channels_without_leakage(self):
        self._seed_ready_two_leaf_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            prepared = prepare_classification_dataset(
                self.db,
                artifact_root=temp_dir,
                required_leaf_keys=("phone", "camera"),
                minimum_samples_per_leaf=4,
            )
            manifest_path = Path(prepared.report["artifacts"]["manifest_path"])
            split_paths = {
                split: Path(details["path"])
                for split, details in prepared.report["artifacts"]["splits"].items()
            }
            creator_splits = {}
            for split, path in split_paths.items():
                for line in path.read_text(encoding="utf-8").splitlines():
                    row = json.loads(line)
                    creator_splits.setdefault(row["creator_group_key"], set()).add(split)

            self.assertTrue(prepared.report["ready"])
            self.assertEqual(prepared.report["channel_leakage_count"], 0)
            self.assertTrue(manifest_path.is_file())
            self.assertTrue(all(len(splits) == 1 for splits in creator_splits.values()))
            self.assertEqual(
                prepared.report["unknown_support"]["strategy"],
                "validation_selected_confidence_and_train_similarity",
            )
            self.assertFalse(
                prepared.report["unknown_support"]["uses_synthetic_training_rows"]
            )

    def test_incomplete_dataset_stops_before_creating_database_models(self):
        self._add_example("phone", "train", 0)
        self.db.commit()
        with tempfile.TemporaryDirectory() as temp_dir:
            result = train_and_evaluate_classification_models(
                self.db,
                artifact_root=temp_dir,
                model_version="not-ready-v1",
                embedding_model="phase22/test-model-not-cached",
                required_leaf_keys=("phone", "camera"),
                minimum_samples_per_leaf=4,
            )
        self.assertEqual(result["status"], "not_ready")
        self.assertFalse(result["dataset"]["ready"])
        self.assertEqual(self.db.query(ClassificationModel).count(), 0)
        self.assertEqual(self.db.query(ModelEvaluationMetric).count(), 0)

    def test_smoke_test_uses_incomplete_rows_and_is_never_promotion_eligible(self):
        self._seed_ready_two_leaf_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            result = train_and_evaluate_classification_models(
                self.db,
                artifact_root=temp_dir,
                model_version="smoke-v1",
                embedding_model="phase22/test-model-not-cached",
                required_leaf_keys=("phone", "camera"),
                minimum_samples_per_leaf=30,
                unknown_threshold=0.10,
                smoke_test=True,
            )
            models = self.db.query(ClassificationModel).all()
            best = next(
                item
                for item in result["models"]
                if item["model_id"] == result["best_model"]["model_id"]
            )
            prediction = classify_with_artifact(
                best["artifact_path"],
                title="Phone review",
                text="smartphone battery display camera android mobile",
            )
            renamed_prediction = classify_with_artifact(
                best["artifact_path"],
                title="1-final-copy.mp4",
                text="smartphone battery display camera android mobile",
            )

        self.assertEqual(result["status"], "smoke_test_evaluated")
        self.assertFalse(result["dataset"]["ready"])
        self.assertEqual(result["smoke_test_scope"]["dataset_sample_count"], 8)
        self.assertFalse(result["smoke_test_scope"]["promotion_eligible"])
        self.assertEqual(len(models), 2)
        self.assertTrue(all(model.status == "smoke_test_only" for model in models))
        self.assertTrue(all(not model.is_active for model in models))
        self.assertTrue(
            all(not item["qualification"]["passed"] for item in result["models"])
        )
        self.assertTrue(
            all(
                item["qualification"]["blocked_reason"]
                == "smoke_test_incomplete_dataset"
                for item in result["models"]
            )
        )
        self.assertTrue(prediction["smoke_test_only"])
        self.assertEqual(prediction, renamed_prediction)
        self.assertIn(prediction["taxonomy_leaf_key"], {"phone", "camera", "unknown"})
        reload_metrics = (
            self.db.query(ModelEvaluationMetric)
            .filter(ModelEvaluationMetric.metric_name == "reload_classify_passed")
            .all()
        )
        self.assertEqual(len(reload_metrics), 2)
        self.assertTrue(all(item.metric_value == 1.0 for item in reload_metrics))

    def test_benchmark_persists_all_metrics_but_never_activates_automatically(self):
        self._seed_covered_two_leaf_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            result = train_and_evaluate_classification_models(
                self.db,
                artifact_root=temp_dir,
                model_version="benchmark-v1",
                embedding_model="phase22/test-model-not-cached",
                required_leaf_keys=("phone", "camera"),
                minimum_samples_per_leaf=4,
                unknown_threshold=0.10,
                promotion_threshold=0.80,
                enforce_phase22_gate=False,
            )
            models = self.db.query(ClassificationModel).all()
            metrics = self.db.query(ModelEvaluationMetric).all()
            artifact = load_classification_artifact(models[0].artifact_path)

        self.assertEqual(result["status"], "evaluated")
        self.assertEqual(result["database_models_created"], 3)
        self.assertEqual(len(models), 3)
        self.assertTrue(all(not model.is_active for model in models))
        self.assertTrue(all(model.status == "evaluated_below_threshold" for model in models))
        self.assertTrue(all("scope_validation_not_passed" in row["qualification"]["blocked_reasons"]
                            for row in result["models"]))
        self.assertEqual(artifact["fit_split"], "train")
        self.assertEqual(artifact["scope_policy"]["unknown_validation_count"], 0)
        self.assertTrue(
            all(
                model.status in {"qualified", "evaluated_below_threshold"}
                for model in models
            )
        )
        self.assertEqual(artifact["unknown_leaf_key"], UNKNOWN_LEAF_KEY)
        self.assertEqual(set(artifact["labels"]), {"phone", "camera"})
        self.assertGreater(len(metrics), 0)
        metric_names = {metric.metric_name for metric in metrics}
        self.assertTrue({"all", "th"}.issubset({item.language for item in metrics}))
        self.assertNotIn("en", {item.language for item in metrics})
        self.assertTrue(
            {
                "accuracy",
                "precision_macro",
                "recall_macro",
                "f1_macro",
                "confusion_matrix",
                "passed",
            }.issubset(metric_names)
        )
        confusion = next(
            metric for metric in metrics if metric.metric_name == "confusion_matrix"
        )
        self.assertIn("unknown", json.loads(confusion.details)["labels"])
        self.assertTrue(
            all(
                fold["channel_overlap_count"] == 0
                for model_result in result["models"]
                for fold in model_result["grouped_cv"]["folds"]
            )
        )
        self.assertIn("grouped_cv", {metric.dataset_split for metric in metrics})
        self.assertIn("validation", {metric.dataset_split for metric in metrics})
        self.assertEqual(len(result["model_catalog"]), 4)
        self.assertEqual(len(result["skipped_models"]), 1)
        self.assertEqual(
            result["skipped_models"][0]["model_key"],
            "taxonomy-multilingual-embeddings-logreg",
        )
        logistic_result = next(
            item
            for item in result["models"]
            if item["model_key"] == "taxonomy-tfidf-logreg-tuned"
        )
        self.assertIn(
            logistic_result["tuning"]["selected_parameters"]["C"],
            {0.5, 1.0, 2.0, 4.0},
        )
        self.assertEqual(len(logistic_result["tuning"]["candidates"]), 4)
        self.assertTrue(
            all(
                "grouped_cv_minimum_class_recall"
                in model_result["qualification"]["checks"]
                for model_result in result["models"]
            )
        )

    def test_cached_embedding_model_resolves_to_a_local_snapshot_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            resolved = _resolve_sentence_transformer_model_path(
                temp_dir,
                cache_folder=None,
                local_files_only=True,
            )

        self.assertEqual(resolved, str(Path(temp_dir).resolve()))

    def test_one_failed_optional_model_does_not_discard_other_results(self):
        self._seed_ready_two_leaf_dataset()

        def fail_factory():
            raise RuntimeError("optional model failed")

        baseline_specs = default_classification_model_specs(
            embedding_model="phase22/test-model-not-cached"
        )[:2]
        specs = (
            *baseline_specs,
            ClassificationModelSpec(
                model_key="optional-failing-model",
                model_type="test_failure",
                description="Test-only model failure",
                factory=fail_factory,
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            result = train_and_evaluate_classification_models(
                self.db,
                artifact_root=temp_dir,
                model_version="partial-success-v1",
                required_leaf_keys=("phone", "camera"),
                minimum_samples_per_leaf=4,
                unknown_threshold=0.10,
                promotion_threshold=0.10,
                enforce_phase22_gate=False,
                model_specs=specs,
            )

        self.assertEqual(result["database_models_created"], 2)
        self.assertEqual(self.db.query(ClassificationModel).count(), 2)
        failed = next(
            item
            for item in result["skipped_models"]
            if item["model_key"] == "optional-failing-model"
        )
        self.assertEqual(failed["status"], "failed_during_benchmark")
        self.assertIn("optional model failed", failed["reason"])

    def test_low_confidence_prediction_becomes_unknown(self):
        labels, confidences = predict_with_unknown(
            _ProbabilityEstimator(),
            ["uncertain topic", "clear phone"],
            unknown_threshold=0.60,
        )
        self.assertEqual(labels, [UNKNOWN_LEAF_KEY, "phone"])
        self.assertEqual(confidences, [0.55, 0.95])

    def test_deleted_holdout_still_blocks_training_copy(self):
        self._seed_ready_two_leaf_dataset()
        reserved = self.db.query(DatasetContent).filter_by(data_split="test", taxonomy_leaf_key="phone").one()
        reserved.deleted_at = datetime.utcnow()
        reserved.is_active = False
        training = self.db.query(DatasetContent).filter_by(data_split="train", taxonomy_leaf_key="phone").first()
        training.transcript = "\n" + reserved.transcript.upper().replace(" ", "\t")
        training.transcript_sha256 = hashlib.sha256(training.transcript.encode()).hexdigest()
        self.db.commit()
        report = prepare_classification_dataset(self.db, required_leaf_keys=("phone", "camera"),
                                                minimum_samples_per_leaf=2).report
        self.assertFalse(report["ready"])
        self.assertIn("transcript", [r["field"] for r in report["partition_conflicts"]])
        with tempfile.TemporaryDirectory() as temp_dir:
            result = train_and_evaluate_classification_models(
                self.db, artifact_root=temp_dir, smoke_test=True,
                required_leaf_keys=("phone", "camera"), minimum_samples_per_leaf=2)
        self.assertEqual(result["status"], "not_ready")
        self.assertEqual(result["database_models_created"], 0)

    def test_unknown_validation_cannot_overlap_training_channel(self):
        self._seed_ready_two_leaf_dataset()
        self._add_example("unknown", "validation", 80)
        self.db.commit()
        outside = self.db.query(DatasetContent).filter_by(taxonomy_leaf_key="unknown").one()
        outside.source_channel_id = self.db.query(DatasetContent).filter_by(data_split="train").first().source_channel_id
        self.db.commit()
        report = prepare_classification_dataset(self.db, required_leaf_keys=("phone", "camera"),
                                                minimum_samples_per_leaf=2).report
        self.assertFalse(report["ready"])
        self.assertIn("source_channel_id", [r["field"] for r in report["partition_conflicts"]])

    def test_unknown_group_must_match_its_actual_source_channel(self):
        self._seed_ready_two_leaf_dataset()
        self._add_example("unknown", "validation", 80)
        self.db.commit()
        outside = self.db.query(DatasetContent).filter_by(taxonomy_leaf_key="unknown").one()
        outside.creator_group_key = "0" * 64
        self.db.commit()
        report = prepare_classification_dataset(self.db, required_leaf_keys=("phone", "camera"),
                                                minimum_samples_per_leaf=2).report
        self.assertFalse(report["ready"])
        self.assertFalse(report["partition_integrity_passed"])
        self.assertIn(outside.dataset_id, report["invalid_partition_assignments"])

    def test_out_of_scope_rows_are_evaluation_only_and_phase22_gate_blocks(self):
        self._seed_ready_two_leaf_dataset()
        self._add_example(UNKNOWN_LEAF_KEY, "test", 99)
        self.db.commit()
        with tempfile.TemporaryDirectory() as temp_dir:
            prepared = prepare_classification_dataset(
                self.db,
                artifact_root=temp_dir,
                required_leaf_keys=("phone", "camera"),
                minimum_samples_per_leaf=4,
            )
            result = train_and_evaluate_classification_models(
                self.db,
                artifact_root=temp_dir,
                model_version="phase22-gated-v1",
                embedding_model="phase22/test-model-not-cached",
                required_leaf_keys=("phone", "camera"),
                minimum_samples_per_leaf=4,
                unknown_threshold=0.60,
                promotion_threshold=0.10,
            )

        self.assertEqual(len(prepared.examples), 8)
        self.assertEqual(len(prepared.out_of_scope_examples), 1)
        self.assertEqual(
            prepared.out_of_scope_examples[0].leaf_key,
            UNKNOWN_LEAF_KEY,
        )
        self.assertFalse(prepared.report["phase22_ready"])
        self.assertEqual(
            prepared.report["phase22"]["out_of_scope"]["sample_count"],
            1,
        )
        self.assertEqual(
            prepared.report["artifacts"]["out_of_scope"]["sample_count"],
            1,
        )
        self.assertTrue(
            all(model["out_of_scope"]["sample_size"] == 1 for model in result["models"])
        )
        self.assertTrue(
            all(
                "phase22_collection_not_ready" in model["qualification"]["blocked_reasons"]
                for model in result["models"]
            )
        )
        self.assertTrue(
            all(model["status"] == "evaluated_below_threshold" for model in result["models"])
        )
        persisted_splits = {
            metric.dataset_split
            for metric in self.db.query(ModelEvaluationMetric).all()
        }
        self.assertIn("out_of_scope", persisted_splits)

    def test_qualified_model_can_be_activated_and_used_by_runtime(self):
        self._seed_covered_two_leaf_dataset()
        for index in range(10):
            self._add_example("unknown", "validation", 100 + index)
            self._add_example("unknown", "test", 200 + index)
        self.db.commit()
        with tempfile.TemporaryDirectory() as temp_dir:
            result = train_and_evaluate_classification_models(
                self.db,
                artifact_root=temp_dir,
                model_version="runtime-v1",
                embedding_model="phase22/test-model-not-cached",
                required_leaf_keys=("phone", "camera"),
                minimum_samples_per_leaf=30,
                unknown_threshold=0.10,
                promotion_threshold=0.50,
                enforce_phase22_gate=False,
            )
            qualified = next(
                item for item in result["models"] if item["status"] == "qualified"
            )
            activation = activate_classification_model(
                self.db,
                int(qualified["model_id"]),
            )
            prediction = classify_text_domain(
                self.db,
                title="Phone review",
                text="smartphone mobile battery display android phone",
            )

        self.assertTrue(activation["is_active"])
        self.assertEqual(prediction["method"], "trained_tfidf_classifier")
        self.assertEqual(prediction["model_id"], qualified["model_id"])
        self.assertEqual(prediction["taxonomy_leaf_key"], "phone")
        self.assertIn("phone", prediction["candidates"][0]["domain"])

    def test_smoke_test_model_cannot_be_activated(self):
        self._seed_ready_two_leaf_dataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            result = train_and_evaluate_classification_models(
                self.db,
                artifact_root=temp_dir,
                model_version="blocked-smoke-v1",
                embedding_model="phase22/test-model-not-cached",
                required_leaf_keys=("phone", "camera"),
                minimum_samples_per_leaf=30,
                unknown_threshold=0.10,
                smoke_test=True,
            )
            with self.assertRaises(ClassificationTrainingError):
                activate_classification_model(
                    self.db,
                    int(result["best_model"]["model_id"]),
                )


if __name__ == "__main__":
    unittest.main()
