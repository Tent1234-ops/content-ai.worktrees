import copy
import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.database.db import get_db
from app.database.models import AnalysisResult, ReferenceStatisticsRun, ReferenceVideoStatistic, User, UserContent
from app.routes.contents import router
from app.services.performance_clustering import cluster_and_compare, name_centroids, performance_for_content
from tests import test_phase20_keyword_gap_evidence as fixtures


LOW = "battery charging processor memory cooling laptop keyboard price budget value "
HIGH = "camera autofocus sensor photography lens stabilization aperture shutter portrait exposure "


def sample_records(low=4, high=6):
    rows = []
    for i in range(low + high):
        high_group = i >= low
        rows.append({"dataset_id": i + 1, "video_id": f"testvid{i:04d}",
            "channel_id": f"channel-{i}", "channel_title": f"Channel {i}", "title": f"Test {i}",
            "url": f"https://www.youtube.com/watch?v=testvid{i:04d}",
            "transcript": (HIGH if high_group else LOW) * 3 + f"example{i}",
            "transcript_scope": "full_video", "views": (250000 if high_group else 30000) + i * 100,
            "likes": (10000 if high_group else 300) + i * 5, "format": "long_form",
            "view_metric_version": "youtube_play_start_view_v2"})
    return rows


class PerformanceCalculationTests(unittest.TestCase):
    def calculate(self, rows=None, text=HIGH):
        return cluster_and_compare(rows or sample_records(), user_transcript=text,
                                   category="camera", minimum_views=25000)

    def test_kmeans_summary_similarity_high_and_no_user_kpi(self):
        data = self.calculate()
        self.assertEqual(data["clustering"]["status"], "ready")
        high = next(c for c in data["clustering"]["clusters"] if c["performance_level"] == "high")
        self.assertEqual(high["video_count"], 6)
        self.assertAlmostEqual(high["average_views"], np.mean([r["views"] for r in sample_records()[4:]]))
        self.assertAlmostEqual(high["median_likes"], np.median([r["likes"] for r in sample_records()[4:]]))
        similarity = data["content_similarity"]
        self.assertEqual(similarity["closest_group"], "high")
        self.assertGreater(similarity["high_score"], similarity["low_score"])
        self.assertEqual(similarity["k_used"], 4)
        self.assertEqual([len(v) for v in similarity["supporting_dataset_ids"].values()], [4, 4])
        self.assertEqual(len(data["reference_videos"]), 10)
        self.assertNotIn("user_views", json.dumps(data))
        self.assertNotIn("predicted", json.dumps(data))
        self.assertTrue(data["shared_keywords"])

    def test_low_similarity_and_shared_feature_space(self):
        data = self.calculate(text=LOW)
        self.assertEqual(data["content_similarity"]["closest_group"], "low")
        self.assertGreater(data["content_similarity"]["low_score"], 0.5)
        self.assertLess(data["content_similarity"]["high_score"], 0.01)

    def test_centroid_names_do_not_depend_on_cluster_id_and_tradeoff_ties_abstain(self):
        self.assertEqual(name_centroids([[1, 1], [-1, -1]]), {0: "high", 1: "low"})
        self.assertEqual(name_centroids([[-1, -1], [1, 1]]), {1: "high", 0: "low"})
        self.assertEqual(name_centroids([[2, -1], [-2, 1]]), {0: "high", 1: "low"})
        self.assertIsNone(name_centroids([[1, -1], [-1, 1]]))

    def test_threshold_missing_values_short_transcript_and_dedup(self):
        rows = sample_records()
        rows[0]["views"] = 24999
        rows[1]["likes"] = None
        rows[2]["views"] = float("nan")
        rows[3]["transcript"] = "short"
        rows[4]["likes"] = True
        rows.append(copy.deepcopy(rows[5]))
        rows[-1]["dataset_id"] = 99
        result = self.calculate(rows)
        self.assertEqual(result["eligible_count"], 5)
        self.assertEqual(result["excluded_counts"], {
            "below_minimum_views": 1, "missing_or_invalid_kpi": 3,
            "insufficient_reference_transcript": 1, "duplicate_video_or_transcript": 1})
        self.assertEqual(result["clustering"]["reason"], "not_enough_references")

    def test_equal_points_and_sparse_group_abstain(self):
        rows = sample_records()
        for row in rows:
            row.update(views=30000, likes=100)
        self.assertEqual(self.calculate(rows)["clustering"]["reason"], "identical_kpi_points")
        rows[-1].update(views=10_000_000, likes=100000)
        self.assertEqual(self.calculate(rows)["clustering"]["reason"], "cluster_too_small")

    def test_user_empty_short_or_outside_vocabulary_never_forces_group(self):
        for text, reason in (("", "insufficient_user_transcript"), ("camera", "insufficient_user_transcript"),
                             ("orchard village river mountains forest landscape hiking sailing sunshine outdoors", "no_shared_features")):
            with self.subTest(text=text):
                result = self.calculate(text=text)
                self.assertEqual(result["clustering"]["status"], "ready")
                self.assertEqual(result["content_similarity"]["reason"], reason)
                self.assertIsNone(result["content_similarity"]["closest_group"])
                self.assertFalse(result["recommendations"])

    def test_similar_groups_are_inconclusive(self):
        result = self.calculate(sample_records(low=4, high=4), text=LOW + HIGH)
        self.assertEqual(result["content_similarity"]["status"], "inconclusive")
        self.assertIsNone(result["content_similarity"]["closest_group"])

    def test_group_without_usable_transcripts_excluded_before_kmeans(self):
        rows = sample_records()
        for row in rows[4:]:
            row["transcript"] = ""
        result = self.calculate(rows)
        self.assertEqual(result["eligible_count"], 4)
        self.assertEqual(result["clustering"]["status"], "insufficient_evidence")

    def test_deterministic_reordering_and_labels_do_not_depend_on_user_text(self):
        first = self.calculate()
        other = self.calculate(list(reversed(sample_records())), text=LOW)
        self.assertEqual(first["clustering"], other["clustering"])
        self.assertEqual([r["performance_level"] for r in first["reference_videos"]],
                         [r["performance_level"] for r in other["reference_videos"]])

    def test_zero_likes_is_measured_not_missing_and_kpis_only(self):
        rows = sample_records()
        rows[0]["likes"] = 0
        original = self.calculate(rows)
        for row in rows:
            row.update(comments=999999999, followers=999999999)
        other = self.calculate(rows)
        self.assertEqual(original["eligible_count"], 10)
        self.assertEqual(original["clustering"], other["clustering"])

    def test_grounded_advice_quotes_high_references_and_requires_two_channels(self):
        rows = sample_records()
        result = self.calculate(rows)
        self.assertTrue(result['recommendations'])
        by_id = {r['dataset_id']: r for r in rows}
        high_ids = {r['dataset_id'] for r in result['reference_videos'] if r['performance_level'] == 'high'}
        for advice in result['recommendations']:
            self.assertGreaterEqual(advice['channel_count'], 2)
            for ref in advice['references']:
                self.assertIn(ref['dataset_id'], high_ids)
                self.assertIn(ref['matched_text'], by_id[ref['dataset_id']]['transcript'])
                self.assertIn(ref['matched_text'], ref['quote'])
        for row in rows[4:]:
            row['channel_id'] = 'one-channel'
        self.assertFalse(self.calculate(rows)['recommendations'])

    def test_threshold_boundary_and_metric_versions_not_mixed(self):
        rows = sample_records()
        rows[0]['views'] = 25000
        rows[1]['view_metric_version'] = 'youtube_qualified_view_v1'
        result = self.calculate(rows)
        self.assertEqual(result['eligible_count'], 9)
        self.assertEqual(result['excluded_counts'], {'incompatible_view_metric': 1})
        self.assertIn(1, [r['dataset_id'] for r in result['reference_videos']])


class PerformanceApiTests(unittest.TestCase):
    def setUp(self):
        with patch.object(fixtures, 'create_engine', side_effect=lambda url: create_engine(
                url, connect_args={'check_same_thread': False}, poolclass=StaticPool)):
            fixtures.Phase20KeywordGapEvidenceTests.setUp(self)
        self.db.add(User(user_id=12, username='performance-owner', email='owner@example.test', password_hash='test'))
        self.db.add(UserContent(content_id=1, user_id=12, title='Test analysis', raw_transcript=LOW * 3))
        self.db.add(AnalysisResult(content_id=1, summary=json.dumps({'recommendation': self.detail()['recommendation']})))
        self.db.commit()

    tearDown = fixtures.Phase20KeywordGapEvidenceTests.tearDown
    _add_phone_rows = fixtures.Phase20KeywordGapEvidenceTests._add_phone_rows

    def detail(self):
        return {"analysis_id": 1, "raw_transcript": LOW * 3, "recommendation": {
            "classification": {"taxonomy_leaf_key": "phone", "is_unknown": False,
                               "acceptance": {"accepted": True}},
            "evidence_bundle": {"input": {"availability": "available"}}}}

    def _observations(self):
        from app.database.models import DatasetContent
        now = datetime.utcnow()
        run = ReferenceStatisticsRun(actor="test", started_at=now, status="completed")
        self.db.add(run)
        self.db.flush()
        rows = self.db.query(DatasetContent).all()
        for i, row in enumerate(rows):
            row.transcript += ' unique' + chr(97 + i // 26) + chr(97 + i % 26)
            from app.services.recommendation_evidence import text_hash
            row.transcript_sha256 = text_hash(row.transcript)
            self.db.add(ReferenceVideoStatistic(run_id=run.run_id, dataset_id=row.dataset_id,
                video_id=row.source_youtube_id, source_url=row.video_url, observed_at=now,
                status="partial", views=30000+i*100 if i < 15 else 250000+i*100,
                likes=100+i if i < 15 else 10000+i, comments=None,
                view_metric_version="youtube_play_start_view_v2"))
        self.db.commit()
        return now

    def test_api_auth_threshold_real_db_read_and_no_mutation(self):
        self._observations()
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[get_current_user] = lambda: User(user_id=12)
        before = self.db.get(AnalysisResult, 1).summary
        result = performance_for_content(self.db, user_id=12, content_id=1, minimum_views=25000)
        self.assertEqual(result["reference_count"], 30)
        self.assertEqual(result["eligible_count"], 30)
        self.assertEqual(result["clustering"]["status"], "ready")
        self.assertFalse(self.db.dirty)
        with TestClient(app) as client:
            response = client.get('/contents/1/performance-clustering?minimum_views=25000')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["eligible_count"], 30)
            self.assertEqual(response.json()['clustering'], result['clustering'])
            self.assertEqual(response.json()['content_similarity'], result['content_similarity'])
            self.assertEqual(client.get('/contents/1/performance-clustering?minimum_views=-1').status_code, 422)
            self.assertEqual(client.get('/contents/1/performance-clustering?minimum_views=abc').status_code, 422)
            self.assertEqual(client.get('/contents/1/performance-clustering?minimum_views=9007199254740992').status_code, 422)
            empty = client.get('/contents/1/performance-clustering?minimum_views=9000000').json()
            self.assertEqual(empty['eligible_count'], 0)
            app.dependency_overrides[get_current_user] = lambda: User(user_id=99)
            self.assertEqual(client.get('/contents/1/performance-clustering').status_code, 404)
            app.dependency_overrides.pop(get_current_user)
            self.assertEqual(client.get('/contents/1/performance-clustering').status_code, 401)
        self.db.expire_all()
        self.assertEqual(self.db.get(AnalysisResult, 1).summary, before)
        self.assertEqual(self.db.query(AnalysisResult).count(), 1)

    def test_unknown_missing_acceptance_and_foreign_content_do_not_read_references(self):
        detail = self.detail()
        for classification in ({}, {"taxonomy_leaf_key": "unknown", "is_unknown": True},
                               {"taxonomy_leaf_key": "phone", "is_unknown": False, "acceptance": {"accepted": False}}):
            detail["recommendation"]["classification"] = classification
            with patch('app.services.performance_clustering.get_user_content_detail', return_value=detail), \
                 patch('app.services.performance_clustering.reference_transcript_rows') as query:
                result = performance_for_content(self.db, user_id=1, content_id=1, minimum_views=25000)
                self.assertEqual(result["clustering"]["status"], "withheld")
                query.assert_not_called()
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as caught:
            performance_for_content(self.db, user_id=999999, content_id=999999, minimum_views=25000)
        self.assertEqual(caught.exception.status_code, 404)

    def test_latest_failure_stale_stats_holdout_and_hash_mismatch_excluded(self):
        from app.database.models import DatasetContent
        now = self._observations()
        rows = self.db.query(DatasetContent).order_by(DatasetContent.dataset_id).all()
        rows[0].data_split = "test"
        rows[1].transcript_sha256 = "0" * 64
        observations = self.db.query(ReferenceVideoStatistic).all()
        next(o for o in observations if o.dataset_id == rows[2].dataset_id).observed_at = now - timedelta(days=3)
        latest = next(o for o in observations if o.dataset_id == rows[3].dataset_id)
        latest.status = "failed"
        self.db.commit()
        with patch('app.services.performance_clustering.get_user_content_detail', return_value=self.detail()):
            result = performance_for_content(self.db, user_id=1, content_id=1, minimum_views=25000)
        self.assertLess(result["reference_count"], 30)
        self.assertEqual(result["excluded_counts"]["transcript_hash_mismatch"], 1)
        self.assertEqual(result["excluded_counts"]["no_recent_statistics"], 1)
        self.assertEqual(result["excluded_counts"]["latest_statistics_unavailable"], 1)
        self.assertTrue(all(r["channel_id"] != rows[0].source_channel_id for r in result["reference_videos"]))
