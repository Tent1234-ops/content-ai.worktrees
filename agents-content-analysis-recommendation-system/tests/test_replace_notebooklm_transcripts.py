import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("CONTENT_AI_SKIP_DB_BOOTSTRAP", "1")

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.db import Base
from app.database.models import DatasetContent, SystemLog
from app.services.training_transcript import training_transcript_sha256
from scripts import replace_notebooklm_transcripts as repair


THAI = "\u0e17\u0e14\u0e2a\u0e2d\u0e1a " * 80


class ReplaceNotebookLmTranscriptsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = create_engine("sqlite:///" + str(self.root / "test.db"))
        Base.metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()
        self.tmp.cleanup()

    def add(self, video_id="abcdefghijk", split="test"):
        body = THAI + video_id
        with Session(self.engine) as db:
            row = DatasetContent(
                title="phone sample", transcript=body, transcript_sha256=training_transcript_sha256(body),
                source_youtube_id=video_id, source_record_id=video_id,
                video_url=f"https://www.youtube.com/watch?v={video_id}",
                source_creator="Example channel", source_channel_id="channel-" + video_id,
                category="phone", taxonomy_leaf_key="phone", source_platform="youtube",
                data_split=split, split_strategy="fixed", creator_group_key="a" * 64,
                language="th", is_active=True, is_training_eligible=False,
                is_keyword_recommendation_eligible=False, is_duration_recommendation_eligible=False,
                transcript_acquisition_method="notebooklm_manual_source",
                transcript_timestamps_available=False, transcript_scope="full_video",
                transcript_segment_count=1, transcript_start_seconds=0,
                transcript_end_seconds=180, transcript_window_seconds=180, duration_seconds=180,
                raw_metadata_json=json.dumps({"original": True}), review_notes="Original review",
                views=123, likes=10, comments=2, view_metric_version="youtube_play_start_view_v2",
            )
            db.add(row)
            db.commit()
            dataset_id = row.dataset_id
        path = self.root / f"transcript_{video_id}.md"
        new_body = body + " " + THAI
        entry = {"path": str(path), "status": "parsed", "leaf_key": "phone",
                 "title": "phone sample", "declared_video_id": video_id,
                 "source_url": f"https://www.youtube.com/watch?v={video_id}",
                 "transcript": new_body}
        path.write_text(f"# phone sample\n## Transcript\n{new_body}", encoding="utf-8")
        return dataset_id, entry

    def plan(self, entries, reviews=None):
        with Session(self.engine) as db:
            plan, backup = repair.build_plan(db, entries, title_reviews=reviews)
        for record in plan["records"]:
            if record.get("source_file_sha256"):
                record["source_snapshot_path"] = record["path"]
        return plan, backup

    def test_replaces_in_place_preserving_identity_splits_statistics_and_flags(self):
        first, e1 = self.add(split="test")
        second, e2 = self.add("lmnopqrstuv", split="validation")
        plan, backup = self.plan([e1, e2])
        result = repair.apply_plan(self.engine, plan, [e1, e2], plan_id="a" * 64, backup=backup)
        self.assertEqual(result["updated_dataset_ids"], [first, second])
        with Session(self.engine) as db:
            self.assertEqual(db.query(DatasetContent).count(), 2)
            for dataset_id in (first, second):
                row = db.get(DatasetContent, dataset_id)
                repair.check_preserved(backup[str(dataset_id)], repair.snapshot(row))
                self.assertNotEqual(row.transcript_sha256, backup[str(dataset_id)]["transcript_sha256"])
                metadata = json.loads(row.raw_metadata_json)
                self.assertTrue(metadata["original"])
                self.assertFalse(metadata["transcript_replacements"][0]["fullness_and_word_accuracy_verified"])
            self.assertEqual(db.query(SystemLog).count(), 3)
        rerun, _ = self.plan([e1, e2])
        self.assertEqual([r["status"] for r in rerun["records"]], ["unchanged", "unchanged"])

    def test_rolls_back_all_service_commits_and_logs_on_second_failure(self):
        _, e1 = self.add()
        _, e2 = self.add("lmnopqrstuv")
        plan, backup = self.plan([e1, e2])
        original = repair.update_admin_dataset
        calls = []

        def fail_second(*args, **kwargs):
            calls.append(kwargs["dataset_id"])
            if len(calls) == 2:
                raise RuntimeError("synthetic failure")
            return original(*args, **kwargs)

        with patch.object(repair, "update_admin_dataset", side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
                repair.apply_plan(self.engine, plan, [e1, e2], plan_id="b" * 64, backup=backup)
        with Session(self.engine) as db:
            for row in db.query(DatasetContent).all():
                self.assertEqual(repair.snapshot(row), backup[str(row.dataset_id)])
            self.assertEqual(db.query(SystemLog).count(), 0)

    def test_stale_database_or_source_aborts(self):
        dataset_id, entry = self.add()
        plan, backup = self.plan([entry])
        with Session(self.engine) as db:
            db.get(DatasetContent, dataset_id).views += 1
            db.commit()
        with self.assertRaisesRegex(ValueError, "Database row changed"):
            repair.apply_plan(self.engine, plan, [entry], plan_id="c" * 64, backup=backup)
        plan, backup = self.plan([entry])
        Path(entry["path"]).write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Source file changed"):
            repair.apply_plan(self.engine, plan, [entry], plan_id="d" * 64, backup=backup)

    def test_english_missing_caption_and_mismatched_id_are_blocked(self):
        _, entry = self.add()
        for changes in (
            {"transcript": "This is an English translation, not the Thai transcript. " * 10},
            {"transcript": "No usable captions found " + "x" * 100},
            {"declared_video_id": "lmnopqrstuv"},
            {"leaf_key": "camera"},
        ):
            with self.subTest(changes=changes):
                plan, _ = self.plan([{**entry, **changes}])
                self.assertEqual(plan["records"][0]["status"], "blocked")

    def test_versioned_filename_and_channel_suffix_are_accepted(self):
        _, entry = self.add()
        target = Path(entry["path"]).with_name("transcript_abcdefghijk-v2.md")
        Path(entry["path"]).rename(target)
        entry.update(path=str(target), title="phone sample | Example channel")
        plan, _ = self.plan([entry])
        self.assertEqual(plan["records"][0]["status"], "ready")

    def test_title_override_requires_matching_file_hash_dataset_and_opening(self):
        dataset_id, entry = self.add()
        entry["title"] = "Different title"
        plan, _ = self.plan([entry])
        self.assertEqual(plan["records"][0]["status"], "blocked")
        reviews = {entry["declared_video_id"]: {
            "dataset_id": dataset_id, "source_file_sha256": repair.digest(Path(entry["path"]).read_bytes()),
            "reason": "Reviewed source identity separately",
        }}
        plan, _ = self.plan([entry], reviews)
        self.assertEqual(plan["records"][0]["status"], "ready")
        reviews[entry["declared_video_id"]]["source_file_sha256"] = "0" * 64
        plan, _ = self.plan([entry], reviews)
        self.assertEqual(plan["records"][0]["status"], "blocked")

    def test_duplicate_batch_or_other_dataset_hash_is_blocked(self):
        _, e1 = self.add()
        other_id, e2 = self.add("lmnopqrstuv")
        plan, _ = self.plan([e1, e1])
        self.assertTrue(all(r["status"] == "blocked" for r in plan["records"]))
        with Session(self.engine) as db:
            e1["transcript"] = db.get(DatasetContent, other_id).transcript
        plan, _ = self.plan([e1, e2])
        self.assertEqual(plan["records"][0]["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
