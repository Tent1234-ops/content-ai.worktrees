import copy
import json
import unittest
from datetime import datetime

from app.database.models import DatasetContent, User
from app.schemas.recommendation import RecommendationAnalysisResponse
from app.services.group_response_summary import summarize_group_responses
from app.services.persistence import save_video_analysis_result
from app.services.recommendation import (build_recommendation_from_analysis_data,
                                         build_recommendation_from_saved_content)
from tests.test_topic_comparisons import TopicComparisonIntegrationTests

NOW = datetime(2026, 10, 18, 10)


def record(identifier, views, channel, *, detected=True):
    video = f"video{identifier:06d}"
    return {
        "dataset_id": identifier, "video_id": video, "source_record_id": video,
        "taxonomy_leaf_key": "camera", "data_split": "train", "channel_id": channel,
        "sampling_frame": "general_protocol_v1", "collection_strategy": "classification_diverse",
        "comparison_eligible": True, "format_group": "long_form", "format_source": "raw_metadata.is_short",
        "age_group": "age_90_365d", "published_at": "2026-05-01T00:00:00Z",
        "view_metric_version": "youtube_play_start_view_v2",
        "topic_status": "detected" if detected else "not_detected",
        "occurrences": [{"quote": "low light"}] if detected else [],
        "latest_observation": {"observation_id": identifier, "video_id": video,
            "observed_at": "2026-10-18T09:00:00Z", "status": "complete", "views": views,
            "view_metric_version": "youtube_play_start_view_v2"},
    }


def summarize(rows):
    return summarize_group_responses(rows, category="camera", as_of=NOW)


class GroupResponseCalculationTests(unittest.TestCase):
    def setUp(self):
        self.rows = [record(1, 100, "a"), record(2, 300, "b"),
                     record(3, 200, "a", detected=False), record(4, 400, "b", detected=False)]

    def test_counts_topic_members_against_complete_context_benchmark(self):
        before = copy.deepcopy(self.rows)
        result = summarize(self.rows)
        group = result["groups"][0]
        self.assertEqual((group["passing_count"], group["sample_size"], group["percentage"],
                          group["channel_count"]), (1, 2, 50, 2))
        self.assertEqual(group["threshold_views"], 200)
        self.assertEqual(group["benchmark_sample_size"], 4)
        self.assertEqual(group["passing_video_ids"], ["video000002"])
        self.assertFalse(result["is_prediction"])
        self.assertEqual(self.rows, before)
        self.assertEqual(result, summarize(list(reversed(self.rows))))

    def test_all_supported_categories_keep_separate_labels(self):
        for category in ("phone", "camera", "laptop"):
            rows = copy.deepcopy(self.rows)
            for row in rows:
                row["taxonomy_leaf_key"] = category
            group = summarize_group_responses(rows, category=category, as_of=NOW)["groups"][0]
            self.assertEqual(group["category"], category)
            self.assertEqual(group["percentage"], 50)

    def test_channel_balanced_median_not_video_weighted_median(self):
        rows = [record(i, 300, "large") for i in range(1, 11)] + [record(11, 100, "small")]
        group = summarize(rows)["groups"][0]
        self.assertEqual(group["threshold_views"], 100)
        self.assertEqual(group["passing_count"], 10)
        self.assertEqual(group["sample_size"], 11)

    def test_zero_and_tied_views_are_valid_and_zero_percent_is_visible(self):
        group = summarize([record(1, 0, "a"), record(2, 0, "b")])["groups"][0]
        self.assertEqual(group["percentage"], 0)
        self.assertEqual(group["threshold_views"], 0)
        self.assertEqual(group["sample_size"], 2)

    def test_duplicates_do_not_inflate_count_or_channel_count(self):
        duplicate = copy.deepcopy(self.rows[0])
        duplicate["dataset_id"] = 99
        result = summarize([*self.rows, duplicate])
        self.assertEqual(result["groups"][0]["sample_size"], 2)
        self.assertEqual(result["exclusions"]["duplicate_video"], 1)

    def test_missing_context_selected_high_response_or_protected_data_are_excluded(self):
        for field, value in [
            ("data_split", "test"), ("data_split", "validation"), ("taxonomy_leaf_key", "phone"),
            ("format_group", "unknown"), ("format_source", None), ("channel_id", ""),
            ("sampling_frame", None), ("sampling_frame", "high_response_protocol_v1"),
            ("collection_strategy", "recommendation_high_performance"),
            ("comparison_eligible", False), ("topic_status", "unassessable"),
            ("source_record_id", "other000001"), ("occurrences", []),
            ("published_at", "2027-01-01T00:00:00Z"), ("age_group", "age_7_30d"),
        ]:
            with self.subTest(field=field, value=value):
                rows = copy.deepcopy(self.rows)
                rows[0][field] = value
                self.assertEqual(summarize(rows)["groups"], [])

    def test_bad_observations_never_fall_back_to_latest_counters(self):
        for field, value in [
            ("views", None), ("views", -1), ("views", True), ("views", 1.5),
            ("status", "failed"), ("video_id", "other000001"), ("observation_id", None),
            ("view_metric_version", "unknown"), ("observed_at", "invalid"),
            ("observed_at", "2026-10-19T09:00:00Z"), ("observed_at", "2026-10-16T09:00:00Z"),
        ]:
            with self.subTest(field=field, value=value):
                rows = copy.deepcopy(self.rows)
                rows[0]["latest_observation"][field] = value
                self.assertEqual(summarize(rows)["groups"], [])

    def test_cells_are_separate_and_never_selected_by_positive_rate(self):
        short_rows = [record(5, 0, "a"), record(6, 0, "b")]
        for row in short_rows:
            row["format_group"] = "short_form"
        groups = summarize([*self.rows, *short_rows])["groups"]
        self.assertEqual(len(groups), 2)
        self.assertEqual([g["percentage"] for g in groups], [50, 0])
        rows = copy.deepcopy(self.rows[:2])
        rows[0]["channel_id"] = rows[1]["channel_id"]
        self.assertEqual(summarize(rows)["groups"], [])


class GroupResponseIntegrationTests(unittest.TestCase):
    setUp = TopicComparisonIntegrationTests.setUp
    tearDown = TopicComparisonIntegrationTests.tearDown
    _add_phone_rows = TopicComparisonIntegrationTests._add_phone_rows
    _prepare_balanced_history = TopicComparisonIntegrationTests._prepare_balanced_history

    def test_new_analysis_freezes_summary_and_reopening_needs_no_current_data(self):
        self._prepare_balanced_history()
        rows = self.db.query(DatasetContent).all()
        for row in rows:
            metadata = json.loads(row.raw_metadata_json)
            metadata.update(content_format="long_form", outcome_sampling_frame="general_protocol_v1")
            row.raw_metadata_json = json.dumps(metadata)
            row.collection_strategy = "classification_diverse"
        self.db.commit()
        result = build_recommendation_from_analysis_data(
            self.db, domain="phone", user_keywords=[], dimension_status=[], hook_terms=[],
            transcript="รีวิวมือถือ แบตเตอรี่อึด เหมาะกับการเดินทาง")
        comparisons = result["evidence_bundle"]["topic_comparisons"]
        charging = next(item for item in comparisons["items"] if item["canonical_topic"] == "charging speed")
        summary = charging["group_response_summary"]
        self.assertEqual(summary["status"], "available")
        group = summary["groups"][0]
        self.assertEqual(group["sample_size"], 20)
        self.assertEqual(group["benchmark_sample_size"], 30)
        self.assertEqual(group["channel_count"], 10)
        serialized = RecommendationAnalysisResponse.model_validate(result).model_dump()
        user = User(username="group-audit", email="group@example.test", password_hash="fixture")
        self.db.add(user)
        self.db.commit()
        saved = save_video_analysis_result(
            self.db, user=user, filename="fixture.mp4", file_path="fixture.mp4",
            transcript="รีวิวมือถือ แบตเตอรี่อึด", analysis_payload={}, nlp_result={},
            recommendation_payload=serialized)
        before = json.dumps(result, ensure_ascii=False, sort_keys=True)
        rows[0].views = 99999999
        rows[0].transcript = "changed after analysis"
        self.db.commit()
        self.assertEqual(json.dumps(result, ensure_ascii=False, sort_keys=True), before)
        self.assertEqual(json.loads(before)["evidence_bundle"]["topic_comparisons"]["items"], comparisons["items"])
        self.db.expire_all()
        reloaded = build_recommendation_from_saved_content(
            self.db, content_id=saved["content_id"], user_id=user.user_id)
        self.assertEqual(reloaded["evidence_bundle"]["topic_comparisons"], comparisons)


if __name__ == "__main__":
    unittest.main()
