import unittest

from app.services.analysis_evaluation import (
    audit_recommendation, classification_metrics, diagnose_transcript_pair,
    human_review_summary, overlap_audit, scoring_exclusions,
)


class AnalysisEvaluationTests(unittest.TestCase):
    def test_asr_cause_requires_a_person_to_verify_audio_and_label(self):
        result = diagnose_transcript_pair("speech text", {}, lambda text: {"taxonomy_leaf_key": "phone"})
        self.assertEqual(result["diagnosis"], "awaiting_audio_verified_transcript")
        self.assertIsNone(result["verified_transcript_prediction"])

    def test_verified_transcript_comparison_separates_remaining_classifier_error(self):
        review = {"expected_label": "unknown", "label_reviewed_by": "reviewer",
                  "transcript_reviewed_by": "reviewer", "listened_to_audio": True,
                  "verified_transcript": "keyboard switches"}
        result = diagnose_transcript_pair("noisy text", review, lambda text: {"taxonomy_leaf_key": "phone"})
        self.assertEqual(result["diagnosis"], "classification_error_remains_on_verified_text")
        result = diagnose_transcript_pair("noisy text", review, lambda text: {
            "taxonomy_leaf_key": "unknown" if text == "keyboard switches" else "phone"})
        self.assertEqual(result["diagnosis"], "prediction_sensitive_to_transcription")
        self.assertFalse(result["is_new_test"])

    def test_empty_is_unknown_not_perfect_accuracy(self):
        metrics = classification_metrics([])
        self.assertEqual(metrics["sample_size"], 0)
        self.assertIsNone(metrics["accuracy"])
        self.assertIsNone(metrics["unknown_recall"])

    def test_accuracy_f1_abstention_and_unknown_are_separate(self):
        rows = [{"expected_label": a, "predicted_label": b, "exclusions": []}
                for a, b in [("phone", "phone"), ("laptop", "unknown"), ("unknown", "phone")]]
        rows.append({"expected_label": "phone", "predicted_label": "phone", "exclusions": ["duplicate"]})
        metrics = classification_metrics(rows)
        self.assertEqual(metrics["sample_size"], 3)
        self.assertAlmostEqual(metrics["accuracy"], 1 / 3)
        self.assertAlmostEqual(metrics["macro_f1"], 2 / 9)
        self.assertEqual(metrics["unknown_recall"], 0)

    def test_failed_jobs_cannot_make_a_partial_run_look_perfect(self):
        metrics = classification_metrics([
            {"expected_label": "phone", "predicted_label": "phone", "exclusions": []},
            {"expected_label": "camera", "error": "decode failed", "exclusions": ["analysis_not_completed"]},
        ])
        self.assertIsNone(metrics["accuracy"])
        self.assertEqual(metrics["failed_case_count"], 1)

    def test_overlap_checks_channel_video_and_normalized_transcript(self):
        pool = [{"dataset_id": 1, "source_youtube_id": "same", "transcript": "Battery LIFE",
                 "source_channel_id": "channel", "evaluation_pool": "reference"}]
        audit = overlap_audit({"source_youtube_id": "same", "source_channel_id": "channel"}, "battery life", pool)
        self.assertEqual(set(audit[0]["reasons"]), {"source_youtube_id", "source_channel_id", "exact_transcript"})

    def test_near_copy_is_flagged_not_declared_independent(self):
        text = "phone screen brightness sensor battery charging processor " * 12
        audit = overlap_audit({}, text + " end", [{"transcript": text, "dataset_id": 5}])
        self.assertIn("near_transcript_requires_review", audit[0]["reasons"])
        self.assertFalse(overlap_audit({}, "generic short text", [{"transcript": "other short text"}]))

    def test_filename_does_not_supply_label_or_provenance(self):
        case = {"video_path": "phone.mp4", "role": "regression"}
        reasons = scoring_exclusions(case, [], duplicate=True)
        self.assertIn("human_label_missing", reasons)
        self.assertIn("regression_not_new_holdout", reasons)
        self.assertIn("duplicate_media", reasons)
        self.assertIn("source_identity_missing", reasons)
        case = {"role": "heldout", "expected_label": "camera", "label_reviewed_by": "r1",
                "independence_confirmed_by": "r1", "source_kind": "self_recorded",
                "provenance_note": "Recorded locally after the model freeze, never imported"}
        self.assertEqual(scoring_exclusions(case, []), [])
        self.assertIn("training_or_reference_overlap", scoring_exclusions(case, [{"dataset_id": 1}]))

    def test_human_review_requires_actual_reviewer_and_matching_output(self):
        key = {"case_id": "test-1", "output_sha256": "abc", "lane": "missing_keywords", "index": "0"}
        incomplete = {**key, "reviewer": ""}
        self.assertIsNone(human_review_summary([incomplete], [key])["pass_rates"]["actionable"])
        complete = {**key, "reviewer": "r1", "relevant": "1", "not_already_covered": "1",
                    "evidence_correct": "1", "actionable": "0"}
        summary = human_review_summary([complete, complete, {**complete, "output_sha256": "stale"}], [key])
        self.assertEqual(summary["reviewed"], 1)
        self.assertEqual(summary["rejected_rows"], 2)
        self.assertEqual(summary["pass_rates"]["actionable"], 0)
        self.assertEqual(summary["engagement_effect"], "not_measured")

    def test_structural_audit_catches_synonym_repetition_and_missing_evidence(self):
        result = {"cleaned_transcript": "Snapdragon chip processor", "recommendation": {
            "domain": "phone", "hook_keywords": [{"keyword": "dimensity", "score": 0}],
        }}
        issues = audit_recommendation(result, [])[0]["structural_issues"]
        self.assertIn("already_mentioned_or_synonym", issues)
        self.assertIn("no_dataset_evidence", issues)

    def test_structural_audit_rejects_wrong_rows_and_frequencies(self):
        item = {"keyword": "battery life", "supporting_dataset_row_ids": [9], "support_count": 1,
                "total_frequency": 100, "supporting_examples": [{"dataset_id": 8}]}
        result = {"transcript": "camera", "recommendation": {"domain": "phone", "missing_keywords": [item]}}
        issues = audit_recommendation(result, [{"dataset_id": 9, "taxonomy_leaf_key": "camera", "data_split": "test"}])[0]["structural_issues"]
        self.assertIn("invalid_reference_row", issues)
        self.assertIn("invalid_total_frequency", issues)
        self.assertIn("example_not_in_support", issues)


if __name__ == "__main__":
    unittest.main()
