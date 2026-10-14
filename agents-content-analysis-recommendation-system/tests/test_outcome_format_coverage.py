import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

from app.services.training_transcript import training_transcript_sha256
from scripts.audit_outcome_format_coverage import assess_format, count_coverage, source_index

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = json.loads((ROOT / "docs/implementation/outcome-prediction-protocol-v1.json").read_text(encoding="utf-8"))
VIDEO = "abcdefghijk"
TEXT = "Source spoken text " * 10
DIGEST = training_transcript_sha256(TEXT.strip())


def record():
    return {"source_youtube_id": VIDEO, "transcript_sha256": DIGEST, "confirmed_format": "unknown"}


def source(short=True):
    return {"path": "fixture.md", "source_url": f"https://www.youtube.com/shorts/{VIDEO}" if short else f"https://youtu.be/{VIDEO}",
            "transcript_sha256": DIGEST, "original_shorts_link": short}


def api(seconds=60):
    return {"id": VIDEO, "contentDetails": {"duration": f"PT{seconds}S"}}


class OutcomeFormatEvidenceTests(unittest.TestCase):
    def test_original_shorts_link_requires_matching_transcript_and_api_identity(self):
        result = assess_format(record(), [source()], api())
        self.assertEqual(result["proposed_format"], "short_form")
        self.assertEqual(result["format_evidence_status"], "documented_original_shorts_url_and_transcript_match")
        self.assertFalse(result["direct_platform_is_short_flag_observed"])
        different = source()
        different["transcript_sha256"] = "different"
        self.assertEqual(assess_format(record(), [different], api())["proposed_format"], "unknown")

    def test_duration_below_or_at_limit_is_never_sufficient_for_short(self):
        for seconds in (23, 60, 180):
            self.assertEqual(assess_format(record(), [source(False)], api(seconds))["proposed_format"], "unknown")

    def test_regular_video_is_explicitly_labeled_as_official_policy_inference(self):
        result = assess_format(record(), [source(False)], api(601))
        self.assertEqual(result["proposed_format"], "long_form")
        self.assertIn("inferred", result["format_evidence_status"])
        self.assertEqual(result["policy_review_date"], "2026-10-12")
        self.assertEqual(result["database_format_unchanged"], "unknown")

    def test_conflicting_short_link_and_duration_abstains(self):
        result = assess_format(record(), [source()], api(601))
        self.assertEqual(result["proposed_format"], "unknown")
        self.assertIn("original_shorts_link_conflicts_with_official_max_duration", result["format_reason_codes"])

    def test_missing_metadata_and_wrong_identity_never_confirm(self):
        wrong = api()
        wrong["id"] = "other_video"
        for item in ({}, wrong, api(0)):
            self.assertEqual(assess_format(record(), [source()], item)["proposed_format"], "unknown")

    def test_source_index_checks_declared_id_and_exact_source_path(self):
        entry = {"status": "parsed", "path": "fixture.md", "source_url": f"https://youtube.com/shorts/{VIDEO}?si=original",
                 "declared_video_id": VIDEO, "transcript": TEXT}
        self.assertTrue(source_index([entry])[VIDEO][0]["original_shorts_link"])
        mismatch = dict(entry, declared_video_id="other_video")
        self.assertEqual(dict(source_index([mismatch])), {})
        invalid = dict(entry, source_url="https://example.com/not-youtube")
        self.assertEqual(dict(source_index([invalid])), {})

    def test_watch_query_containing_short_url_is_not_original_short_path(self):
        entry = {"status": "parsed", "path": "fixture.md", "source_url": f"https://youtube.com/watch?v={VIDEO}&ref=/shorts/{VIDEO}",
                 "declared_video_id": VIDEO, "transcript": TEXT}
        self.assertFalse(source_index([entry])[VIDEO][0]["original_shorts_link"])


def count_row(index, content_format="long_form", role="fit", metric="v2"):
    return {"video_id": f"video-{index}", "channel_id": f"channel-{index % 5}", "category": "phone",
            "actual_observation_age": "age_90_365d", "proposed_format": content_format,
            "countable_metadata_and_text": True, "outcome_role": role, "view_metric_version": metric}


class OutcomeFormatCoverageTests(unittest.TestCase):
    def coverage(self, rows):
        return count_coverage(rows, [], PROTOCOL, datetime(2026, 10, 12, tzinfo=timezone.utc))

    def test_shorts_and_tuning_cannot_fill_fit_minimum(self):
        rows = [count_row(i) for i in range(18)] + [count_row(18, "short_form"), count_row(19, role="tuning")]
        cell = next(r for r in self.coverage(rows) if r["category"] == "phone" and r["age_context"] == "age_90_365d")
        self.assertEqual(cell["fit_videos"], 18)
        self.assertEqual(cell["tuning_videos"], 1)
        self.assertEqual(cell["fit_slots_to_fill_from_reviewed_or_new_data"], 2)
        self.assertFalse(cell["count_minimums_met"])

    def test_unknown_is_only_an_optimistic_scenario_not_confirmed_support(self):
        rows = [count_row(i) for i in range(18)] + [count_row(18, "unknown"), count_row(19, "unknown")]
        original = copy.deepcopy(rows)
        cell = next(r for r in self.coverage(rows) if r["category"] == "phone" and r["age_context"] == "age_90_365d")
        self.assertEqual(cell["fit_videos"], 18)
        self.assertEqual(cell["remaining_fit_slots_if_all_unknown_prove_regular"], 0)
        self.assertFalse(cell["count_minimums_met"])
        self.assertEqual(rows, original)

    def test_metric_versions_are_not_pooled_and_duplicate_videos_not_counted_twice(self):
        rows = [count_row(i, metric="v1" if i < 10 else "v2") for i in range(20)]
        rows.append(copy.deepcopy(rows[0]))
        cells = [r for r in self.coverage(rows) if r["category"] == "phone" and r["age_context"] == "age_90_365d"]
        self.assertEqual([r["fit_videos"] for r in cells], [10, 10])
        self.assertTrue(all(not r["count_minimums_met"] for r in cells))

    def test_counts_passing_are_not_probability_qualification(self):
        rows = [count_row(i) for i in range(20)]
        cell = next(r for r in self.coverage(rows) if r["category"] == "phone" and r["age_context"] == "age_90_365d")
        self.assertTrue(cell["count_minimums_met"])
        self.assertFalse(cell["probability_qualified"])

    def test_unknown_only_cell_keeps_upper_bound_separate_from_actual_count(self):
        rows = [count_row(i, "unknown") for i in range(20)]
        cell = next(r for r in self.coverage(rows) if r["category"] == "phone" and r["age_context"] == "age_90_365d")
        self.assertEqual(cell["fit_videos"], 0)
        self.assertEqual(cell["unresolved_format_fit_videos"], 20)
        self.assertEqual(cell["remaining_fit_slots_if_all_unknown_prove_regular"], 0)
        self.assertFalse(cell["count_minimums_met"])


if __name__ == "__main__":
    unittest.main()
