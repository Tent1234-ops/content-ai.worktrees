import hashlib
import unittest
from datetime import datetime, timedelta

from app.database.models import (DatasetContent, ReferenceStatisticsRun,
                                 ReferenceVideoStatistic)
from app.services.recommendation import build_recommendation_from_analysis_data
from app.services.topic_comparisons import (_bootstrap_interval, _growth,
                                            _age_bucket, _duration_bucket,
                                            _metric_comparison,
                                            comparison_policy)
from tests import test_phase20_keyword_gap_evidence as fixtures


class TopicComparisonIntegrationTests(unittest.TestCase):
    setUp = fixtures.Phase20KeywordGapEvidenceTests.setUp
    tearDown = fixtures.Phase20KeywordGapEvidenceTests.tearDown
    _add_phone_rows = fixtures.Phase20KeywordGapEvidenceTests._add_phone_rows

    def _prepare_balanced_history(self, *, negative=False):
        now = datetime.utcnow().replace(microsecond=0)
        rows = self.db.query(DatasetContent).order_by(DatasetContent.dataset_id).all()
        for index, row in enumerate(rows):
            channel = index % 10
            row.source_channel_id = f"comparison-channel-{channel}"
            row.source_creator = f"Comparison channel {channel}"
            row.creator_group_key = hashlib.sha256(row.source_channel_id.encode()).hexdigest()
            detected = index < 20
            row.transcript = ("รีวิวมือถือ แบตเตอรี่ การชาร์จเร็ว charging จับเวลา "
                              if detected else "รีวิวมือถือ แบตเตอรี่ ใช้งานทั่วไป ") + f"case-{index}"
            row.transcript_sha256 = hashlib.sha256(row.transcript.encode()).hexdigest()
        self.db.commit()
        start = now - timedelta(hours=25)
        end = now - timedelta(hours=1)
        first = ReferenceStatisticsRun(actor="test", status="completed", started_at=start,
                                       completed_at=start, candidate_count=len(rows))
        second = ReferenceStatisticsRun(actor="test", status="completed", started_at=end,
                                        completed_at=end, candidate_count=len(rows))
        self.db.add_all([first, second])
        self.db.flush()
        for index, row in enumerate(rows):
            channel = index % 10
            detected = index < 20
            baseline = 1000 + channel * 100
            latest = baseline + (400 + channel * 20 if detected else 100)
            if negative:
                latest = baseline + (50 if detected else 500 + channel * 20)
            for run, observed, views in ((first, start, baseline), (second, end, latest)):
                self.db.add(ReferenceVideoStatistic(
                    run_id=run.run_id, dataset_id=row.dataset_id,
                    video_id=row.source_youtube_id, source_url=row.video_url,
                    observed_at=observed, status="complete", views=views,
                    likes=views // 20, comments=views // 100,
                    view_metric_version="youtube_play_start_view_v2"))
        self.db.commit()
        return now

    def test_new_analysis_freezes_all_reference_rows_and_channel_comparisons(self):
        now = self._prepare_balanced_history()
        result = build_recommendation_from_analysis_data(
            self.db, domain="phone", user_keywords=[], dimension_status=[], hook_terms=[],
            transcript="รีวิวมือถือ แบตเตอรี่อึด เหมาะกับการเดินทาง")
        comparison_bundle = result["evidence_bundle"]["topic_comparisons"]
        self.assertEqual(comparison_bundle["schema_version"], "topic-comparison-evidence-v1")
        charging = next(row for row in comparison_bundle["items"]
                        if row["canonical_topic"] == "charging speed")
        self.assertEqual(charging["cohort"]["eligible_video_count"], 30)
        self.assertEqual(charging["cohort"]["support_cohort_video_count"], 12)
        self.assertEqual(charging["cohort"]["comparison_pool_video_count"], 18)
        self.assertEqual(charging["cohort"]["detected_count"], 20)
        self.assertEqual(charging["cohort"]["not_detected_count"], 10)
        views = charging["metrics"]["views"]
        self.assertEqual(views["paired_channel_count"], 10)
        self.assertEqual(views["detected"]["count"], 20)
        self.assertEqual(views["not_detected"]["count"], 10)
        self.assertEqual(views["direction"], "higher")
        self.assertIn(views["status"], {"comparison_supported", "comparison_uncertain"})
        growth = charging["metrics"]["views_per_hour"]
        self.assertEqual(growth["detected"]["count"], 20)
        self.assertEqual(growth["not_detected"]["count"], 10)
        record = charging["records"][0]
        self.assertEqual(record["growth"]["elapsed_hours"], 24)
        self.assertIsNotNone(record["growth"]["views_per_hour"])
        self.assertLessEqual(datetime.fromisoformat(comparison_bundle["as_of"].replace("Z", "+00:00")).replace(tzinfo=None), now + timedelta(seconds=3))
        self.assertFalse(charging["causal_claim"])
        self.assertNotIn("_comparison_reference_rows", result["dataset_profile"])
        documents = comparison_bundle["reference_documents"]
        self.assertEqual(len(documents), 30)
        self.assertTrue(all(row["transcript"] and row["transcript_sha256"] for row in documents))
        original = documents[0]["transcript"]
        self.db.get(DatasetContent, documents[0]["dataset_id"]).transcript = "changed after analysis"
        self.db.commit()
        self.assertEqual(documents[0]["transcript"], original)

    def test_no_statistics_never_uses_dataset_latest_value_as_fake_observation(self):
        result = build_recommendation_from_analysis_data(
            self.db, domain="phone", user_keywords=[], dimension_status=[], hook_terms=[],
            transcript="รีวิวมือถือ แบตเตอรี่อึด")
        charging = next(row for row in result["evidence_bundle"]["topic_comparisons"]["items"]
                        if row["canonical_topic"] == "charging speed")
        self.assertEqual(charging["metrics"]["views"]["status"], "not_comparable")
        self.assertEqual(charging["metrics"]["views"]["detected"]["count"], 0)
        self.assertEqual(charging["cohort"]["exclusions"]["no_recent_successful_observation"], 30)

    def test_negative_results_are_kept_instead_of_filtered_out(self):
        self._prepare_balanced_history(negative=True)
        result = build_recommendation_from_analysis_data(
            self.db, domain="phone", user_keywords=[], dimension_status=[], hook_terms=[],
            transcript="รีวิวมือถือ แบตเตอรี่อึด")
        charging = next(row for row in result["evidence_bundle"]["topic_comparisons"]["items"]
                        if row["canonical_topic"] == "charging speed")
        growth = charging["metrics"]["views_per_hour"]
        self.assertEqual(growth["direction"], "lower")
        self.assertLess(growth["within_channel_median_difference"], 0)
        self.assertFalse(growth["causal_claim"])


class TopicComparisonCalculationTests(unittest.TestCase):
    def _observation(self, identifier, at, views, *, status="complete", version="youtube_play_start_view_v2"):
        return ReferenceVideoStatistic(observation_id=identifier, run_id=identifier, dataset_id=1,
            video_id="video", source_url="https://youtu.be/video", observed_at=at,
            status=status, views=views, likes=10, comments=1, view_metric_version=version)

    def test_growth_uses_two_real_times_and_breaks_on_failure_or_correction(self):
        end = datetime(2026, 9, 29, 12)
        start = end - timedelta(hours=24)
        first = self._observation(1, start, 1000)
        latest = self._observation(2, end, 1600)
        value = _growth([first, latest], latest)
        self.assertEqual(value["views_delta"], 600)
        self.assertEqual(value["views_per_hour"], 25)
        failed = self._observation(3, start + timedelta(hours=12), None, status="failed")
        self.assertEqual(_growth([first, failed, latest], latest)["status"], "unavailable")
        corrected = self._observation(4, end, 800)
        correction = _growth([first, corrected], corrected)
        self.assertEqual(correction["status"], "counter_correction")
        self.assertIsNone(correction["views_per_hour"])

    def test_growth_cannot_bridge_metric_changes_or_recovered_counter_corrections(self):
        end = datetime(2026, 9, 29, 12)
        first = self._observation(1, end - timedelta(hours=24), 1000)
        latest = self._observation(3, end, 1600)
        changed = self._observation(2, end - timedelta(hours=6), 1300, version="unknown")
        self.assertIsNone(_growth([first, changed, latest], latest)["views_per_hour"])
        changed.view_metric_version = "youtube_play_start_view_v2"
        changed.views = 500
        self.assertIsNone(_growth([first, changed, latest], latest)["views_per_hour"])

    def test_channel_weighting_and_sparse_status_are_deterministic(self):
        records = []
        for channel, difference in (("large", 100), ("small", -20)):
            repeats = 20 if channel == "large" else 1
            for arm, value in (("detected", 1000 + difference), ("not_detected", 1000)):
                for index in range(repeats):
                    records.append({"video_id": f"{channel}-{arm}-{index}", "channel_id": channel,
                        "stratum": ["phone", "unknown", "duration_1_180s", "age_7_30d", "v"],
                        "topic_status": arm, "comparison_eligible": True,
                        "exclusion_reasons": [], "metrics": {"views": value}})
        result = _metric_comparison(records, "views")
        self.assertEqual(result["paired_channel_count"], 2)
        self.assertEqual(result["within_channel_median_difference"], 40)
        self.assertEqual(result["status"], "reference_only")

    def test_bootstrap_policy_is_versioned_and_degenerate_data_is_not_zero_interval(self):
        policy = comparison_policy()
        self.assertEqual(policy["bootstrap_resamples"], 2000)
        self.assertEqual(len(policy["sha256"]), 64)
        self.assertEqual(_bootstrap_interval([1.0] * 10)["status"], "uncertainty_unavailable")
        first = _bootstrap_interval(list(range(-5, 5)))
        second = _bootstrap_interval(list(range(-5, 5)))
        self.assertEqual(first, second)

    def test_bucket_boundaries_do_not_mix_age_or_duration_groups(self):
        self.assertEqual(_age_bucket(0), "age_0_7d")
        self.assertEqual(_age_bucket(6.999), "age_0_7d")
        self.assertEqual(_age_bucket(7), "age_7_30d")
        self.assertEqual(_age_bucket(30), "age_30_90d")
        self.assertEqual(_age_bucket(90), "age_90_365d")
        self.assertEqual(_age_bucket(365), "age_365d_plus")
        self.assertIsNone(_age_bucket(-0.01))
        self.assertEqual(_duration_bucket(180), "duration_1_180s")
        self.assertEqual(_duration_bucket(181), "duration_over_180s")
        self.assertIsNone(_duration_bucket(0))

    def test_missing_rate_metric_does_not_remove_valid_view_metric(self):
        records = []
        for arm, views, likes in (("detected", 1000.0, None),
                                  ("not_detected", 900.0, None)):
            records.append({"video_id": arm, "channel_id": "same", "topic_status": arm,
                "stratum": ["phone", "unknown", "duration_1_180s", "age_7_30d", "v"],
                "comparison_eligible": True, "exclusion_reasons": [],
                "metrics": {"views": views, "likes_per_1000_views": likes}})
        self.assertEqual(_metric_comparison(records, "views")["detected"]["count"], 1)
        rate = _metric_comparison(records, "likes_per_1000_views")
        self.assertEqual(rate["status"], "not_comparable")
        self.assertEqual(rate["excluded"]["missing_likes_per_1000_views"], 2)


if __name__ == "__main__":
    unittest.main()
