import copy
import json
import unittest
from types import SimpleNamespace
from datetime import datetime
from pathlib import Path

from app.services.outcome_dataset import freeze_manifest
from app.services.outcome_evidence import _comparison_message
from app.services.outcome_independence import sealed_holdout_check
from app.services.outcome_prediction_readiness import data_use_gate
from app.services.outcome_support import qualified_scope_reasons
from app.services.topic_comparisons import _metric_comparison
from tests.test_outcome_dataset import confirmed_data_use, record

PROTOCOL = json.loads((Path(__file__).resolve().parents[1] /
    "docs/implementation/outcome-prediction-protocol-v1.json").read_text(encoding="utf-8"))


class OutcomeReviewRegressionTests(unittest.TestCase):
    def test_explicit_denial_missing_and_withdrawn_permissions(self):
        rights = confirmed_data_use()
        rights["status"] = "withdrawn"
        self.assertFalse(data_use_gate(rights, "audit")["allowed"])
        for purpose in ("training", "serving"):
            for value in (False, None):
                rights = confirmed_data_use()
                rights["decision"][f"real_{purpose}_allowed"] = value
                self.assertFalse(data_use_gate(rights, purpose)["allowed"])
            rights = confirmed_data_use()
            rights["status"] = "withdrawn"
            self.assertFalse(data_use_gate(rights, purpose)["allowed"])
        from app.services.outcome_training_fixture import synthetic_data_use_record
        rights = synthetic_data_use_record()
        self.assertFalse(data_use_gate(rights, "serving")["allowed"])
        self.assertTrue(data_use_gate(rights, "serving", allow_synthetic_fixture=True)["allowed"])

    def test_normalized_and_transitive_duplicates_never_cross_partitions(self):
        rows = [record(1, role="fit", channel="a", transcript="Review CAMERA, low light"),
                record(2, role="tuning", channel="b", transcript="review camera low light"),
                record(3, role="tuning", channel="b", transcript="Different clip")]
        result = freeze_manifest(rows, cutoff=datetime(2026, 10, 1), protocol=PROTOCOL,
                                 data_use_record=confirmed_data_use())
        self.assertIsNone(result["manifest"])
        self.assertEqual(len(result["excluded"]), 3)
        self.assertTrue(all("identity_crosses_outcome_partitions" in row["reason_codes"]
                            for row in result["excluded"]))
        rows = [record(4), record(5, role="tuning")]
        for row in rows:
            row["near_duplicate_group_key"] = "reviewed-near-duplicate-1"
        result = freeze_manifest(rows, cutoff=datetime(2026, 10, 1), protocol=PROTOCOL,
                                 data_use_record=confirmed_data_use())
        self.assertIsNone(result["manifest"])

    def test_fresh_count_requires_sealed_frozen_provenance(self):
        row = record(1, role="independent_test", source_split="test")
        row.update(outcome_holdout_status="fresh_confirmed", outcome_prior_use_reviewed=True)
        frozen = freeze_manifest([row], cutoff=datetime(2026, 10, 1), protocol=PROTOCOL,
                                 data_use_record=confirmed_data_use())["manifest"]
        self.assertEqual(sealed_holdout_check(frozen)["fresh_count"], 1)
        result = sealed_holdout_check(frozen, prior_use={"by_dataset_id": {"1": ["classification_test"]}})
        self.assertEqual(result["fresh_count"], 0)
        self.assertFalse(sealed_holdout_check(None)["valid"])

    def test_holdout_near_duplicate_reference_and_invalid_live_metadata_are_blocked(self):
        row = record(1, role="independent_test", source_split="test")
        row.update(outcome_holdout_status="fresh_confirmed", outcome_prior_use_reviewed=True,
                   near_duplicate_group_key="reviewed-pair")
        frozen = freeze_manifest([row], cutoff=datetime(2026, 10, 1), protocol=PROTOCOL,
                                 data_use_record=confirmed_data_use())["manifest"]
        reference = SimpleNamespace(source_youtube_id="other", source_channel_id="other-channel",
            creator_group_key="other-creator", transcript_sha256="other-hash", transcript="Another review",
            raw_metadata_json=json.dumps({"outcome_near_duplicate_group_key": "reviewed-pair"}))
        result = sealed_holdout_check(frozen, reference_rows=[reference])
        self.assertIn("independent_test_reference_overlap", result["reason_codes"])
        live = SimpleNamespace(**{key: row.get(key) for key in
            ("source_youtube_id", "source_channel_id", "creator_group_key", "transcript_sha256", "transcript")},
            is_active=True, deleted_at=None, data_split="test", raw_metadata_json="broken JSON")
        result = sealed_holdout_check(frozen, current_rows={1: live})
        self.assertEqual(result["fresh_count"], 0)
        self.assertIn("holdout_provenance_unreadable", result["reason_codes"])

    def test_qualified_scopes_are_actual_contexts_not_dimension_names(self):
        context = {"accepted_category": "phone", "confirmed_format": "long_form",
                   "frozen_age_context": "age_30_90d", "view_metric_version": "v1"}
        scopes = {"schema_version": "outcome-qualified-scopes-v1",
                  "contexts": [dict(context, qualified=True)]}
        self.assertEqual(qualified_scope_reasons(scopes, context), [])
        self.assertTrue(qualified_scope_reasons(scopes, dict(context, accepted_category="camera")))
        self.assertTrue(qualified_scope_reasons(["overall", "category", "confirmed_format", "age_context"]))
        scopes["contexts"][0]["qualified"] = False
        self.assertTrue(qualified_scope_reasons(scopes, context))

    def test_simpson_paradox_explanation_uses_paired_difference(self):
        rows = []
        for channel in range(10):
            low = channel < 5
            base = 100 if low else 10000
            for status, count, views in (("detected", 10 if low else 1, base + 10 + channel),
                                         ("not_detected", 1 if low else 10, base)):
                for number in range(count):
                    rows.append({"video_id": f"{channel}-{status}-{number}", "channel_id": str(channel),
                                 "stratum": ["camera", "long_form", "30_90d", "v2"],
                                 "comparison_eligible": True, "exclusion_reasons": [],
                                 "topic_status": status, "metrics": {"views": views}})
        metric = _metric_comparison(rows, "views")
        self.assertEqual(metric["direction"], "higher")
        self.assertLess(metric["detected"]["median"], metric["not_detected"]["median"])
        result = _comparison_message({"metrics": {"views": metric}}, {})
        self.assertIn("ผลต่างแบบจับคู่", result["message_th"])
        self.assertNotIn("112 ซึ่งสูงกว่า", result["message_th"])
        self.assertFalse(result["causal_claim"])
        negative = copy.deepcopy(metric)
        negative.update(direction="lower", within_channel_median_difference=-14.5)
        self.assertIn("ต่ำกว่า", _comparison_message({"metrics": {"views": negative}}, {})["message_th"])


if __name__ == "__main__":
    unittest.main()
