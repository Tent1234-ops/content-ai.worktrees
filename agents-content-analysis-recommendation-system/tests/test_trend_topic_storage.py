import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("CONTENT_AI_SKIP_DB_BOOTSTRAP", "1")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.db import Base, get_db
from app.database.models import (
    TrendHistoryAttempt, TrendHistoryBucket, TrendSnapshotItem, TrendSnapshotRun, TrendTopic, TrendTopicAlias, TrendTopicCount,
    TrendTopicDefinition, TrendTopicEvidence, TrendTopicJob, TrendTopicObservation, TrendTopicVersion,
)
from app.routes.trend_topics import router
from app.services.trend_history import archive_snapshot_run
from app.services.trend_topic_history import load_job_evidence, load_topic_history
from app.services.trend_topic_processing import claim_job, drain_topic_jobs, process_next_job
from app.services.trend_topic_store import (
    CATALOG, activate_version, active_version, backfill_topic_observations,
    packed, register_version, store_observation,
    runtime_manifest,
)


class TopicStorageTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine)
        self.db = self.factory()
        self.at = datetime.utcnow().replace(microsecond=0)
        self.catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        self.version = active_version(self.db).version_id
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def store(self, run_id=1, title="แกะกล่องสกุชชี้ สกุชชี่", video_id="abcde123456", scope="global", at=None, **kwargs):
        items = [{"title": title, "rank": 1, "video_url": f"https://youtu.be/{video_id}"}]
        row = store_observation(self.db, run_id=run_id, region="TH", scope=scope,
            observed_at=at or self.at, items=kwargs.pop("items", items), **kwargs)
        self.db.commit()
        return row.observation_id

    def history(self, **kwargs):
        self.db.expire_all()
        return load_topic_history(self.db, now=self.at + timedelta(minutes=1), **kwargs)

    def test_registry_is_versioned_and_stable_ids_survive_rename(self):
        changed = copy.deepcopy(self.catalog)
        changed["version"] = "rename-v2"
        changed["topics"][0]["label"] = "Squishy toys"
        newer = register_version(self.db, changed)
        self.db.commit()
        self.assertNotEqual(newer.version_id, self.version)
        self.assertEqual(register_version(self.db, changed).version_id, newer.version_id)
        self.assertEqual(self.db.query(TrendTopic).count(), 2)
        self.assertEqual(self.db.query(TrendTopicDefinition).count(), 4)
        self.assertEqual(self.db.query(TrendTopicAlias).count(), 12)
        old_label = self.db.get(TrendTopicDefinition, (self.version, "squishy")).label
        self.assertEqual(old_label, "สกุชชี้")

    def test_activation_fences_unfinished_old_jobs_and_enqueues_all_pages(self):
        for run in range(1, 206):
            store_observation(self.db, run_id=run, region="TH", scope="global", observed_at=self.at, items=[])
        self.db.commit()
        changed = copy.deepcopy(self.catalog)
        changed["version"] = "next"
        new = register_version(self.db, changed)
        self.assertEqual(activate_version(self.db, new.version_id), 205)
        self.db.commit()
        self.assertEqual(self.db.query(TrendTopicJob).filter_by(status="superseded").count(), 205)
        self.assertEqual(self.db.query(TrendTopicJob).filter_by(status="pending").count(), 205)
        self.assertEqual(activate_version(self.db, new.version_id), 0)

    def test_returning_to_an_older_catalog_resumes_its_superseded_jobs(self):
        self.store()
        changed = copy.deepcopy(self.catalog)
        changed["version"] = "next"
        new = register_version(self.db, changed)
        activate_version(self.db, new.version_id)
        self.db.commit()
        self.assertEqual(activate_version(self.db, self.version), 1)
        self.db.commit()
        self.assertEqual(drain_topic_jobs(self.factory)["statuses"], {"completed": 1})
        self.assertEqual(self.history()["version_id"], self.version)
        self.assertEqual(self.history()["points"][0]["counts"]["squishy"], 1)

    def test_replay_never_overwrites_source_or_duplicates_job(self):
        source_id = self.store()
        self.store(title="changed", at=self.at + timedelta(hours=1))
        self.assertEqual(self.db.query(TrendTopicObservation).count(), 1)
        self.assertEqual(self.db.query(TrendTopicJob).count(), 1)
        source = self.db.get(TrendTopicObservation, source_id)
        self.assertEqual(source.observed_at, self.at)
        self.assertIn("สกุชชี้", source.payload_json)
        self.assertEqual(drain_topic_jobs(self.factory)["statuses"], {"completed": 1})
        self.assertEqual(drain_topic_jobs(self.factory)["processed"], 0)
        self.assertEqual(self.db.query(TrendTopicEvidence).count(), 1)
        self.assertEqual(self.db.query(TrendTopicCount).count(), 2)

    def test_repeated_aliases_count_one_video_and_related_objects_stay_separate(self):
        self.store(title="สกุชชี้ สกุชชี่ กล่องสุ่ม")
        drain_topic_jobs(self.factory)
        point = self.history()["points"][0]
        self.assertEqual(point["counts"], {"squishy": 1, "blind_box": 1})
        proof = load_job_evidence(self.db, point["job_id"])
        self.assertEqual(proof["version_id"], self.version)
        for topic in proof["evidence"][0]["matches"]:
            for span in topic["evidence"]:
                self.assertEqual(proof["evidence"][0]["title"][span["start"]:span["end"]], span["text"])

    def test_same_title_different_videos_count_distinct_ids_not_title_strings(self):
        self.store(items=[{"title": "สกุชชี้", "rank": i, "video_url": f"https://youtu.be/{v}"}
                          for i, v in enumerate(("abcde123456", "abcde123457"), 1)])
        drain_topic_jobs(self.factory)
        self.assertEqual(self.history()["points"][0]["counts"]["squishy"], 2)

    def test_duplicate_video_in_scope_counts_once(self):
        self.store(items=[{"title": "สกุชชี้", "rank": i, "video_url": "https://youtu.be/abcde123456"}
                          for i in (1, 2)])
        drain_topic_jobs(self.factory)
        self.assertEqual(self.history()["points"][0]["counts"]["squishy"], 1)

    def test_scopes_are_not_added_together(self):
        self.store()
        self.store(scope="category:20")
        drain_topic_jobs(self.factory)
        self.assertEqual(len(self.history()["points"]), 1)
        self.assertEqual(self.history(scope="category:20")["points"][0]["counts"]["squishy"], 1)

    def test_vague_title_abstains(self):
        self.store(title="ไม่คิดว่าจะเจอสิ่งนี้!")
        drain_topic_jobs(self.factory)
        point = self.history()["points"][0]
        self.assertEqual(point["counts"], {"squishy": 0, "blind_box": 0})
        self.assertEqual(load_job_evidence(self.db, point["job_id"])["evidence"][0]["status"], "unknown")

    def test_failed_and_missing_are_null_but_confirmed_empty_is_zero(self):
        self.store(1, status="failed", items=[])
        self.store(2, status="missing_source", items=[])
        self.store(3, items=[])
        drain_topic_jobs(self.factory)
        points = self.history()["points"]
        self.assertIsNone(points[0]["counts"])
        self.assertIsNone(points[1]["counts"])
        self.assertEqual(points[2]["counts"]["squishy"], 0)
        self.assertEqual(self.db.query(TrendTopicJob).count(), 1)

    def test_invalid_video_identity_never_becomes_zero(self):
        self.store(video_id="invalid")
        drain_topic_jobs(self.factory)
        point = self.history()["points"][0]
        self.assertEqual(point["status"], "insufficient_source")
        self.assertIsNone(point["counts"])

    def test_only_real_times_are_returned_no_fill_for_uncollected_days(self):
        self.store(1, at=self.at - timedelta(days=4))
        self.store(2)
        drain_topic_jobs(self.factory)
        points = self.history()["points"]
        self.assertEqual(len(points), 2)
        self.assertEqual(points[1]["gap_seconds_before"], 4 * 86400)

    def test_new_version_blocks_comparison_until_whole_period_recomputed(self):
        self.store(1)
        self.store(2, title="Squishy toy")
        drain_topic_jobs(self.factory)
        changed = copy.deepcopy(self.catalog)
        changed["version"] = "rules-v2"
        changed["topics"][0]["aliases"] = [{"text": "สกุชชี้"}]
        newer = register_version(self.db, changed)
        self.assertEqual(activate_version(self.db, newer.version_id), 2)
        self.db.commit()
        process_next_job(self.factory)
        result = self.history()
        self.assertEqual(result["status"], "recalculation_required")
        self.assertEqual(result["points"], [])
        self.assertEqual(self.history(version_id=self.version)["status"], "ready")
        drain_topic_jobs(self.factory)
        self.assertEqual(self.history()["points"][1]["counts"]["squishy"], 0)
        self.assertEqual(self.history(version_id=self.version)["points"][1]["counts"]["squishy"], 1)

    def test_snapshot_transaction_captures_and_survives_raw_deletion(self):
        run = TrendSnapshotRun(region="TH", snapshot_kind="global", status="completed",
            started_at=self.at, completed_at=self.at,
            provider_status=packed({"youtube": {"status": "ok", "mode": "live"}}))
        run.items = [TrendSnapshotItem(platform="youtube", ranking_scope="global", trend_key="a",
            provider_rank=1, title="สกุชชี้", category="Gaming", source_platform="youtube",
            video_url="https://youtu.be/abcde123456")]
        self.db.add(run)
        self.db.flush()
        archive_snapshot_run(self.db, run)
        self.db.commit()
        self.db.delete(run)
        self.db.commit()
        drain_topic_jobs(self.factory)
        self.assertEqual(self.history()["points"][0]["counts"]["squishy"], 1)

    def test_rollback_does_not_publish_partial_snapshot_job(self):
        store_observation(self.db, run_id=1, region="TH", scope="global", observed_at=self.at, items=[])
        self.db.rollback()
        self.assertEqual(self.db.query(TrendTopicObservation).count(), 0)
        self.assertEqual(self.db.query(TrendTopicJob).count(), 0)

    def test_expired_claim_is_recovered_but_unexpired_claim_not_stolen(self):
        self.store()
        now = datetime.utcnow() + timedelta(seconds=1)
        claim = claim_job(self.factory, now=now)
        self.assertIsNotNone(claim)
        self.assertEqual(process_next_job(self.factory, now=now + timedelta(seconds=1))["status"], "idle")
        self.assertEqual(process_next_job(self.factory, now=now + timedelta(minutes=6))["status"], "completed")
        self.assertEqual(self.db.query(TrendTopicEvidence).count(), 1)

    def test_expired_worker_cannot_publish_after_another_worker_claims(self):
        from app.services.trend_topic_processing import count_observation
        self.store()
        now = datetime.utcnow() + timedelta(seconds=1)

        def steal_and_compute(payload, catalog):
            self.assertIsNotNone(claim_job(self.factory, now=now + timedelta(minutes=6)))
            return count_observation(payload, catalog)

        with patch("app.services.trend_topic_processing.count_observation", side_effect=steal_and_compute):
            self.assertEqual(process_next_job(self.factory, now=now)["status"], "lease_lost")
        self.assertEqual(self.db.query(TrendTopicEvidence).count(), 0)
        self.assertEqual(process_next_job(self.factory, now=now + timedelta(minutes=12))["status"], "completed")
        self.assertEqual(self.db.query(TrendTopicEvidence).count(), 1)

    def test_publication_failure_rolls_back_completed_status_and_evidence(self):
        self.store()
        with patch("app.services.trend_topic_processing.TrendTopicCount", side_effect=RuntimeError("write failed")):
            self.assertEqual(process_next_job(self.factory)["status"], "error")
        self.assertEqual(self.db.query(TrendTopicEvidence).count(), 0)
        self.assertEqual(self.db.query(TrendTopicCount).count(), 0)
        self.assertEqual(self.db.query(TrendTopicJob).one().status, "pending")

    def test_worker_transaction_rolls_back_all_evidence_on_failure(self):
        self.store()
        with patch("app.services.trend_topic_processing.count_observation", side_effect=RuntimeError("private detail")):
            self.assertEqual(process_next_job(self.factory)["status"], "error")
        self.assertEqual(self.db.query(TrendTopicEvidence).count(), 0)
        self.assertEqual(self.db.query(TrendTopicCount).count(), 0)
        self.assertEqual(self.history()["status"], "recalculation_required")
        job = self.db.query(TrendTopicJob).one()
        self.assertEqual(job.error_code, "RuntimeError")

    def test_changed_code_and_tampered_sources_are_rejected(self):
        source_id = self.store()
        source = self.db.get(TrendTopicObservation, source_id)
        source.payload_json = "[]"
        self.db.commit()
        self.assertEqual(process_next_job(self.factory)["status"], "error")
        self.db.expire_all()
        self.assertEqual(self.db.query(TrendTopicJob).one().error_code, "SourceIntegrityMismatch")
        self.store(2)
        with patch("app.services.trend_topic_processing.runtime_manifest", return_value={}):
            self.assertEqual(process_next_job(self.factory)["status"], "error")
        self.assertEqual(self.db.query(TrendTopicEvidence).count(), 0)

    def test_catalog_cannot_be_changed_under_an_existing_version_id(self):
        self.store()
        row = self.db.get(TrendTopicVersion, self.version)
        altered = json.loads(row.catalog_json)
        altered["topics"][0]["aliases"] = [{"text": "everything"}]
        row.catalog_json = packed(altered)
        self.db.commit()
        self.assertEqual(process_next_job(self.factory)["status"], "error")
        self.db.expire_all()
        self.assertEqual(self.db.query(TrendTopicJob).one().error_code, "VersionIntegrityMismatch")

    def test_running_process_cannot_claim_to_use_newly_edited_code(self):
        with patch("app.services.trend_topic_store._build_manifest", return_value={}):
            with self.assertRaisesRegex(ValueError, "ExtractorBuildMismatch"):
                runtime_manifest()

    def test_backfill_without_sources_creates_no_fake_observations(self):
        self.assertEqual(backfill_topic_observations(self.db, now=self.at)["new_observations"], 0)
        self.assertEqual(self.db.query(TrendTopicObservation).count(), 0)

    def test_backfill_archive_only_is_idempotent_and_records_missing_intermediate_titles(self):
        sample = {"run_id": 40, "observed_at": self.at.isoformat() + "Z",
            "items": [{"key": "old", "title": "สกุชชี้", "rank": 1, "category": "Gaming",
                       "video_url": "https://youtu.be/abcde123456", "channel_title": "example"}]}
        self.db.add(TrendHistoryBucket(region="TH", platform="youtube", ranking_scope="global",
            bucket_at=self.at.replace(minute=0, second=0), first_at=self.at, last_at=self.at,
            first_sample=packed(sample), last_sample=packed(sample)))
        self.db.add(TrendHistoryAttempt(run_id=39, region="TH", platform="youtube", ranking_scope="global",
            observed_at=self.at - timedelta(minutes=1), status="observed", sample_count=50))
        self.db.commit()
        self.assertEqual(backfill_topic_observations(self.db, now=self.at)["new_observations"], 2)
        self.db.commit()
        self.assertEqual(backfill_topic_observations(self.db, now=self.at)["new_observations"], 0)
        self.db.commit()
        drain_topic_jobs(self.factory)
        points = self.history()["points"]
        self.assertIsNone(points[0]["counts"])
        self.assertEqual(points[0]["status"], "missing_source")
        self.assertEqual(points[1]["counts"]["squishy"], 1)

    def test_public_read_does_not_run_extractor_or_mutate_jobs_and_admin_is_protected(self):
        self.store()
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        client = TestClient(app)
        with patch("app.services.trend_topic_processing.count_observation", side_effect=AssertionError("NLP on read")):
            result = client.get("/dashboard/public/topics/history")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["status"], "recalculation_required")
        self.assertEqual(client.get("/admin/trend-topics/status").status_code, 401)
        self.assertEqual(client.post("/admin/trend-topics/versions", json={"catalog": self.catalog, "reason": "test"}).status_code, 401)
        self.assertEqual(self.db.query(TrendTopicJob).one().status, "pending")

    def test_persists_across_engine_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            url = "sqlite:///" + str(Path(directory) / "topics.db")
            engine = create_engine(url)
            Base.metadata.create_all(engine)
            factory = sessionmaker(bind=engine)
            with factory() as db:
                store_observation(db, run_id=88, region="TH", scope="global", observed_at=self.at,
                    items=[{"title": "สกุชชี้", "rank": 1, "video_url": "https://youtu.be/abcde123456"}])
                db.commit()
            engine.dispose()
            engine = create_engine(url)
            factory = sessionmaker(bind=engine)
            self.assertEqual(drain_topic_jobs(factory)["statuses"], {"completed": 1})
            with factory() as db:
                self.assertEqual(load_topic_history(db)["points"][0]["counts"]["squishy"], 1)
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
