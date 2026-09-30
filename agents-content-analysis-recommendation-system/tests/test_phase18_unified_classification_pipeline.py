import json
import unittest
from unittest.mock import MagicMock, patch

from app.routes.analyze import _build_recommendation
from app.services.classification import classify_text_domain


class Phase18UnifiedClassificationPipelineTests(unittest.TestCase):
    @staticmethod
    def _phone_classification() -> dict:
        return {
            "domain": "phone",
            "legacy_domain": "phone",
            "taxonomy_leaf_key": "phone",
            "category_level_1": "Technology",
            "category_level_2": "Electronics",
            "category_level_3": "Phone",
            "taxonomy_version": "content-taxonomy-v1",
            "is_unknown": False,
            "confidence": 0.91,
            "method": "trained_tfidf_classifier",
        }

    @patch("app.routes.analyze.build_recommendation_from_analysis_data")
    @patch("app.routes.analyze.classify_text_domain")
    def test_phone_prediction_replaces_legacy_mouse_signals(
        self,
        classify_mock,
        recommendation_mock,
    ):
        classify_mock.return_value = self._phone_classification()
        captured: dict = {}

        def recommendation_side_effect(_db, **kwargs):
            captured.update(kwargs)
            return {
                "domain": kwargs["domain"],
                "user_keywords": list(kwargs["user_keywords"]),
                "missing_keywords": [],
                "hook_keywords": [],
            }

        recommendation_mock.side_effect = recommendation_side_effect
        result = {
            "transcript": (
                "phone android camera battery display charging speed "
                "mobile processor software support"
            ),
            "analysis": {
                "domain": "mouse",
                "product": "gaming mouse",
                "features": {"dpi": 8000, "polling_rate_hz": 1000},
                "top_keywords": [
                    {"keyword": "dpi", "score": 1.0},
                    {"keyword": "polling rate", "score": 0.9},
                ],
                "comparison_dimensions": [
                    {"name": "sensor performance", "confidence": 0.8},
                ],
                "dimension_status": [
                    {"name": "click latency", "status": "present"},
                ],
                "entity_keywords": ["gaming mouse"],
                "context_keywords": ["ergonomics"],
                "analysis_quality": 0.8,
                "hook_transcript": "phone camera battery display",
                "hook_keywords": ["legacy ambiguous value"],
                "stt_meta": {"transcript_source": "speech_to_text"},
            },
        }

        recommendation, _nlp_result = _build_recommendation(
            MagicMock(),
            filename="clip-001.mp4",
            result=result,
        )

        self.assertTrue(classify_mock.call_args.kwargs["require_active_model"])
        self.assertEqual(captured["domain"], "phone")
        self.assertEqual(recommendation["domain"], "phone")
        self.assertEqual(result["analysis"]["domain"], "phone")
        self.assertEqual(
            result["analysis"]["domain_source"],
            "trained_tfidf_classifier",
        )
        self.assertIn("hook_terms", result["analysis"])
        self.assertNotIn("hook_keywords", result["analysis"])
        self.assertEqual(
            result["analysis"]["hook_terms"],
            recommendation["hook_terms"],
        )
        for removed_key in (
            "product",
            "features",
            "entity_keywords",
            "context_keywords",
            "analysis_quality",
        ):
            self.assertNotIn(removed_key, result["analysis"])

        downstream_terms = {
            str(keyword).strip().lower()
            for keyword in recommendation["user_keywords"]
        }
        downstream_terms.update(
            str(item["keyword"]).strip().lower()
            for item in result["analysis"]["top_keywords"]
        )
        downstream_terms.update(
            str(item["name"]).strip().lower()
            for item in result["analysis"]["dimension_status"]
        )
        forbidden_mouse_terms = {
            "dpi",
            "polling rate",
            "sensor performance",
            "click latency",
            "ergonomics",
        }
        self.assertFalse(downstream_terms & forbidden_mouse_terms)
        serialized_output = json.dumps(
            {"analysis": result["analysis"], "recommendation": recommendation}
        ).lower()
        for forbidden_term in forbidden_mouse_terms:
            self.assertNotIn(forbidden_term, serialized_output)
        self.assertNotIn('"domain": "mouse"', serialized_output)

    @patch("app.routes.analyze.build_recommendation_from_analysis_data")
    @patch("app.routes.analyze.classify_text_domain")
    def test_unknown_prediction_does_not_restore_pipeline_domain(
        self,
        classify_mock,
        recommendation_mock,
    ):
        classify_mock.return_value = {
            "domain": "unknown",
            "legacy_domain": "phone",
            "taxonomy_leaf_key": "unknown",
            "category_level_1": "Unknown/Other",
            "category_level_2": None,
            "category_level_3": None,
            "taxonomy_version": "content-taxonomy-v1",
            "is_unknown": True,
            "confidence": 0.49,
            "method": "trained_tfidf_classifier",
        }
        captured: dict = {}

        def recommendation_side_effect(_db, **kwargs):
            captured.update(kwargs)
            return {
                "domain": kwargs["domain"],
                "user_keywords": list(kwargs["user_keywords"]),
            }

        recommendation_mock.side_effect = recommendation_side_effect
        result = {
            "transcript": "unclear mixed subject transcript",
            "analysis": {
                "domain": "mouse",
                "top_keywords": [{"keyword": "dpi", "score": 1.0}],
                "hook_transcript": "unclear mixed subject",
                "stt_meta": {"transcript_source": "speech_to_text"},
            },
        }

        recommendation, _nlp_result = _build_recommendation(
            MagicMock(),
            filename="clip-002.mp4",
            result=result,
        )

        self.assertEqual(captured["domain"], "unknown")
        self.assertEqual(recommendation["domain"], "unknown")
        self.assertEqual(result["analysis"]["domain"], "unknown")

    @patch("app.services.classification.taxonomy_coverage")
    @patch("app.services.classification.build_domain_classifier_profiles")
    @patch("app.services.classification._classify_with_active_model")
    def test_required_active_model_never_falls_back_to_legacy_classifier(
        self,
        active_model_mock,
        legacy_profiles_mock,
        coverage_mock,
    ):
        active_model_mock.return_value = None
        coverage_mock.return_value = {"ready": False}

        result = classify_text_domain(
            MagicMock(),
            text="phone camera battery",
            require_active_model=True,
        )

        self.assertEqual(result["domain"], "unknown")
        self.assertTrue(result["is_unknown"])
        self.assertEqual(result["method"], "active_model_unavailable")
        legacy_profiles_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
