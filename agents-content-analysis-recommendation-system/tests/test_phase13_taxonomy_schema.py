import hashlib
import json
import unittest
from datetime import datetime
from unittest.mock import patch

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.database.db import Base
from app.database.migrations import migrate_phase13_taxonomy_schema
from app.database.models import (
    AnalysisResult,
    ClassificationModel,
    DatasetCollectionRun,
    DatasetContent,
    ModelEvaluationMetric,
    TaxonomyNode,
    User,
)
from app.services.classification import classify_text_domain
from app.services.dataset_contract import (
    SPLIT_STRATEGY,
    YOUTUBE_CC_LICENSE_NAME,
    YOUTUBE_CC_LICENSE_URL,
)
from app.services.persistence import save_video_analysis_result
from app.services.recommendation import build_dataset_profile_for_domain
from app.services.taxonomy import (
    ACTIVE_LEAF_KEYS,
    TAXONOMY_VERSION,
    normalize_taxonomy_leaf,
    sync_taxonomy_registry,
    taxonomy_coverage,
    taxonomy_path,
)
from app.services.view_metrics import (
    YOUTUBE_PLAY_START_VIEW_V2,
    YOUTUBE_QUALIFIED_VIEW_V1,
)


HASH_A = hashlib.sha256(b"candidate artifact").hexdigest()
HASH_B = hashlib.sha256(b"review artifact").hexdigest()
HASH_C = hashlib.sha256(b"import batch").hexdigest()


class Phase13TaxonomySchemaTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.run = DatasetCollectionRun(
            run_key=hashlib.sha256(b"phase13-run").hexdigest(),
            dataset_source="youtube_cc",
            dataset_version="youtube-cc-test-v1",
            status="reviewed",
            region_code="TH",
            languages_json='["th", "en"]',
            query_config_json="{}",
        )
        self.db.add(self.run)
        self.db.commit()
        sync_taxonomy_registry(self.db)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _add_verified_leaf_rows(self, leaf_key: str, count: int) -> None:
        path = taxonomy_path(leaf_key)
        start = (
            self.db.query(DatasetContent)
            .filter(DatasetContent.taxonomy_leaf_key == leaf_key)
            .count()
        )
        now = datetime.utcnow()
        for index in range(start, start + count):
            transcript = f"real reviewed transcript for {leaf_key} sample {index}"
            channel_id = f"channel-{leaf_key}-{index % 5}"
            youtube_id = f"{leaf_key[:8]}{index:06d}"
            self.db.add(
                DatasetContent(
                    title=f"{leaf_key} real sample {index}",
                    video_url=f"https://www.youtube.com/watch?v={youtube_id}",
                    transcript=transcript,
                    category=leaf_key,
                    source_platform="youtube",
                    dataset_source="youtube_cc",
                    dataset_version="youtube-cc-test-v1",
                    collection_run_id=self.run.collection_run_id,
                    source_record_id=f"{leaf_key}-{index}",
                    source_youtube_id=youtube_id,
                    source_creator=f"creator-{index % 5}",
                    source_channel_id=channel_id,
                    source_category="28",
                    source_subcategory=leaf_key,
                    collection_query=f"{leaf_key} review",
                    source_release_url=f"https://www.youtube.com/watch?v={youtube_id}",
                    source_archive_sha256=HASH_A,
                    source_annotation_path="data/reviews/test.csv",
                    source_annotation_sha256=HASH_B,
                    import_batch_id=HASH_C,
                    taxonomy_version=TAXONOMY_VERSION,
                    taxonomy_leaf_key=leaf_key,
                    category_level_1=path["category_level_1"],
                    category_level_2=path["category_level_2"],
                    category_level_3=path["category_level_3"],
                    language="th",
                    verification_status="human_verified",
                    label_source="human_review",
                    license_name=YOUTUBE_CC_LICENSE_NAME,
                    license_url=YOUTUBE_CC_LICENSE_URL,
                    data_split="train",
                    split_strategy=SPLIT_STRATEGY,
                    creator_group_key=hashlib.sha256(channel_id.encode()).hexdigest(),
                    transcript_sha256=hashlib.sha256(transcript.encode()).hexdigest(),
                    transcript_segment_count=10,
                    transcript_start_seconds=0,
                    transcript_end_seconds=120,
                    transcript_window_seconds=300,
                    transcript_source="youtube_public_caption",
                    caption_type="manual",
                    transcript_quality="good",
                    reviewed_by="reviewer@example.test",
                    reviewed_at=now,
                    statistics_captured_at=now,
                    license_verified_at=now,
                    raw_metadata_json=json.dumps({"license": "creativeCommon"}),
                    is_training_eligible=True,
                    is_keyword_recommendation_eligible=True,
                    is_duration_recommendation_eligible=True,
                    is_active=True,
                    duration_seconds=120,
                    published_at=now,
                )
            )
        self.db.commit()

    def test_v1_has_twelve_non_overlapping_trainable_leaves(self):
        self.assertEqual(TAXONOMY_VERSION, "content-taxonomy-v1")
        self.assertEqual(len(ACTIVE_LEAF_KEYS), 12)
        self.assertEqual(len(set(ACTIVE_LEAF_KEYS)), 12)
        self.assertIn("phone", ACTIVE_LEAF_KEYS)
        self.assertIn("general_food", ACTIVE_LEAF_KEYS)
        self.assertNotIn("keyboard", ACTIVE_LEAF_KEYS)
        self.assertEqual(normalize_taxonomy_leaf("keyboard"), "unknown")
        self.assertEqual(normalize_taxonomy_leaf("FPS"), "unknown")

    def test_hierarchy_paths_are_three_levels_and_unknown_is_explicit(self):
        path = taxonomy_path("headphone")
        self.assertEqual(path["category_level_1"], "Technology")
        self.assertEqual(path["category_level_2"], "Electronics")
        self.assertEqual(path["category_level_3"], "Headphone")
        unknown = taxonomy_path("keyboard")
        self.assertEqual(unknown["category_level_1"], "Unknown/Other")
        self.assertTrue(unknown["is_unknown"])

    def test_registry_is_idempotent_and_does_not_create_fake_model(self):
        node_count = self.db.query(TaxonomyNode).count()
        sync_taxonomy_registry(self.db)
        self.assertEqual(self.db.query(TaxonomyNode).count(), node_count)
        self.assertEqual(self.db.query(ClassificationModel).count(), 0)

    def test_leaf_activates_only_after_thirty_human_reviews(self):
        phone = self.db.query(TaxonomyNode).filter(TaxonomyNode.node_key == "phone").one()
        self.assertFalse(phone.is_active)
        self._add_verified_leaf_rows("phone", 29)
        sync_taxonomy_registry(self.db)
        self.db.refresh(phone)
        self.assertFalse(phone.is_active)
        self._add_verified_leaf_rows("phone", 1)
        sync_taxonomy_registry(self.db)
        self.db.refresh(phone)
        self.assertTrue(phone.is_active)

    def test_coverage_requires_thirty_verified_youtube_rows_per_leaf(self):
        self.db.add(
            DatasetContent(
                title="unreviewed candidate",
                transcript="must never count",
                category="phone",
                source_platform="youtube",
                dataset_source="youtube_cc",
                taxonomy_version=TAXONOMY_VERSION,
                taxonomy_leaf_key="phone",
                verification_status="unverified",
                label_source="search_query",
                is_training_eligible=False,
            )
        )
        self.db.commit()
        for leaf_key in ACTIVE_LEAF_KEYS:
            self._add_verified_leaf_rows(leaf_key, 29)
        before = taxonomy_coverage(self.db)
        self.assertEqual(before["source_dataset"], "youtube_public_research")
        self.assertEqual(before["ready_leaf_count"], 0)
        for leaf_key in ACTIVE_LEAF_KEYS:
            self._add_verified_leaf_rows(leaf_key, 1)
        after = taxonomy_coverage(self.db)
        self.assertTrue(after["ready"])
        self.assertTrue(all(item["verified_sample_count"] == 30 for item in after["leaves"]))

    def test_classifier_returns_unknown_until_coverage_then_emits_hierarchy(self):
        profiles = [{"domain": "phone", "sample_size": 30, "term_weights": {"phone": 1.0}}]
        with patch("app.services.classification.build_domain_classifier_profiles", return_value=profiles):
            before = classify_text_domain(self.db, title="phone review", text="phone camera battery")
        self.assertEqual(before["domain"], "unknown")
        self.assertIn("0/30", before["warning"])

        self._add_verified_leaf_rows("phone", 30)
        with patch("app.services.classification.build_domain_classifier_profiles", return_value=profiles):
            after = classify_text_domain(self.db, title="phone review", text="phone camera battery")
        self.assertEqual(after["domain"], "phone")
        self.assertEqual(after["category_level_3"], "Phone")

    def test_evaluation_metrics_remain_versioned_by_model_and_leaf(self):
        model = ClassificationModel(
            model_key="taxonomy-classifier",
            model_version="test-v1",
            taxonomy_version=TAXONOMY_VERSION,
            model_type="centroid",
            training_dataset_source="youtube_cc",
            training_dataset_version="youtube-cc-test-v1",
        )
        self.db.add(model)
        self.db.flush()
        self.db.add_all(
            [
                ModelEvaluationMetric(
                    model_id=model.model_id,
                    taxonomy_level=3,
                    taxonomy_leaf_key="__overall__",
                    metric_name="f1_macro",
                    metric_value=0.82,
                    sample_size=360,
                ),
                ModelEvaluationMetric(
                    model_id=model.model_id,
                    taxonomy_level=3,
                    taxonomy_leaf_key="phone",
                    metric_name="f1_macro",
                    metric_value=0.84,
                    sample_size=30,
                ),
            ]
        )
        self.db.commit()
        self.assertEqual(self.db.query(ModelEvaluationMetric).count(), 2)

    def test_recommendation_evidence_uses_real_same_leaf_subset(self):
        self._add_verified_leaf_rows("phone", 30)
        for index, row in enumerate(
            self.db.query(DatasetContent)
            .filter(DatasetContent.taxonomy_leaf_key == "phone")
            .order_by(DatasetContent.dataset_id)
            .all()
        ):
            row.views = 1000 + index * 1000
            row.likes = 50 + index * 10
            row.comments = 5 + index
            row.trend_score = float(index)
        self.db.commit()
        sync_taxonomy_registry(self.db)

        profile = build_dataset_profile_for_domain(
            self.db,
            domain="phone",
            source_prefix="youtube",
            limit=150,
        )

        self.assertEqual(profile["eligible_pool_size"], 30)
        self.assertEqual(profile["sample_size"], 12)
        self.assertEqual(profile["source"], "youtube_public_human_verified")
        self.assertEqual(sum(profile["source_platform_counts"].values()), 12)
        self.assertEqual(len(profile["dataset_row_ids"]), 12)
        selected_scores = [
            self.db.get(DatasetContent, dataset_id).trend_score
            for dataset_id in profile["dataset_row_ids"]
        ]
        self.assertEqual(min(selected_scores), 18.0)

    def test_recommendation_never_ranks_across_view_metric_versions(self):
        self._add_verified_leaf_rows("phone", 30)
        rows = (
            self.db.query(DatasetContent)
            .filter(DatasetContent.taxonomy_leaf_key == "phone")
            .order_by(DatasetContent.dataset_id)
            .all()
        )
        legacy_ids = set()
        for index, row in enumerate(rows):
            if index < 20:
                row.view_metric_version = YOUTUBE_QUALIFIED_VIEW_V1
                row.trend_score = float(index)
                legacy_ids.add(row.dataset_id)
            else:
                row.view_metric_version = YOUTUBE_PLAY_START_VIEW_V2
                row.trend_score = 100_000.0 + index
        self.db.commit()
        sync_taxonomy_registry(self.db)

        profile = build_dataset_profile_for_domain(
            self.db,
            domain="phone",
            source_prefix="youtube",
            limit=150,
        )

        self.assertEqual(profile["eligible_pool_size"], 30)
        self.assertEqual(profile["view_metric_cohort_size"], 20)
        self.assertEqual(profile["excluded_incompatible_view_metric_rows"], 10)
        self.assertEqual(
            profile["view_metric_version"],
            YOUTUBE_QUALIFIED_VIEW_V1,
        )
        self.assertTrue(set(profile["dataset_row_ids"]).issubset(legacy_ids))

    def test_saved_unknown_analysis_tracks_current_taxonomy(self):
        user = User(
            username="phase13-user",
            email="phase13@example.test",
            password_hash="not-used",
        )
        self.db.add(user)
        self.db.commit()
        save_video_analysis_result(
            self.db,
            user=user,
            filename="outside-scope.mp4",
            file_path="videos/outside-scope.mp4",
            transcript="an out-of-scope transcript",
            analysis_payload={"analysis": {"title": "Outside Scope"}},
            nlp_result={"top_keywords": []},
            recommendation_payload={
                "domain": "unknown",
                "missing_keywords": [],
                "hook_keywords": [],
                "recommended_duration": {"recommended_seconds": 60},
                "classification": {**taxonomy_path("unknown"), "confidence": 0.0},
            },
        )
        saved = self.db.query(AnalysisResult).one()
        self.assertEqual(saved.taxonomy_version, TAXONOMY_VERSION)
        self.assertTrue(saved.classification_is_unknown)

    def test_phase13_migration_adds_taxonomy_columns_to_legacy_schema(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE dataset_contents (dataset_id INTEGER PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE analysis_results (result_id INTEGER PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE model_evaluation_metrics (metric_id INTEGER PRIMARY KEY)"))
        migrate_phase13_taxonomy_schema(engine)
        dataset_columns = {
            item["name"] for item in inspect(engine).get_columns("dataset_contents")
        }
        self.assertIn("taxonomy_leaf_key", dataset_columns)
        self.assertIn("verification_status", dataset_columns)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
