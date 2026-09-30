import hashlib
import json
import unittest
from unittest.mock import patch
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.db import Base
from app.database.models import DatasetCollectionRun, DatasetContent, SystemLog
from app.schemas.admin_report import AdminDatasetUpdate
from app.services.admin_report import update_admin_dataset, delete_admin_dataset, restore_admin_dataset, list_admin_datasets
from app.services.dataset_eligibility import production_transcript_query
from app.services.dataset_contract import (
    NOTEBOOKLM_TRANSCRIPT_ACQUISITION,
    NOTEBOOKLM_TRANSCRIPT_SOURCE,
    SPLIT_STRATEGY,
    TRANSCRIPT_SCOPE_FULL_VIDEO,
    YOUTUBE_LICENSE_INFO_URL,
    YOUTUBE_PUBLIC_DATASET_SOURCE,
    YOUTUBE_STANDARD_LICENSE_NAME,
    channel_dataset_split,
)
from app.services.taxonomy import TAXONOMY_VERSION, taxonomy_path
from app.services.training_transcript import normalize_training_transcript


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class AdminDatasetCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.run = DatasetCollectionRun(
            run_key=_hash("admin-correction-run"),
            dataset_source=YOUTUBE_PUBLIC_DATASET_SOURCE,
            dataset_version="admin-correction-test-v1",
            status="reviewed",
            region_code="TH",
            languages_json='["th"]',
            query_config_json="{}",
        )
        self.db.add(self.run)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _add_dataset(self, *, video_id: str, leaf_key: str, transcript: str):
        path = taxonomy_path(leaf_key)
        transcript = normalize_training_transcript(transcript)
        split, creator_group_key = channel_dataset_split(f"channel-{video_id}")
        now = datetime.utcnow()
        row = DatasetContent(
            title=f"{leaf_key} review",
            video_url=f"https://www.youtube.com/watch?v={video_id}",
            transcript=transcript,
            category=leaf_key,
            source_platform="youtube",
            dataset_source=YOUTUBE_PUBLIC_DATASET_SOURCE,
            dataset_version="admin-correction-test-v1",
            collection_run_id=self.run.collection_run_id,
            source_record_id=video_id,
            source_youtube_id=video_id,
            source_creator=f"Creator {video_id}",
            source_channel_id=f"channel-{video_id}",
            source_category="28",
            source_subcategory=leaf_key,
            collection_query=f"{leaf_key} review",
            source_release_url=f"https://www.youtube.com/watch?v={video_id}",
            source_archive_sha256=_hash("candidate-artifact"),
            source_annotation_path="data/reviews/admin-correction.csv",
            source_annotation_sha256=_hash("review-artifact"),
            import_batch_id=_hash("import-batch"),
            taxonomy_version=TAXONOMY_VERSION,
            taxonomy_leaf_key=leaf_key,
            category_level_1=path["category_level_1"],
            category_level_2=path["category_level_2"],
            category_level_3=path["category_level_3"],
            language="th",
            verification_status="human_verified",
            label_source="human_review",
            license_name=YOUTUBE_STANDARD_LICENSE_NAME,
            license_url=YOUTUBE_LICENSE_INFO_URL,
            data_split=split,
            split_strategy=SPLIT_STRATEGY,
            creator_group_key=creator_group_key,
            transcript_sha256=_hash(transcript),
            transcript_segment_count=20,
            transcript_start_seconds=0,
            transcript_end_seconds=180,
            transcript_window_seconds=180,
            transcript_source=NOTEBOOKLM_TRANSCRIPT_SOURCE,
            transcript_acquisition_method=NOTEBOOKLM_TRANSCRIPT_ACQUISITION,
            transcript_scope=TRANSCRIPT_SCOPE_FULL_VIDEO,
            transcript_timestamps_available=False,
            caption_type="unspecified",
            transcript_quality="good",
            reviewed_by="original-reviewer",
            reviewed_at=now,
            statistics_captured_at=now,
            license_verified_at=now,
            raw_metadata_json=json.dumps({"source": "notebooklm"}),
            collection_strategy="classification_diverse",
            is_training_eligible=True,
            is_keyword_recommendation_eligible=True,
            is_duration_recommendation_eligible=True,
            is_active=True,
            duration_seconds=180,
            published_at=now,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def test_trash_restore_preserves_content_split_and_permissions_after_restart(self):
        row = self._add_dataset(video_id="restore0001", leaf_key="phone",
                                transcript="phone battery camera display performance " * 8)
        saved = (row.dataset_id, row.transcript, row.transcript_sha256, row.data_split, row.creator_group_key)
        delete_admin_dataset(self.db, dataset_id=row.dataset_id, confirmation_id=row.dataset_id, user_id=9)
        self.assertEqual(list_admin_datasets(self.db)[0], 0)
        self.assertEqual(list_admin_datasets(self.db, trashed=True)[0], 1)
        self.db.close()
        self.db = sessionmaker(bind=self.engine)()
        restored = restore_admin_dataset(self.db, dataset_id=saved[0], confirmation_id=saved[0], user_id=9)
        self.assertEqual((restored.dataset_id, restored.transcript, restored.transcript_sha256,
                          restored.data_split, restored.creator_group_key), saved)
        self.assertTrue(restored.is_active and restored.is_training_eligible)
        self.assertTrue(restored.is_keyword_recommendation_eligible)
        self.assertIsNone(restored.deleted_at)
        self.assertIsNone(restored.deletion_state_json)
        self.assertEqual(list_admin_datasets(self.db, trashed=True)[0], 0)
        self.assertIsNone(restore_admin_dataset(self.db, dataset_id=saved[0], confirmation_id=saved[0], user_id=9))
        self.assertEqual(self.db.query(SystemLog).filter_by(action="admin_dataset_restore").count(), 1)

    def test_failed_restore_commit_rolls_back_flags_and_success_log(self):
        row = self._add_dataset(video_id="restore0003", leaf_key="phone",
                                transcript="phone battery camera display performance " * 8)
        dataset_id = row.dataset_id
        delete_admin_dataset(self.db, dataset_id=dataset_id, confirmation_id=dataset_id, user_id=9)
        with patch.object(self.db, 'commit', side_effect=RuntimeError('database write failed')):
            with self.assertRaises(RuntimeError):
                restore_admin_dataset(self.db, dataset_id=dataset_id, confirmation_id=dataset_id, user_id=9)
        self.assertIsNotNone(self.db.get(DatasetContent, dataset_id).deleted_at)
        self.assertFalse(self.db.get(DatasetContent, dataset_id).is_training_eligible)
        self.assertEqual(self.db.query(SystemLog).filter_by(action='admin_dataset_restore').count(), 0)

    def test_restore_cannot_reenable_invalid_training_contract(self):
        row = self._add_dataset(video_id="restore0002", leaf_key="phone",
                                transcript="phone battery camera display performance " * 8)
        delete_admin_dataset(self.db, dataset_id=row.dataset_id, confirmation_id=row.dataset_id, user_id=9)
        row.transcript_quality = "bad"
        self.db.commit()
        with self.assertRaises(ValueError):
            restore_admin_dataset(self.db, dataset_id=row.dataset_id, confirmation_id=row.dataset_id, user_id=9)
        self.assertIsNotNone(row.deleted_at)
        self.assertFalse(row.is_training_eligible)
        self.assertEqual(self.db.query(SystemLog).filter_by(action="admin_dataset_restore").count(), 0)

    def test_deleted_training_row_is_excluded_even_if_legacy_code_resets_flags(self):
        row = self._add_dataset(video_id="archive0001", leaf_key="phone",
                                transcript="phone battery camera display performance " * 8)
        self.assertEqual(production_transcript_query(self.db).count(), 1)
        delete_admin_dataset(self.db, dataset_id=row.dataset_id, confirmation_id=row.dataset_id, user_id=9)
        self.assertEqual(production_transcript_query(self.db).count(), 0)
        row.is_active = True
        row.is_training_eligible = True
        row.is_keyword_recommendation_eligible = True
        row.is_duration_recommendation_eligible = True
        self.db.commit()
        self.assertEqual(production_transcript_query(self.db).count(), 0)

    def test_transcript_and_leaf_correction_updates_all_derived_fields(self):
        old_transcript = "phone battery display camera " * 8
        row = self._add_dataset(
            video_id="phone000001",
            leaf_key="phone",
            transcript=old_transcript,
        )
        edited = "  mirrorless &amp; lens\n sensor aperture photography  " * 8

        updated = update_admin_dataset(
            self.db,
            dataset_id=row.dataset_id,
            payload=AdminDatasetUpdate(
                transcript=edited,
                taxonomy_leaf_key="camera",
            ),
            user_id=9,
            reviewer="admin1",
        )

        expected_transcript = " ".join(edited.replace("&amp;", "&").split())
        camera_path = taxonomy_path("camera")
        self.assertIsNotNone(updated)
        self.assertEqual(updated.transcript, expected_transcript)
        self.assertEqual(updated.transcript_sha256, _hash(expected_transcript))
        self.assertEqual(updated.category, "camera")
        self.assertEqual(updated.taxonomy_leaf_key, "camera")
        self.assertEqual(updated.taxonomy_version, TAXONOMY_VERSION)
        self.assertEqual(updated.category_level_1, camera_path["category_level_1"])
        self.assertEqual(updated.category_level_2, camera_path["category_level_2"])
        self.assertEqual(updated.category_level_3, camera_path["category_level_3"])
        self.assertEqual(updated.reviewed_by, "admin1")
        self.assertIsNotNone(updated.reviewed_at)

        log = self.db.query(SystemLog).order_by(SystemLog.log_id.desc()).first()
        self.assertEqual(log.action, "admin_dataset_training_content_corrected")
        self.assertIn("taxonomy=phone->camera", log.detail)
        self.assertIn("model_retrain_required=true", log.detail)

    def test_duplicate_transcript_is_rejected_without_changing_row(self):
        first_transcript = "camera sensor lens aperture photography " * 8
        second_transcript = "laptop processor memory keyboard display " * 8
        self._add_dataset(
            video_id="camera00001",
            leaf_key="camera",
            transcript=first_transcript,
        )
        row = self._add_dataset(
            video_id="laptop00001",
            leaf_key="laptop",
            transcript=second_transcript,
        )

        with self.assertRaisesRegex(ValueError, "duplicates existing dataset"):
            update_admin_dataset(
                self.db,
                dataset_id=row.dataset_id,
                payload=AdminDatasetUpdate(transcript=first_transcript),
                reviewer="admin1",
            )

        self.db.expire_all()
        unchanged = self.db.get(DatasetContent, row.dataset_id)
        expected_transcript = normalize_training_transcript(second_transcript)
        self.assertEqual(unchanged.transcript, expected_transcript)
        self.assertEqual(unchanged.transcript_sha256, _hash(expected_transcript))


if __name__ == "__main__":
    unittest.main()
