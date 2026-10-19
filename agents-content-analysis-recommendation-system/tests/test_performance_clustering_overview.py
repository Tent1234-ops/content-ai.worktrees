"""Automatic topic overview: scope, abstention and owner authorization."""
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.api.deps import get_current_user
from app.database.db import get_db
from app.database.models import User
from app.routes.contents import router
from app.schemas.performance_clustering import PerformanceOverviewResponse
from app.services.performance_clustering_overview import performance_overview_for_content


class AutomaticOverviewTests(unittest.TestCase):
    def setUp(self):
        self.groups = [
            {"topic_id": "charging", "group_index": 0, "format": "long_form",
             "age_group": "age_90_365d", "topic_title": "ความเร็วในการชาร์จ",
             "threshold_views": 14374, "sample_size": 29, "passing_count": 16,
             "as_of": "2026-10-19T12:00:00Z"},
            {"topic_id": "camera", "group_index": 0, "format": "long_form",
             "age_group": "age_90_365d", "topic_title": "กล้อง",
             "threshold_views": 9000, "sample_size": 24, "passing_count": 14,
             "as_of": "2026-10-19T12:00:00Z"},
            {"topic_id": "charging", "group_index": 2, "format": "short_form",
             "age_group": "age_30_90d", "topic_title": "ความเร็วในการชาร์จ",
             "threshold_views": 5000, "sample_size": 10, "passing_count": 5,
             "as_of": "2026-10-19T12:00:00Z"},
        ]
        self.bundle = {
            "taxonomy_leaf_key": "phone",
            "input": {"availability": "available"},
            "action_topics": [
                {"topic_id": "charging"}, {"topic_id": "camera"},
            ],
            "topic_comparisons": {"items": [
                {"evidence_topic_id": "charging",
                 "group_response_summary": {"groups": [{}, {}, {}]}},
                {"evidence_topic_id": "camera",
                 "group_response_summary": {"groups": [{}]}},
                {"evidence_topic_id": "not_saved",
                 "group_response_summary": {"groups": [{}]}},
            ]},
        }
        self.content = {
            "analysis_id": 9,
            "recommendation": {
                "classification": {
                    "taxonomy_leaf_key": "phone", "is_unknown": False,
                    "acceptance": {"accepted": True},
                },
                "evidence_bundle": self.bundle,
            },
        }

    def mock_cohort(self, bundle, category, topic_id, index):
        for group in self.groups:
            if group["topic_id"] == topic_id and group["group_index"] == index:
                return group
        return None

    def calculated(self, db, *, topic_id, group_index, **kwargs):
        if topic_id == "charging" and group_index == 0:
            return {
                "eligible_count": 16,
                "clustering": {"status": "ready"},
                "content_similarity": {
                    "status": "ready", "closest_group": "high",
                    "low_score": 0.12, "high_score": 0.25, "k_used": 5,
                },
            }
        if topic_id == "camera":
            return {
                "eligible_count": 13,
                "clustering": {"status": "ready"},
                "content_similarity": {
                    "status": "inconclusive", "closest_group": None,
                    "low_score": 0.12, "high_score": 0.14,
                    "reason": "similar_scores", "k_used": 5,
                },
            }
        return {
            "eligible_count": 5,
            "clustering": {"status": "insufficient_evidence",
                           "reason": "not_enough_references"},
            "content_similarity": {
                "status": "insufficient_evidence", "closest_group": None,
                "low_score": None, "high_score": None, "k_used": 0,
            },
        }

    def test_runs_all_saved_cells_automatically_and_never_merges_them(self):
        rows = [object()]
        with patch("app.services.performance_clustering_overview.get_user_content_detail",
                   return_value=self.content), \
             patch("app.services.performance_clustering_overview.saved_topic_cohort",
                   side_effect=self.mock_cohort), \
             patch("app.services.performance_clustering_overview.reference_transcript_rows",
                   return_value=rows) as read, \\
             patch("app.services.performance_clustering_overview.performance_for_content",
                   side_effect=self.calculated) as calculate:
            result = performance_overview_for_content(None, user_id=12, content_id=51)

        self.assertEqual(result["topic_count"], 2)
        self.assertEqual(result["group_count"], 3)
        self.assertEqual(result["high_count"], 1)
        self.assertEqual(result["low_count"], 0)
        self.assertEqual(result["inconclusive_count"], 2)
        self.assertEqual(result["groups"][0]["topic_sample_size"], 29)
        self.assertEqual(result["groups"][0]["passing_count"], 16)
        self.assertEqual(result["groups"][0]["closest_group"], "high")
        self.assertEqual(result["groups"][1]["reason"], "similar_scores")
        self.assertIsNone(result["groups"][2]["closest_group"])
        self.assertEqual(
            [(g["topic_id"], g["group_index"]) for g in result["groups"]],
            [("charging", 0), ("charging", 2), ("camera", 0)],
        )
        read.assert_called_once()
        self.assertEqual(calculate.call_count, 3)
        for call in calculate.call_args_list:
            self.assertIs(call.kwargs["_content"], self.content)
            self.assertIs(call.kwargs["_reference_rows"], rows)
        PerformanceOverviewResponse.model_validate(result)

    def test_invalid_saved_evidence_does_not_fall_back_to_category(self):
        with patch("app.services.performance_clustering_overview.get_user_content_detail",
                   return_value=self.content), \
             patch("app.services.performance_clustering_overview.saved_topic_cohort",
                   return_value=None), \
             patch("app.services.performance_clustering_overview.reference_transcript_rows") as read:
            result = performance_overview_for_content(None, user_id=12, content_id=51)
        self.assertEqual(result["status"], "no_saved_topic_groups")
        self.assertEqual(result["groups"], [])
        read.assert_not_called()

    def test_rejected_classification_never_reads_references(self):
        self.content["recommendation"]["classification"]["acceptance"]["accepted"] = False
        with patch("app.services.performance_clustering_overview.get_user_content_detail",
                   return_value=self.content), \
             patch("app.services.performance_clustering_overview.reference_transcript_rows") as read:
            result = performance_overview_for_content(None, user_id=12, content_id=51)
        self.assertEqual(result["status"], "classification_not_accepted")
        read.assert_not_called()

    def test_missing_or_other_users_content_returns_404(self):
        with patch("app.services.performance_clustering_overview.get_user_content_detail",
                   return_value=None):
            with self.assertRaises(HTTPException) as raised:
                performance_overview_for_content(None, user_id=99, content_id=51)
        self.assertEqual(raised.exception.status_code, 404)

    def test_api_requires_login_and_returns_typed_payload(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: None
        app.dependency_overrides[get_current_user] = lambda: User(user_id=12)
        empty = {
            "schema_version": "performance-clustering-overview-v1",
            "content_id": 51, "analysis_id": 9, "category": "phone",
            "as_of": "2026-10-19T12:00:00Z", "status": "no_saved_topic_groups",
            "topic_count": 0, "group_count": 0, "ready_count": 0,
            "high_count": 0, "low_count": 0, "inconclusive_count": 0,
            "groups": [], "limitation": "Not a prediction",
        }
        with patch("app.routes.contents.performance_overview_for_content",
                   return_value=empty):
            with TestClient(app) as client:
                response = client.get("/contents/51/performance-clustering/overview")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["group_count"], 0)
                app.dependency_overrides.pop(get_current_user)
                self.assertEqual(
                    client.get("/contents/51/performance-clustering/overview").status_code,
                    401,
                )


if __name__ == "__main__":
    unittest.main()
