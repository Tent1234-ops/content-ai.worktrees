import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.contents import get_user_content_detail
from app.services.recommendation import (
    _duration_evidence_rows,
    _duration_summary,
)


class Phase21RecommendedDurationTests(unittest.TestCase):
    def test_fewer_than_ten_samples_returns_insufficient_evidence(self):
        result = _duration_summary(
            [30, 45, 60, 75, 90, 105, 120, 135, 150],
            "phone",
        )

        self.assertEqual(result["evidence_status"], "insufficient_evidence")
        self.assertEqual(result["recommended_range"], "Insufficient evidence")
        self.assertIsNone(result["recommended_seconds"])
        self.assertIsNone(result["median_seconds"])
        self.assertEqual(result["sample_size"], 9)
        self.assertEqual(result["minimum_sample_size"], 10)
        self.assertEqual(result["target_sample_size"], 15)

    def test_sufficient_samples_use_median_and_interpolated_percentiles(self):
        durations = [15, 43, 58, 60, 76, 82, 120, 174, 273, 294, 295]

        result = _duration_summary(durations, "phone")

        self.assertEqual(result["evidence_status"], "sufficient")
        self.assertEqual(result["recommended_seconds"], 82)
        self.assertEqual(result["median_seconds"], 82)
        self.assertEqual(result["percentile_low_seconds"], 59)
        self.assertEqual(result["percentile_high_seconds"], 224)
        self.assertEqual(result["recommended_range"], "59-224 sec")
        self.assertEqual(result["source"], "youtube_metadata")

    def test_duration_rows_require_youtube_metadata_and_upload_compatible_length(self):
        def row(
            dataset_id: int,
            duration: int,
            *,
            eligible: bool = True,
            metadata: bool = True,
        ):
            raw_metadata = (
                {"contentDetails": {"duration": f"PT{duration}S"}}
                if metadata
                else {"source": "youtube"}
            )
            return SimpleNamespace(
                dataset_id=dataset_id,
                duration_seconds=duration,
                is_duration_recommendation_eligible=eligible,
                raw_metadata_json=json.dumps(raw_metadata),
            )

        selected = _duration_evidence_rows(
            [
                row(4, 60),
                row(2, 180),
                row(3, 301),
                row(1, 45, metadata=False),
                row(5, 90, eligible=False),
            ]
        )

        self.assertEqual([item.dataset_id for item in selected], [2, 4])

    @patch("app.services.recommendation.build_recommendation_from_text")
    def test_legacy_history_does_not_rebuild_or_invent_range(
        self,
        build_recommendation,
    ):
        build_recommendation.side_effect = AssertionError('Never recalculate history')
        content = SimpleNamespace(
            content_id=7,
            user_id=3,
            title="Legacy phone review",
            created_at=None,
            video_url="legacy.mp4",
            transcript="phone transcript",
            raw_transcript="phone transcript",
            cleaned_transcript="phone transcript",
            analysis_results=[],
            recommendations=[],
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = content

        result = get_user_content_detail(db, user_id=3, content_id=7)

        self.assertEqual(result['recommendation']['evidence_bundle']['origin'], 'historical_legacy_no_snapshot')
        self.assertEqual(
            result["recommendation"]["recommended_duration"]["recommended_range"],
            "Insufficient evidence",
        )
        build_recommendation.assert_not_called()


if __name__ == "__main__":
    unittest.main()
