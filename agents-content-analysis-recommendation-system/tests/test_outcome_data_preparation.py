import argparse
import copy
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.prepare_outcome_data_review import (
    parse_cutoff, partition_minimums, prepare_review, write_csv,
)
from tests.test_outcome_dataset import record

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = json.loads((ROOT / "docs/implementation/outcome-prediction-protocol-v1.json").read_text(encoding="utf-8"))
CUTOFF = datetime(2026, 10, 12, tzinfo=timezone.utc)


def review(records, selected_ids=()):
    return prepare_review(records, selected_ids=set(selected_ids), cutoff=CUTOFF,
                          protocol=PROTOCOL, training_gate={"allowed": False})


class OutcomeDataPreparationTests(unittest.TestCase):
    def test_owner_selection_overrides_diverse_label_without_mutation(self):
        source = record(1, role="calibration", source_split="validation")
        original = copy.deepcopy(source)
        result = review([source], [1])
        row = result["records"][0]
        self.assertIn("outcome_selected_holdout_forbidden", row["exclusion_reasons"])
        self.assertEqual(row["queue"], "protected_do_not_train")
        self.assertEqual(row["proposed_sampling_frame_requires_review"], "high_response_protocol_v1")
        self.assertFalse(row["training_allowed_now"])
        self.assertEqual(source, original)

    def test_unknown_sampling_is_not_confirmed_from_strategy(self):
        source = record(2)
        source["sampling_frame"] = None
        source["exclusion_reasons"] = ["sampling_frame_not_confirmed"]
        row = review([source])["records"][0]
        self.assertEqual(row["proposed_sampling_frame_requires_review"], "")
        self.assertFalse(row["structurally_eligible_now"])

    def test_partial_transcript_and_protected_split_not_repaired_by_export(self):
        source = record(3, role="independent_test", source_split="test")
        source["transcript_scope"] = "first_window"
        source["exclusion_reasons"] = ["transcript_not_full_video", "fresh_outcome_test_not_demonstrated"]
        row = review([source])["records"][0]
        self.assertEqual(row["queue"], "transcript_repair")
        self.assertEqual(row["source_split_unchanged"], "test")
        self.assertTrue(row["protected"])
        self.assertFalse(row["structurally_eligible_now"])

    def test_readiness_and_development_candidates_are_different(self):
        source = record(4)
        source["confirmed_format"] = "unknown"
        source["exclusion_reasons"] = ["confirmed_format_missing", "sampling_frame_not_confirmed"]
        result = review([source], [4])
        self.assertEqual(result["queue_counts"], {"development_review": 1})
        self.assertEqual(result["training_allowed_now"], 0)
        self.assertEqual(result["structurally_eligible_now"], 0)

    def test_invalid_full_text_is_not_a_development_candidate(self):
        source = record(5)
        source["exclusion_reasons"] = ["transcript_hash_mismatch"]
        self.assertEqual(review([source])["queue_counts"], {"transcript_repair": 1})

    def test_effective_calibration_minimum_includes_three_bins(self):
        minimums = partition_minimums(PROTOCOL)
        self.assertEqual(minimums["calibration"]["protocol_minimum_videos"], 20)
        self.assertEqual(minimums["calibration"]["necessary_assessed_videos"], 30)
        self.assertEqual(minimums["independent_test"]["necessary_assessed_videos"], 30)
        self.assertFalse(minimums["calibration"]["sufficient_for_qualification"])

    def test_projected_coverage_is_not_observation_or_cell_support(self):
        source = record(6)
        source["observation"] = None
        source["frozen_age_context"] = "unknown"
        source["exclusion_reasons"] = ["no_observation", "invalid_age_context"]
        result = review([source])
        row = result["records"][0]
        self.assertEqual(row["actual_observation_age_context"], "unknown")
        self.assertEqual(row["projected_age_if_refreshed_at_cutoff_not_an_observation"], "age_30_90d")
        self.assertIsNone(row["observed_at"])
        self.assertFalse(result["projected_age_coverage_not_actual_support"][0]["supported_cell"])
        self.assertIsNone(result["exact_additional_collection_count"])

    def test_export_does_not_disclose_transcript_outcome_values_or_labels(self):
        result = review([record(7, views=876543210)])
        payload = json.dumps(result)
        self.assertNotIn("876543210", payload)
        self.assertNotIn('"transcript":', payload)
        self.assertNotIn('"views":', payload)
        self.assertNotIn('"label":', payload)
        self.assertFalse(result["labels_or_test_scores_computed"])

    def test_each_row_in_exactly_one_queue_and_category(self):
        rows = [record(1), record(2, category="camera", role="calibration", source_split="validation"),
                record(3, category="laptop", role="independent_test", source_split="test")]
        rows[2]["transcript_scope"] = "first_window"
        rows[2]["exclusion_reasons"] = ["transcript_not_full_video"]
        result = review(rows, [1, 2])
        self.assertEqual(sum(result["queue_counts"].values()), 3)
        self.assertEqual(sum(v["rows"] for v in result["by_category"].values()), 3)
        self.assertEqual(result["holdout_gap"]["calibration"]["unfilled_assessed_slots"], 30)
        self.assertEqual(result["holdout_gap"]["independent_test"]["unfilled_assessed_slots"], 30)

    def test_duplicate_video_does_not_inflate_development_sample_count(self):
        first = record(10)
        second = copy.deepcopy(first)
        second["dataset_id"] = 11
        result = review([first, second])
        self.assertEqual(result["active_rows"], 2)
        self.assertEqual(result["unique_videos"], 1)
        self.assertEqual(result["by_category"]["phone"]["development_roles"]["fit"]["videos"], 1)

    def test_csv_formula_cells_are_inert_and_blank_review_fields_stay_blank(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "review.csv"
            write_csv(path, [{"value": "=1+1", "review": ""}], ["value", "review"])
            with path.open(encoding="utf-8-sig", newline="") as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual(row["value"], "'=1+1")
            self.assertEqual(row["review"], "")

    def test_cutoff_requires_timezone_and_normalizes_to_utc(self):
        self.assertEqual(parse_cutoff("2026-10-12T07:00:00+07:00"), CUTOFF)
        with self.assertRaises(ValueError):
            parse_cutoff("invalid")
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_cutoff("2026-10-12T07:00:00")


if __name__ == "__main__":
    unittest.main()
