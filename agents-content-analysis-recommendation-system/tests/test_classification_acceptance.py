import copy
import hashlib
import unittest
from dataclasses import replace
from unittest.mock import MagicMock, patch

import numpy as np

from app.services.classification_acceptance import (
    POLICY_VERSION, acceptance_summary, apply_acceptance_policy,
    evaluate_acceptance_policy, fit_acceptance_policy, partition_conflicts,
)
from app.services.classification_training import TrainingExample, classify_with_artifact, _evaluate_out_of_scope
from app.services.recommendation import build_recommendation_from_analysis_data
from app.schemas.classification import ClassificationResponse
from app.schemas.recommendation import RecommendationAnalysisResponse


class ConfidentEstimator:
    classes_ = np.asarray(["phone", "camera", "laptop"])

    def predict_proba(self, texts):
        values = []
        for text in texts:
            index = 1 if "photography" in text else 2 if "notebook" in text else 0
            row = [0.005, 0.005, 0.005]
            row[index] = 0.99
            values.append(row)
        return np.asarray(values)

    def predict(self, texts):
        return self.classes_[self.predict_proba(texts).argmax(axis=1)]


TEXTS = {
    "phone": "smartphone mobile android battery display charging chip camera",
    "camera": "photography mirrorless lens aperture shutter optical sensor autofocus",
    "laptop": "notebook portable computer windows trackpad processor ram cooling",
    "unknown": "mechanical keyboard switches keycaps typing sound wireless headset mouse dpi",
}


def example(label, split, index):
    text = (TEXTS[label] + " ") * 3 + f" {split} {index}"
    identity = f"{label}-{split}-{index}"
    return TrainingExample(dataset_id=index, source_record_id=identity, source_youtube_id=identity,
                           source_channel_id=identity, creator_group_key=hashlib.sha256(identity.encode()).hexdigest(),
                           dataset_version="unit-test-only", split=split, language="th", leaf_key=label,
                           title="Filename is not evidence", transcript=text,
                           transcript_sha256=hashlib.sha256(text.encode()).hexdigest())


class ClassificationAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.labels = ("phone", "camera", "laptop")
        self.train = [example(label, "train", number * 10 + i)
                      for number, label in enumerate(self.labels) for i in range(3)]
        self.validation = [example(label, "validation", 100 + number * 10 + i)
                           for number, label in enumerate(self.labels) for i in range(3)]
        self.outside = [example("unknown", "validation", 200 + i) for i in range(10)]
        self.estimator = ConfidentEstimator()

    def fit(self):
        return fit_acceptance_policy(self.estimator, self.train, self.validation, self.outside,
                                     labels=self.labels, confidence_threshold=0.6)

    def test_validation_selects_rejection_even_when_wrong_class_confidence_is_high(self):
        policy = self.fit()
        self.assertEqual(policy["status"], "validated")
        self.assertGreater(policy["similarity_threshold"], 0)
        heldout = [example(label, "test", 300 + i) for i, label in enumerate((*self.labels, "unknown"))]
        report = evaluate_acceptance_policy(policy, self.estimator, heldout, labels=self.labels)
        self.assertEqual(report["predictions"], ["phone", "camera", "laptop", "unknown"])
        self.assertEqual(report["raw_predictions"][-1], "phone")
        self.assertEqual(report["confidences"][-1], 0.99)
        self.assertEqual(report["metrics"]["unknown_recall"], 1)

    def test_test_rows_cannot_be_passed_to_calibration(self):
        with self.assertRaisesRegex(ValueError, "never test"):
            fit_acceptance_policy(self.estimator, self.train, self.validation,
                                  [replace(row, split="test") for row in self.outside],
                                  labels=self.labels, confidence_threshold=0.6)

    def test_validation_never_fits_the_classifier(self):
        self.estimator.fit = MagicMock(side_effect=AssertionError("Do not refit on validation"))
        policy = self.fit()
        self.estimator.fit.assert_not_called()
        self.assertEqual(policy["fit_dataset_ids"], [r.dataset_id for r in self.train])
        self.assertNotIn("mechanical", policy["vectorizer"].vocabulary_)

    def test_no_unknown_examples_cannot_create_a_validated_policy(self):
        self.outside = []
        policy = self.fit()
        self.assertEqual(policy["status"], "not_ready")
        self.assertIsNone(policy["similarity_threshold"])
        self.assertIn("insufficient_unknown_validation", policy["reasons"])
        self.assertNotIn("vectorizer", policy)

    def test_one_channel_is_not_sufficient_unknown_coverage(self):
        self.outside = [replace(r, source_channel_id="one-channel") for r in self.outside]
        self.assertIn("insufficient_unknown_validation_channels", self.fit()["reasons"])

    def test_overlapping_channel_is_blocked_even_between_different_labels(self):
        self.outside[0] = replace(self.outside[0], source_channel_id=self.train[0].source_channel_id)
        with self.assertRaisesRegex(ValueError, "overlaps"):
            self.fit()

    def test_whitespace_and_case_changes_do_not_hide_transcript_leakage(self):
        duplicate = replace(self.outside[0], transcript="\n" + self.train[0].transcript.upper().replace(" ", "\t"))
        conflicts = partition_conflicts([self.train[0], duplicate])
        self.assertIn("transcript", [row["field"] for row in conflicts])

    def test_unvalidated_model_abstains_without_changing_raw_confidence(self):
        payload = {"estimator": self.estimator, "model_key": "test", "model_version": "test-v1",
                   "unknown_threshold": 0.6, "unknown_leaf_key": "unknown"}
        with patch("app.services.classification_training.load_classification_artifact", return_value=payload):
            prediction = classify_with_artifact("unused", text=TEXTS["unknown"], title="Phone.mp4")
        self.assertEqual(prediction["raw_taxonomy_leaf_key"], "phone")
        self.assertEqual(prediction["taxonomy_leaf_key"], "unknown")
        self.assertEqual(prediction["confidence"], 0.99)
        self.assertEqual(prediction["acceptance"]["reason"], "scope_validation_unavailable")

    def test_explicit_legacy_diagnostic_mode_is_marked_not_validated(self):
        predictions, decisions = apply_acceptance_policy(None, ["text"], ["phone"], [0.99],
                                                         require_validation=False)
        self.assertEqual(predictions, ["phone"])
        self.assertFalse(decisions[0]["accepted"])
        self.assertFalse(decisions[0]["enforced"])

    def test_acceptance_never_assigns_another_known_category(self):
        policy = self.fit()
        result, _ = apply_acceptance_policy(policy, [TEXTS["camera"]], ["phone"], [0.99])
        self.assertEqual(result, ["unknown"])

    def test_corrupt_policy_abstains(self):
        for policy in (None, {"status": "validated"}, {"version": "unrecognized"}):
            with self.subTest(policy=policy):
                result, _ = apply_acceptance_policy(policy, [TEXTS["phone"]], ["phone"], [0.99])
                self.assertEqual(result, ["unknown"])

    def test_missing_threshold_or_labels_abstains_without_runtime_error(self):
        policy = self.fit()
        for field in ("confidence_threshold", "similarity_threshold", "labels"):
            with self.subTest(field=field):
                malformed = {key: value for key, value in policy.items() if key != field}
                result, _ = apply_acceptance_policy(malformed, [TEXTS["phone"]], ["phone"], [0.99])
                self.assertEqual(result, ["unknown"])

    def test_unvalidated_blanket_withholding_is_not_reported_as_unknown_accuracy(self):
        report = _evaluate_out_of_scope(self.estimator, [example("unknown", "test", 800)],
                                        unknown_threshold=0.6, scope_policy={"status": "not_ready"})
        self.assertEqual(report["status"], "withheld_unvalidated_policy")
        self.assertIsNone(report["unknown_recall"])
        self.assertIsNone(report["false_accept_rate"])

    def test_evaluation_does_not_retune_policy_on_test(self):
        policy = self.fit()
        before = copy.deepcopy(acceptance_summary(policy))
        evaluate_acceptance_policy(policy, self.estimator, [example("unknown", "test", 800)], labels=self.labels)
        self.assertEqual(before, acceptance_summary(policy))

    def test_unknown_never_queries_category_references_or_trend_ideas(self):
        with patch("app.services.recommendation.build_dataset_profile_for_domain") as profile, \
                patch("app.services.current_trend_ideas.build_current_trend_ideas") as trends:
            recommendation = build_recommendation_from_analysis_data(
                MagicMock(), domain="unknown", user_keywords=["switch"],
                dimension_status=[{"name": "battery life", "status": "missing"}],
                hook_terms=[], transcript=TEXTS["unknown"])
        profile.assert_not_called()
        trends.assert_not_called()
        self.assertEqual(recommendation["status"], "withheld_unknown")
        for field in ("missing_keywords", "hook_keywords", "missing_dimensions"):
            self.assertEqual(recommendation[field], [])
        self.assertEqual(recommendation["dataset_profile"]["sample_size"], 0)
        self.assertIsNone(recommendation["recommended_duration"]["recommended_seconds"])
        serialized = RecommendationAnalysisResponse.model_validate(recommendation).model_dump()
        self.assertEqual(serialized["status"], "withheld_unknown")

    def test_api_schema_preserves_raw_prediction_and_acceptance_evidence(self):
        payload = {"domain": "unknown", "confidence": 0.99, "method": "trained_tfidf_classifier",
                   "rule_domain": "mouse", "source": "youtube", "profile_limit": 116, "candidates": [],
                   "taxonomy_leaf_key": "unknown", "is_unknown": True, "model_id": 14,
                   "raw_taxonomy_leaf_key": "phone", "acceptance": {"reason": "scope_validation_unavailable",
                   "accepted": False, "enforced": True, "policy_version": POLICY_VERSION}}
        serialized = ClassificationResponse.model_validate(payload).model_dump()
        self.assertEqual(serialized["acceptance"], payload["acceptance"])
        self.assertEqual(serialized["raw_taxonomy_leaf_key"], "phone")
        self.assertEqual(serialized["model_id"], 14)


if __name__ == "__main__":
    unittest.main()
