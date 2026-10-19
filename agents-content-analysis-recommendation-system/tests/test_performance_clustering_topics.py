"""Frozen per-topic passing cohorts must agree with the saved evidence summary."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import HTTPException

from app.services.performance_clustering import performance_for_content
from app.services.recommendation_evidence import text_hash
from datetime import datetime, timedelta, timezone

from app.services.group_response_summary import summarize_group_responses
from app.services.performance_clustering_topics import saved_topic_cohort


class TopicScopedCohortTests(unittest.TestCase):
    def setUp(self):
        cutoff = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
        observed = (cutoff - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        published = (cutoff - timedelta(days=100)).isoformat().replace("+00:00", "Z")
        self.records = []
        for i in range(30):
            views = (i + 1) * 1000
            self.records.append({
                "dataset_id": i + 1, "video_id": f"clip{i:07d}",
                "source_record_id": f"clip{i:07d}", "channel_id": f"channel-{i}",
                "channel_title": f"Channel {i}", "taxonomy_leaf_key": "phone",
                "data_split": "train", "sampling_frame": "general_protocol_v1",
                "collection_strategy": "general",
                "comparison_eligible": True, "topic_status": "detected",
                "occurrences": [{"matched_text": "charge"}],
                "format_group": "long_form", "format_source": "raw_metadata.format",
                "age_group": "age_90_365d", "published_at": published,
                "view_metric_version": "youtube_play_start_view_v2",
                "latest_observation": {
                    "observation_id": i + 1, "video_id": f"clip{i:07d}",
                    "observed_at": observed, "status": "complete",
                    "views": views, "likes": i * 10,
                    "view_metric_version": "youtube_play_start_view_v2",
                },
                "transcript_sha256": "0" * 64,
            })
        summary = summarize_group_responses(self.records, category="phone", as_of=cutoff)
        self.assertEqual(summary["status"], "available")
        self.assertEqual(len(summary["groups"]), 1)
        self.group = summary["groups"][0]
        self.bundle = {
            "taxonomy_leaf_key": "phone",
            "input": {"availability": "available"},
            "action_topics": [{
                "topic_id": "charge_topic", "source_type": "transcript",
                "user": {"status": "not_detected"},
            }],
            "topic_comparisons": {
                "schema_version": "topic-comparison-evidence-v1",
                "as_of": summary["as_of"],
                "items": [{
                    "evidence_topic_id": "charge_topic",
                    "canonical_topic": "charging_speed",
                    "title_th": "ความเร็วในการชาร์จ",
                    "records": self.records,
                    "group_response_summary": summary,
                }],
            },
        }

    def test_uses_exact_stored_passing_ids_and_strict_benchmark(self):
        cohort = saved_topic_cohort(self.bundle, "phone", "charge_topic", 0)
        self.assertIsNotNone(cohort)
        self.assertEqual(cohort["sample_size"], self.group["sample_size"])
        self.assertEqual(cohort["passing_count"], self.group["passing_count"])
        self.assertEqual([row["video_id"] for row in cohort["passing_records"]],
                         [row["video_id"] for row in self.records
                          if row["video_id"] in self.group["passing_video_ids"]])
        self.assertTrue(all(row["latest_observation"]["views"] > cohort["threshold_views"]
                            for row in cohort["passing_records"]))

    def test_does_not_substitute_category_when_saved_membership_tampered(self):
        bad = copy.deepcopy(self.bundle)
        bad["topic_comparisons"]["items"][0]["group_response_summary"]["groups"][0][
            "passing_video_ids"] = ["invalid-video"]
        self.assertIsNone(saved_topic_cohort(bad, "phone", "charge_topic", 0))
        self.assertIsNone(saved_topic_cohort(self.bundle, "camera", "charge_topic", 0))
        self.assertIsNone(saved_topic_cohort(self.bundle, "phone", "missing_topic", 0))
        self.assertIsNone(saved_topic_cohort(self.bundle, "phone", "charge_topic", 7))

    def test_requires_original_saved_evidence_and_not_detected_user_topic(self):
        invalid = copy.deepcopy(self.bundle)
        invalid["action_topics"][0]["user"]["status"] = "detected"
        self.assertIsNone(saved_topic_cohort(invalid, "phone", "charge_topic", 0))
        invalid = copy.deepcopy(self.bundle)
        invalid["topic_comparisons"]["items"][0]["group_response_summary"]["groups"][0][
            "threshold_views"] = 0
        self.assertIsNone(saved_topic_cohort(invalid, "phone", "charge_topic", 0))


    def test_api_uses_saved_passing_kpis_not_current_category(self):
        transcript = "camera lens sensor autofocus photography video battery charging performance " * 3
        sha = text_hash(transcript)
        saved = {
            "dataset_id": 1, "video_id": "clip0000001",
            "channel_id": "channel-1", "channel_title": "Channel 1",
            "published_at": "2026-01-01T00:00:00Z",
            "transcript_sha256": sha,
            "latest_observation": {
                "views": 14375, "likes": 35, "observed_at": "2026-10-19T12:00:00Z",
                "observation_id": 9, "view_metric_version": "youtube_play_start_view_v2",
            },
        }
        cohort = {
            "passing_records": [saved], "topic_title": "ความเร็วในการชาร์จ",
            "group_index": 0, "topic_id": "charging", "threshold_views": 14374,
            "format": "long_form", "age_group": "age_90_365d",
            "as_of": "2026-10-19T12:00:00Z", "sample_size": 29, "passing_count": 16,
        }
        content = {"analysis_id": 7, "raw_transcript": transcript,
            "recommendation": {
                "classification": {"taxonomy_leaf_key": "phone", "is_unknown": False,
                                   "acceptance": {"accepted": True}},
                "evidence_bundle": {"input": {"availability": "available"}},
            }}
        row = SimpleNamespace(dataset_id=1, source_youtube_id="clip0000001",
                              transcript=transcript, transcript_sha256=sha,
                              title="Reference", transcript_scope="full_video")
        with patch("app.services.performance_clustering.get_user_content_detail", return_value=content), \
             patch("app.services.performance_clustering.saved_topic_cohort", return_value=cohort), \
             patch("app.services.performance_clustering.reference_transcript_rows", return_value=[row]), \
             patch("app.services.performance_clustering.cluster_and_compare",
                   return_value={"reference_count": 1, "eligible_count": 1}) as calculation:
            result = performance_for_content(None, user_id=1, content_id=51,
                minimum_views=25000, topic_id="charging", group_index=0)
        passed = calculation.call_args.args[0]
        self.assertEqual(len(passed), 1)
        self.assertEqual(passed[0]["views"], 14375)
        self.assertEqual(passed[0]["likes"], 35)
        self.assertEqual(calculation.call_args.kwargs["minimum_views"], 14375)
        self.assertEqual(result["minimum_views"], 14374)
        self.assertEqual(result["selection"]["topic_sample_size"], 29)
        self.assertEqual(result["selection"]["passing_count"], 16)

    def test_api_rejects_missing_topic_without_category_fallback(self):
        content = {"analysis_id": 7, "raw_transcript": "phone transcript",
            "recommendation": {
                "classification": {"taxonomy_leaf_key": "phone", "is_unknown": False,
                                   "acceptance": {"accepted": True}},
                "evidence_bundle": {"input": {"availability": "available"}},
            }}
        with patch("app.services.performance_clustering.get_user_content_detail", return_value=content), \
             patch("app.services.performance_clustering.saved_topic_cohort", return_value=None), \
             patch("app.services.performance_clustering.reference_transcript_rows") as category_rows:
            with self.assertRaises(HTTPException) as raised:
                performance_for_content(None, user_id=1, content_id=51,
                    minimum_views=25000, topic_id="not-a-saved-topic", group_index=0)
            self.assertEqual(raised.exception.status_code, 422)
            category_rows.assert_not_called()


if __name__ == "__main__":
    unittest.main()
