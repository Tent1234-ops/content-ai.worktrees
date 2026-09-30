import hashlib
import json
import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.db import Base
from app.database.models import DatasetCollectionRun, DatasetContent
from app.schemas.recommendation import RecommendationAnalysisResponse
from app.services.dataset_contract import SPLIT_STRATEGY
from app.services.recommendation import (
    build_classified_user_signal_snapshot,
    build_dataset_profile_for_domain,
    build_recommendation_from_analysis_data,
)
from app.services.taxonomy import TAXONOMY_VERSION, sync_taxonomy_registry, taxonomy_path


class Phase20KeywordGapEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.run = DatasetCollectionRun(
            run_key=hashlib.sha256(b"phase20-run").hexdigest(),
            dataset_source="youtube_public_research",
            dataset_version="phase20-real-test-v1",
            status="reviewed",
            region_code="TH",
            languages_json='["th"]',
            query_config_json="{}",
        )
        self.db.add(self.run)
        self.db.commit()
        self._add_phone_rows(30)
        sync_taxonomy_registry(self.db)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _add_phone_rows(self, count: int) -> None:
        path = taxonomy_path("phone")
        captured_at = datetime.utcnow()
        transcript = (
            "รีวิว คลิป วันนี้ ครับ camera photo sensor camera photo "
            "Snapdragon chip processor battery battery AMOLED display brightness "
            "cooling thermal heat software update price value charging fast charge "
            "stabilization OIS material build quality"
        )
        for index in range(count):
            youtube_id = f"phase20{index:04d}"
            channel_id = f"phase20-channel-{index % 8}"
            row_transcript = f"{transcript} sample-{index}"
            average_views_per_day = 1000.0 + (index * 250.0)
            engagement_rate = 0.01 + (index * 0.0005)
            performance_signal = (index + 1) * 10.0
            self.db.add(
                DatasetContent(
                    title=f"Real phone evidence clip {index}",
                    video_url=f"https://www.youtube.com/watch?v={youtube_id}",
                    transcript=row_transcript,
                    category="phone",
                    source_platform="youtube",
                    dataset_source="youtube_public_research",
                    dataset_version="phase20-real-test-v1",
                    collection_run_id=self.run.collection_run_id,
                    source_record_id=youtube_id,
                    source_youtube_id=youtube_id,
                    source_creator=f"Creator {index % 8}",
                    source_channel_id=channel_id,
                    source_category="28",
                    source_subcategory="phone",
                    collection_query="รีวิวมือถือ",
                    source_release_url=f"https://www.youtube.com/watch?v={youtube_id}",
                    source_archive_sha256=hashlib.sha256(b"candidate").hexdigest(),
                    source_annotation_path="data/reviews/phase20.csv",
                    source_annotation_sha256=hashlib.sha256(b"review").hexdigest(),
                    import_batch_id=hashlib.sha256(b"phase20-batch").hexdigest(),
                    taxonomy_version=TAXONOMY_VERSION,
                    taxonomy_leaf_key="phone",
                    category_level_1=path["category_level_1"],
                    category_level_2=path["category_level_2"],
                    category_level_3=path["category_level_3"],
                    language="th",
                    verification_status="human_verified",
                    label_source="human_review",
                    license_name="YouTube Standard License",
                    license_url="https://support.google.com/youtube/answer/2797468",
                    data_split="train",
                    split_strategy=SPLIT_STRATEGY,
                    creator_group_key=hashlib.sha256(channel_id.encode()).hexdigest(),
                    transcript_sha256=hashlib.sha256(row_transcript.encode()).hexdigest(),
                    transcript_segment_count=1,
                    transcript_start_seconds=0,
                    transcript_end_seconds=180,
                    transcript_window_seconds=180,
                    transcript_source="notebooklm_source_transcript",
                    transcript_acquisition_method="notebooklm_manual_source",
                    transcript_scope="full_video",
                    transcript_timestamps_available=False,
                    caption_type="unspecified",
                    transcript_quality="good",
                    reviewed_by="phase20-reviewer",
                    reviewed_at=captured_at,
                    statistics_captured_at=captured_at,
                    view_metric_version="youtube_play_start_view_v2",
                    license_verified_at=captured_at,
                    raw_metadata_json=json.dumps({"source": "youtube"}),
                    collection_strategy="recommendation_high_performance",
                    average_views_per_day=average_views_per_day,
                    engagement_rate=engagement_rate,
                    is_training_eligible=True,
                    is_keyword_recommendation_eligible=True,
                    is_duration_recommendation_eligible=True,
                    is_active=True,
                    views=100_000 + (index * 10_000),
                    likes=4_000 + (index * 100),
                    comments=200 + index,
                    trend_score=performance_signal,
                    duration_seconds=180,
                    published_at=captured_at - timedelta(days=30),
                )
            )
        self.db.commit()

    def test_phone_profile_contains_traceable_keyword_evidence(self):
        profile = build_dataset_profile_for_domain(
            self.db,
            domain="phone",
            source_prefix="youtube",
        )

        self.assertEqual(profile["sample_size"], 12)
        self.assertTrue(profile["top_keywords"])
        selected_ids = set(profile["dataset_row_ids"])
        by_keyword = {
            item["keyword"]: item for item in profile["top_keywords"]
        }
        self.assertIn("camera quality", by_keyword)
        self.assertNotIn("รีวิว", by_keyword)
        self.assertNotIn("คลิป", by_keyword)
        self.assertNotIn("วันนี้", by_keyword)
        self.assertNotIn("ครับ", by_keyword)

        for item in profile["top_keywords"]:
            self.assertGreater(item["support_count"], 0)
            self.assertEqual(item["sample_size"], profile["sample_size"])
            self.assertGreater(item["total_frequency"], 0)
            self.assertTrue(item["supporting_examples"])
            self.assertTrue(set(item["supporting_dataset_row_ids"]).issubset(selected_ids))
            self.assertEqual(
                set(item["score_components"]),
                {"document_coverage", "frequency", "engagement"},
            )

    def test_gap_removes_user_synonyms_and_survives_api_schema(self):
        result = build_recommendation_from_analysis_data(
            self.db,
            domain="phone",
            user_keywords=["กล้อง", "แบตเตอรี่"],
            transcript="กล้องและแบตเตอรี่ของมือถือรุ่นนี้",
            dimension_status=[],
            hook_terms=[],
            source_prefix="youtube",
        )

        missing = {item["keyword"]: item for item in result["missing_keywords"]}
        self.assertNotIn("camera quality", missing)
        self.assertNotIn("battery life", missing)
        self.assertIn("display quality", missing)
        self.assertIn("chip performance", missing)
        self.assertTrue(missing["display quality"]["supporting_examples"])

        serialized = RecommendationAnalysisResponse.model_validate(result).model_dump()
        serialized_missing = {
            item["keyword"]: item for item in serialized["missing_keywords"]
        }
        self.assertGreater(serialized_missing["display quality"]["support_count"], 0)
        self.assertTrue(
            serialized_missing["display quality"]["supporting_dataset_row_ids"]
        )
        self.assertTrue(serialized_missing["display quality"]["supporting_examples"])

    def test_generic_phone_mention_does_not_hide_software_gap(self):
        snapshot = build_classified_user_signal_snapshot(
            text=(
                "มือถือรุ่นนี้มีกล้องคมชัด ใช้ชิป Snapdragon "
                "แบตเตอรี่อึด จอ AMOLED และระบายความร้อนได้ดี"
            ),
            hook_text="มือถือรุ่นนี้มีกล้องคมชัด",
            taxonomy_leaf_key="phone",
            max_keywords=10,
        )
        self.assertNotIn("software support", snapshot["comparable_keywords"])

        result = build_recommendation_from_analysis_data(
            self.db,
            domain="phone",
            user_keywords=snapshot["user_keywords"],
            transcript="มือถือรุ่นนี้มีกล้องคมชัด ใช้ชิป Snapdragon แบตเตอรี่อึด จอ AMOLED และระบายความร้อนได้ดี",
            dimension_status=snapshot["dimension_status"],
            hook_terms=snapshot["hook_terms"],
            source_prefix="youtube",
        )
        self.assertIn(
            "software support",
            {item["keyword"] for item in result["missing_keywords"]},
        )

    def test_hook_suggestions_never_recycle_observed_terms_or_lose_evidence(self):
        result = build_recommendation_from_analysis_data(
            self.db, domain="phone", user_keywords=["chip performance"],
            dimension_status=[], hook_terms=["dimensity"],
            transcript="มือถือรุ่นนี้ใช้ชิป Dimensity และแบตเตอรี่อึด", source_prefix="youtube")
        self.assertNotIn("battery life", {item["keyword"] for item in result["missing_keywords"]})
        self.assertTrue(result["hook_keywords"])
        for item in result["hook_keywords"]:
            self.assertNotIn(item["keyword"], {"dimensity", "chip performance", "battery life"})
            self.assertGreater(item["support_count"], 0)
            self.assertTrue(item["supporting_dataset_row_ids"])
            self.assertTrue(item["supporting_examples"])
        serialized = RecommendationAnalysisResponse.model_validate(result).model_dump()
        self.assertTrue(serialized["hook_keywords"][0]["supporting_dataset_row_ids"])

    def test_all_supported_concepts_present_means_no_gap_or_hook_invention(self):
        profile = build_dataset_profile_for_domain(self.db, domain="phone")
        result = build_recommendation_from_analysis_data(
            self.db, domain="phone", user_keywords=[row["keyword"] for row in profile["top_keywords"]],
            dimension_status=[], hook_terms=["dimensity"],
            transcript="ชิป Dimensity", source_prefix="youtube")
        self.assertEqual(result["missing_keywords"], [])
        self.assertEqual(result["hook_keywords"], [])


if __name__ == "__main__":
    unittest.main()
