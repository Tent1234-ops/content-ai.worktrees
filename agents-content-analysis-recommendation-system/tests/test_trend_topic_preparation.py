import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.db import Base
from app.database.models import TrendHistoryAttempt, TrendHistoryBucket, TrendSnapshotItem, TrendSnapshotRun
from app.services.trend_history import archive_snapshot_run
from app.services.trend_topic_preparation import (
    choose_evaluation_samples, inspect_topic_sources, validate_preparation_bundle,
    write_preparation_bundle,
)


class TopicPreparationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.now = datetime(2026, 9, 25, 10)
        self.temp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.temp.cleanup()

    def source(self, ids=(1,), *, scope="global", platform="youtube", mode="live",
               status="ok", at=None, titles=None, region="TH", category="Gaming"):
        at = at or self.now
        provider = {"mode": mode, "status": status}
        if scope != "global":
            provider["categories"] = {scope.split(":")[1]: {"mode": mode, "status": status}}
        run = TrendSnapshotRun(region=region, snapshot_kind="global" if scope == "global" else "youtube_categories",
            status="completed" if status in {"ok", "empty"} else "failed", started_at=at, completed_at=at,
            provider_status=json.dumps({platform: provider}))
        for rank, number in enumerate(ids, start=1):
            url = f"https://www.youtube.com/watch?v=v{number:010d}"
            run.items.append(TrendSnapshotItem(platform=platform, ranking_scope=scope,
                trend_key=hashlib.sha1(url.encode()).hexdigest(), provider_rank=rank,
                title=titles[rank-1] if titles else f"Object {number}", category=category,
                source_platform=platform, video_url=url, channel_title=f"Channel {number % 4}",
                description="Never use this description as a topic feature", duration_seconds=100,
                views=0, views_available=True, likes=0, likes_available=False))
        self.db.add(run)
        self.db.flush()
        archive_snapshot_run(self.db, run)
        self.db.commit()
        return run

    def inspect(self, **kwargs):
        return inspect_topic_sources(self.db, now=self.now, days=7, **kwargs)

    def bundle(self, **kwargs):
        report, candidates, observations = self.inspect()
        path = Path(self.temp.name) / "bundle"
        write_preparation_bundle(path, report, candidates, observations, **kwargs)
        return path

    def test_archive_retains_url_and_channel_without_changing_title_only_contract(self):
        run = self.source()
        self.db.delete(run)
        self.db.commit()
        report, candidates, observations = self.inspect()
        self.assertEqual(candidates[0]["video_id"], "v0000000001")
        self.assertEqual(candidates[0]["channel_title"], "Channel 1")
        self.assertEqual(report["input_fields"], ["title"])
        self.assertNotIn("description", observations[0]["items"][0])

    def test_backfill_enriches_same_run_without_changing_original_timestamp(self):
        run = self.source(at=self.now.replace(microsecond=654321))
        bucket = self.db.query(TrendHistoryBucket).one()
        original = json.loads(bucket.first_sample)
        for field in ("first_sample", "last_sample"):
            sample = json.loads(getattr(bucket, field))
            sample["items"][0].pop("video_url")
            sample["items"][0].pop("channel_title")
            setattr(bucket, field, json.dumps(sample))
        run.completed_at = self.now + timedelta(seconds=1)
        self.db.commit()
        archive_snapshot_run(self.db, run)
        self.db.commit()
        for field in ("first_sample", "last_sample"):
            sample = json.loads(getattr(bucket, field))
            self.assertEqual(sample["observed_at"], original["observed_at"])
            self.assertEqual(sample["items"][0]["video_url"], run.items[0].video_url)

    def test_read_only_import_can_disable_schema_bootstrap(self):
        path = Path(self.temp.name) / "must-not-create.db"
        env = dict(os.environ, CONTENT_AI_SKIP_DB_BOOTSTRAP="1", DATABASE_URL=f"sqlite:///{path.as_posix()}")
        run = subprocess.run([sys.executable, "-c", "from app.database.db import engine; assert engine.url.get_backend_name() == 'sqlite'"],
                             env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertFalse(path.exists())

    def test_scope_identity_dedup_and_platform_region_separation(self):
        self.source((1, 2))
        self.source((1, 3), scope="category:20")
        self.source((4,), platform="google")
        self.source((5,), region="US")
        report, candidates, observations = self.inspect()
        self.assertEqual(len(candidates), 3)
        self.assertEqual(len(observations), 3)
        self.assertEqual(next(c for c in candidates if c["video_id"] == "v0000000001")["scopes"], ["category:20", "global"])
        self.assertEqual(len(report["scopes"]), 3)
        self.assertTrue(all(s["available_samples"] == 1 for s in report["scopes"]))

    def test_failed_empty_and_no_observation_are_different(self):
        self.source(at=self.now - timedelta(hours=4))
        self.source((), status="error", at=self.now - timedelta(hours=2))
        self.source((), status="empty")
        report, _, observations = self.inspect()
        self.assertEqual(len(observations), 2)
        scope = report["scopes"][0]
        self.assertEqual(scope["failed_attempts"], 1)
        self.assertEqual(set(i["status"] for i in scope["hours"]), {"observed", "failed", "no_observation"})
        self.assertIn(0, scope["sample_sizes"])

    def test_failure_is_audited_even_when_attempt_archive_is_missing(self):
        self.source((), status="error")
        self.db.query(TrendHistoryAttempt).delete()
        self.db.commit()
        report, candidates, observations = self.inspect()
        self.assertEqual(report["scopes"][0]["failed_attempts"], 1)
        self.assertEqual(report["scopes"][0]["hours"][-1]["status"], "failed")
        self.assertEqual(candidates, [])
        self.assertEqual(observations, [])

    def test_malformed_archive_is_reported_not_a_zero_observation(self):
        run = self.source()
        bucket = self.db.query(TrendHistoryBucket).one()
        bucket.first_sample = '{"broken":'
        bucket.last_sample = '{"broken":'
        self.db.delete(run)
        self.db.commit()
        report, candidates, observations = self.inspect()
        self.assertEqual(report["issues"]["invalid_archive_samples"], 2)
        self.assertEqual(candidates, [])
        self.assertEqual(observations, [])
        self.assertEqual(report["scopes"][0]["archived_samples"], 0)

    def test_non_live_data_is_excluded_and_reads_do_not_mutate(self):
        self.source((1,))
        self.source((2,), mode="mock")
        self.source((3,), status="error")
        before = (self.db.query(TrendSnapshotRun).count(), self.db.query(TrendHistoryBucket).count())
        report, candidates, _ = self.inspect()
        self.assertEqual([c["video_id"] for c in candidates], ["v0000000001"])
        self.assertEqual(report["issues"]["excluded_non_live_or_failed_raw_rows"], 2)
        self.assertEqual(before, (self.db.query(TrendSnapshotRun).count(), self.db.query(TrendHistoryBucket).count()))

    def test_legacy_identity_uses_verified_url_never_title_or_hash_as_id(self):
        self.source((1, 2))
        bucket = self.db.query(TrendHistoryBucket).one()
        for field in ("first_sample", "last_sample"):
            payload = json.loads(getattr(bucket, field))
            for item in payload["items"]:
                item.pop("video_url")
                item.pop("channel_title")
            setattr(bucket, field, json.dumps(payload))
        self.db.commit()
        _, candidates, _ = self.inspect()
        self.assertEqual(len(candidates), 2)
        self.db.query(TrendSnapshotItem).delete()
        self.db.query(TrendSnapshotRun).delete()
        self.db.commit()
        report, candidates, _ = self.inspect()
        self.assertEqual(candidates, [])
        self.assertEqual(report["issues"]["unresolved_video_identity"], 2)

    def test_raw_metadata_missing_counters_do_not_become_known_zeroes(self):
        self.source()
        report, _, _ = self.inspect()
        quality = report["scopes"][0]["raw_metadata_present"]
        self.assertEqual(quality["views"], 1)
        self.assertEqual(quality["likes"], 0)
        self.assertEqual(quality["description"], 1)

    def test_latest_title_variants_kept_and_exact_title_copies_excluded(self):
        self.source((1,), titles=["Old name"], at=self.now - timedelta(hours=1))
        self.source((1, 2, 3), titles=["New name", "OLD  NAME", "Other name"])
        _, candidates, _ = self.inspect()
        one = next(c for c in candidates if c["video_id"] == "v0000000001")
        self.assertEqual(one["title"], "New name")
        self.assertEqual(len(one["title_variants"]), 2)
        splits, selection = choose_evaluation_samples(candidates, size=3, test_size=1)
        self.assertEqual(selection["selected"], 2)
        self.assertEqual(selection["shortfall"], 1)

    def test_balanced_fixed_200_split_no_video_leak_and_deterministic(self):
        for category in range(5):
            self.source(tuple(range(category*50+1, category*50+51)), scope=f"category:{category+1}", category=f"Category {category}")
        report, candidates, observations = self.inspect()
        splits, selected = choose_evaluation_samples(candidates)
        self.assertEqual([len(splits[s]) for s in ("development", "test")], [100, 100])
        self.assertEqual(set(selected["counts"]["test"].values()), {20})
        self.assertEqual((splits, selected), choose_evaluation_samples(list(reversed(candidates))))
        dev_ids = {c["video_id"] for c in splits["development"]}
        self.assertFalse(dev_ids & {c["video_id"] for c in splits["test"]})
        path = self.bundle()
        result = validate_preparation_bundle(path)
        self.assertTrue(result["valid"], result)
        self.assertFalse(result["ready_for_evaluation"])
        self.assertEqual(result["counts"]["test"]["pending"], 100)
        self.assertEqual(len(json.loads((path / "heldout_video_ids.json").read_text())["video_ids"]), 100)
        with self.assertRaises(FileExistsError):
            write_preparation_bundle(path, report, candidates, observations)

    def edit_labels(self, path, *, status="labeled", evidence=None):
        for split in ("development", "test"):
            file = path / split / "labels.csv"
            with file.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                columns, rows = reader.fieldnames, list(reader)
            for row in rows:
                row.update(status=status, topics=json.dumps([row["title"]]) if status == "labeled" else "[]",
                           evidence=json.dumps([evidence or row["title"]]) if status == "labeled" else "[]", annotator="Test annotator")
            with file.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=columns)
                writer.writeheader()
                writer.writerows(rows)

    def test_label_gate_requires_human_labels_and_exact_title_evidence(self):
        self.source((1, 2, 3, 4))
        path = self.bundle(size=4, test_size=2)
        self.edit_labels(path)
        result = validate_preparation_bundle(path)
        self.assertTrue(result["ready_for_evaluation"], result)
        self.edit_labels(path, evidence="Not in the title")
        self.assertFalse(validate_preparation_bundle(path)["valid"])

    def test_ambiguous_needs_notes_and_no_topic_is_a_real_annotation(self):
        self.source((1, 2))
        path = self.bundle(size=2, test_size=1)
        self.edit_labels(path, status="ambiguous")
        self.assertFalse(validate_preparation_bundle(path)["valid"])
        self.edit_labels(path, status="no_topic")
        self.assertTrue(validate_preparation_bundle(path)["ready_for_evaluation"])

    def test_modified_sources_and_missing_files_are_rejected(self):
        self.source((1, 2))
        path = self.bundle(size=2, test_size=1)
        sample_file = path / "test" / "samples.jsonl"
        text = sample_file.read_text(encoding="utf-8")
        sample_file.write_text(text.replace("Object", "Changed"), encoding="utf-8")
        self.assertFalse(validate_preparation_bundle(path)["valid"])
        sample_file.unlink()
        self.assertFalse(validate_preparation_bundle(path)["valid"])

    def test_formula_title_is_safe_in_csv_original_in_jsonl(self):
        self.source((1, 2), titles=["=SUM(1,2)", "@name"])
        path = self.bundle(size=2, test_size=1)
        self.assertTrue(validate_preparation_bundle(path)["valid"])
        for split in ("development", "test"):
            sample = json.loads((path / split / "samples.jsonl").read_text(encoding="utf-8"))
            with (path / split / "labels.csv").open(encoding="utf-8-sig") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["title"], "'" + sample["title"])

    def test_empty_database_does_not_invent_samples_or_claim_readiness(self):
        path = self.bundle()
        result = validate_preparation_bundle(path)
        self.assertTrue(result["valid"])
        self.assertFalse(result["ready_for_evaluation"])
        self.assertEqual(result["counts"], {"development": {}, "test": {}})


if __name__ == "__main__":
    unittest.main()
