"""Frozen per-topic passing cohorts must agree with the saved evidence summary."""
import copy
import unittest
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


if __name__ == "__main__":
    unittest.main()
