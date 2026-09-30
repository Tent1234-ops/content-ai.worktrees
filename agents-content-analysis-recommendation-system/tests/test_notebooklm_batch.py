import tempfile
import unittest
from unittest.mock import Mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.db import Base
from app.database.models import DatasetContent, DatasetReviewEvent, SystemLog, User
from app.services.dataset_contract import channel_dataset_split
from app.services.taxonomy import sync_taxonomy_registry
from app.services.youtube_cc_dataset import YouTubeCCDatasetError, list_youtube_cc_review_queue, review_youtube_cc_candidate
from scripts.import_notebooklm_batch import audit_entries, attach_metadata, enqueue_entries, summarize
from tests.test_youtube_cc_dataset import _video


def entry(video_id="abcdefghijk", *, leaf="phone"):
    return {"path": f"{leaf}/{video_id}.md", "status": "parsed", "leaf_key": leaf,
            "title": "Fixture source", "source_url": f"https://youtu.be/{video_id}",
            "declared_video_id": video_id,
            "transcript": f"Fixture transcript for {video_id}. " + "Spoken content from the source. " * 8}


class NotebookLMBatchTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        sync_taxonomy_registry(self.db)
        self.admin = User(username="batch-admin", email="batch@example.test", password_hash="fixture",
                          role="admin", is_active=True)
        self.db.add(self.admin)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_audit_separates_existing_batch_duplicate_and_invalid_sources(self):
        self.db.add(DatasetContent(title="Existing", source_youtube_id="abcdefghijk",
                                  taxonomy_leaf_key="camera", data_split="test"))
        self.db.commit()
        inputs = [entry(), entry("lmnopqrstuv"), entry("lmnopqrstuv"),
                  {"path": "missing.md", "leaf_key": "laptop", "status": "invalid", "error": "No transcript"},
                  {**entry("12345678901"), "declared_video_id": "xxxxxxxxxxx"}]
        rows, _ = audit_entries(self.db, inputs)
        self.assertEqual([row["status"] for row in rows],
                         ["duplicate_video", "needs_metadata", "duplicate_in_batch", "invalid", "invalid"])
        self.assertEqual(rows[0]["existing_split"], "test")
        self.assertEqual(self.db.query(DatasetContent).count(), 1)
        self.assertEqual(self.db.query(DatasetReviewEvent).count(), 0)

    def test_metadata_batches_50_and_preserves_channel_conflicts_and_missing(self):
        channel = "UC" + "a" * 22
        assigned, _ = channel_dataset_split(channel)
        old_split = "test" if assigned != "test" else "train"
        self.db.add(DatasetContent(title="Channel reservation", source_channel_id=channel, data_split=old_split))
        self.db.commit()
        inputs = [entry(f"{index:011d}") for index in range(52)]
        rows, _ = audit_entries(self.db, inputs)

        def getter(resource, **kwargs):
            self.assertEqual(resource, "videos")
            result = []
            for index, video_id in enumerate(kwargs["id"].split(",")):
                if video_id == "00000000051":
                    continue
                item = _video(video_id, index)
                item["snippet"]["channelId"] = channel
                result.append(item)
            return {"items": result}

        api = Mock(side_effect=getter)
        attach_metadata(self.db, rows, api_key="fixture", getter=api)
        self.assertEqual(api.call_count, 2)
        self.assertEqual([len(call.kwargs["id"].split(",")) for call in api.call_args_list], [50, 2])
        self.assertEqual(rows[0]["status"], "split_conflict")
        self.assertEqual(rows[0]["data_split"], assigned)
        self.assertEqual(rows[-1]["status"], "metadata_unavailable")

    def test_import_only_creates_pending_candidates_and_can_be_rerun_without_duplicates(self):
        inputs = [entry(), entry("lmnopqrstuv")]
        rows, _ = audit_entries(self.db, inputs)
        api = Mock(return_value={"items": [_video("abcdefghijk"), _video("lmnopqrstuv", 1)]})
        metadata = attach_metadata(self.db, rows, api_key="fixture", getter=api)
        with tempfile.TemporaryDirectory() as folder:
            runs = enqueue_entries(self.db, inputs, rows, metadata, api_key="fixture",
                                   admin_user_id=self.admin.user_id, artifact_root=folder)
            self.assertEqual(len(runs), 1)
            self.assertEqual([row["status"] for row in rows], ["pending_review"] * 2)
            self.assertEqual(self.db.query(DatasetContent).count(), 0)
            self.assertEqual(self.db.query(DatasetReviewEvent).count(), 0)
            self.assertEqual(self.db.query(SystemLog).count(), 2)
            queue = list_youtube_cc_review_queue(self.db, review_status="pending")
            self.assertEqual(len(queue["items"]), 2)
            repeated, _ = audit_entries(self.db, inputs)
            self.assertEqual([row["status"] for row in repeated], ["duplicate_video"] * 2)
            self.assertEqual(summarize(rows)["phone"]["files"], 2)
            self.assertEqual(api.call_count, 1)

    def test_non_admin_cannot_enqueue(self):
        self.admin.role = "user"
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "active admin"):
            enqueue_entries(self.db, [], [], {}, api_key="fixture", admin_user_id=self.admin.user_id)

    def test_pending_approval_verifies_hash_and_cannot_overwrite_existing_review(self):
        inputs = [entry(), entry('lmnopqrstuv')]
        rows, _ = audit_entries(self.db, inputs)
        metadata = attach_metadata(self.db, rows, api_key='fixture', getter=Mock(return_value={
            'items': [_video('abcdefghijk'), _video('lmnopqrstuv', 1)]}))
        with tempfile.TemporaryDirectory() as folder:
            enqueue_entries(self.db, inputs, rows, metadata, api_key='fixture',
                            admin_user_id=self.admin.user_id, artifact_root=folder)
            candidates = list_youtube_cc_review_queue(self.db, review_status='pending')['items']
            for index, candidate in enumerate(candidates):
                kwargs = dict(collection_run_id=candidate['collection_run_id'],
                    source_youtube_id=candidate['source_youtube_id'], decision='approve', reviewer='fixture-admin',
                    reviewed_leaf_key='phone', transcript_quality='good', review_root=folder,
                    require_pending=True)
                for bad_hash in [None, '0' * 64]:
                    with self.assertRaises(YouTubeCCDatasetError):
                        review_youtube_cc_candidate(self.db, **kwargs, expected_candidate_sha256=bad_hash)
                    self.db.rollback()
                if index == 1:
                    review_youtube_cc_candidate(self.db, **{**kwargs, 'decision': 'reject'},
                                               expected_candidate_sha256=candidate['candidate_sha256'])
                else:
                    result = review_youtube_cc_candidate(self.db, **kwargs,
                                               expected_candidate_sha256=candidate['candidate_sha256'])
                    self.assertIsNotNone(result['dataset_id'])
                    self.assertIsNotNone(result['review_event_id'])
                with self.assertRaisesRegex(YouTubeCCDatasetError, 'already reviewed'):
                    review_youtube_cc_candidate(self.db, **kwargs,
                                               expected_candidate_sha256=candidate['candidate_sha256'])
                self.db.rollback()
            self.assertEqual(self.db.query(DatasetContent).count(), 1)
            self.assertEqual(self.db.query(DatasetReviewEvent).count(), 2)
            self.assertEqual(list_youtube_cc_review_queue(self.db, review_status='pending')['total'], 0)

    def test_rejected_candidate_is_not_reported_as_success(self):
        inputs = [entry()]
        rows, _ = audit_entries(self.db, inputs)
        metadata = attach_metadata(self.db, rows, api_key="fixture",
                                   getter=Mock(return_value={"items": [_video("abcdefghijk")]}))
        enqueue_entries(self.db, inputs, rows, metadata, api_key="fixture", admin_user_id=self.admin.user_id,
                        importer=Mock(side_effect=YouTubeCCDatasetError("Video already exists")))
        self.assertEqual(rows[0]["status"], "import_rejected")
        self.assertEqual(self.db.query(SystemLog).count(), 0)


if __name__ == "__main__":
    unittest.main()
