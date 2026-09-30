import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_current_user
from app.database.db import Base, get_db
from app.database.models import (
    ClipRevisionComparison,
    ClipRevisionPlan,
    User,
    UserContent,
)
from app.routes.analyze import analyze_revision_video_job, analyze_video_job, router as analyze_router
from app.routes.contents import router as contents_router
from app.services.actionable_recommendations import build_actionable_recommendations
from app.services.jobs import _jobs, get_status
from app.services.persistence import save_video_analysis_result
from app.services.recommendation_evidence import fingerprint
from app.services.revision_comparisons import (
    build_revision_comparison,
    create_revision_job,
    claim_revision_job,
    mark_inprocess_jobs_interrupted,
)
from tests.test_actionable_recommendations import fixture_result


class RevisionComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            f"sqlite:///{Path(self.temp.name) / 'revision.db'}",
            connect_args={"check_same_thread": False},
        )
        @event.listens_for(self.engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.file = Path(self.temp.name) / "revision.mp4"
        self.file.write_bytes(b"revision-one")
        with self.sessions() as db:
            owner = User(username="revision-owner", email="revision@example.test",
                         password_hash="test", role="user")
            other = User(username="revision-other", email="other-revision@example.test",
                         password_hash="test", role="user")
            db.add_all([owner, other])
            db.commit()
            self.owner_id, self.other_id = owner.user_id, other.user_id
            self.parent_recommendation = fixture_result()
            self.parent_recommendation["classification"] = {"taxonomy_leaf_key": "phone", "is_unknown": False}
            self.parent_recommendation["actionable_recommendations"] = (
                build_actionable_recommendations(self.parent_recommendation)
            )
            parent_input = self.parent_recommendation["evidence_bundle"]["input"]
            parent_raw = parent_input["raw_transcript"]
            parent_cleaned = parent_input["cleaned_transcript"]
            saved = save_video_analysis_result(
                db,
                user=owner,
                filename="original.mp4",
                file_path="original.mp4",
                transcript=parent_cleaned,
                raw_transcript=parent_raw,
                cleaned_transcript=parent_cleaned,
                analysis_payload={},
                nlp_result={},
                recommendation_payload=self.parent_recommendation,
            )
            self.content_id = saved["content_id"]
            self.analysis_id = saved["analysis_id"]
            self.digest = fingerprint(self.parent_recommendation)
            advice = self.parent_recommendation["actionable_recommendations"]["items"][0]
            self.advice_id = advice["id"]
            db.add(ClipRevisionPlan(
                analysis_id=self.analysis_id,
                recommendation_fingerprint=self.digest,
                selected_advice_ids=json.dumps([self.advice_id]),
                notes="เพิ่มการทดสอบ",
                revision=1,
            ))
            db.commit()
        self.actor = self.owner_id
        self.app = FastAPI()
        self.app.include_router(contents_router)
        self.app.include_router(analyze_router)
        def database():
            with self.sessions() as db:
                yield db
        self.app.dependency_overrides[get_db] = database
        self.app.dependency_overrides[get_current_user] = self.current_user
        self.client = TestClient(self.app)

    def current_user(self):
        with self.sessions() as db:
            row = db.get(User, self.actor)
            return SimpleNamespace(user_id=row.user_id, role=row.role, is_active=row.is_active)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        self.temp.cleanup()

    def fields(self, request_id="revision-request-0001", revision=1):
        return {
            "parent_content_id": str(self.content_id),
            "parent_analysis_id": str(self.analysis_id),
            "parent_recommendation_fingerprint": self.digest,
            "expected_plan_revision": str(revision),
            "client_request_id": request_id,
        }

    def settings(self, model="small"):
        return {
            "upload_max_duration_seconds": 300,
            "hook_duration_seconds": 60,
            "asr_model": model,
            "classification_model": {"model_id": 1},
            "captured_at": "2026-09-29T12:00:00+00:00",
        }

    def post(self, **kwargs):
        path = kwargs.pop("path", self.file)
        if not path.exists():
            path.write_bytes(b"revision-one")
        with patch("app.routes.analyze._save_validated_upload", return_value=str(path)), \
                patch("app.routes.analyze._capture_upload_settings", return_value=self.settings()), \
                patch("app.routes.analyze.enqueue") as enqueue:
            enqueue.side_effect = lambda *args, **call: call["_job_id"]
            return self.client.post(
                "/analyze/revision",
                data=self.fields(**kwargs),
                files={"file": ("revision.mp4", b"ignored", "video/mp4")},
            )

    def test_accepts_saved_plan_and_idempotent_request(self):
        first = self.post()
        self.assertEqual(first.status_code, 200, first.text)
        duplicate_file = Path(self.temp.name) / "duplicate.mp4"
        duplicate_file.write_bytes(b"revision-one")
        second = self.post(path=duplicate_file)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(first.json()["job_id"], second.json()["job_id"])
        self.assertFalse(duplicate_file.exists())
        with self.sessions() as db:
            self.assertEqual(db.query(ClipRevisionComparison).count(), 1)
            row = db.query(ClipRevisionComparison).one()
            snapshot = json.loads(row.plan_snapshot_json)
            self.assertEqual(snapshot["plan_revision"], 1)
            self.assertEqual(snapshot["selected_advice_ids"], [self.advice_id])
            self.assertTrue(snapshot["topics"])

    def test_same_request_with_other_file_conflicts(self):
        self.post()
        other = Path(self.temp.name) / "other.mp4"
        other.write_bytes(b"different-file")
        response = self.post(path=other)
        self.assertEqual(response.status_code, 409)
        self.assertFalse(other.exists())

    def test_stale_plan_and_other_user_are_rejected(self):
        self.assertEqual(self.post(revision=2).status_code, 409)
        accepted = self.post().json()
        self.actor = self.other_id
        self.assertEqual(
            self.client.get(f"/revision-jobs/{accepted['job_id']}").status_code,
            404,
        )

    def test_notes_only_plan_is_explicit(self):
        with self.sessions() as db:
            plan = db.get(ClipRevisionPlan, self.analysis_id)
            plan.selected_advice_ids = "[]"
            plan.revision = 2
            db.commit()
        response = self.post(request_id="notes-only-request", revision=2)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["revision_context"]["notes_only"])

    def test_source_transcript_change_is_rejected(self):
        with self.sessions() as db:
            content = db.get(UserContent, self.content_id)
            content.raw_transcript = "changed after plan"
            db.commit()
        self.assertEqual(self.post().status_code, 409)

    def test_worker_uses_captured_plan_after_plan_changes(self):
        with self.sessions() as db:
            row, _ = create_revision_job(
                db,
                user_id=self.owner_id,
                parent_content_id=self.content_id,
                parent_analysis_id=self.analysis_id,
                parent_fingerprint=self.digest,
                expected_plan_revision=1,
                client_request_id="worker-snapshot-request",
                file_sha256=__import__("hashlib").sha256(self.file.read_bytes()).hexdigest(),
                file_path=str(self.file),
                filename="revision.mp4",
                settings_snapshot=self.settings(),
            )
            comparison_id = row.comparison_id
            plan = db.get(ClipRevisionPlan, self.analysis_id)
            plan.selected_advice_ids = "[]"
            plan.revision = 2
            db.commit()
        child_recommendation = copy.deepcopy(self.parent_recommendation)
        child_recommendation["evidence_bundle"]["input"].update({
            "raw_transcript": "รีวิวมือถือ ทดสอบความเร็วในการชาร์จด้วยอุปกรณ์จริง",
            "cleaned_transcript": "รีวิวมือถือ ทดสอบความเร็วในการชาร์จด้วยอุปกรณ์จริง",
            "availability": "available",
            "scope": "full_clip",
            "segments": [],
            "analysis_settings": self.settings(),
        })
        pipeline_result = {
            "transcript": "รีวิวมือถือ ทดสอบความเร็วในการชาร์จด้วยอุปกรณ์จริง",
            "raw_transcript": "รีวิวมือถือ ทดสอบความเร็วในการชาร์จด้วยอุปกรณ์จริง",
            "cleaned_transcript": "รีวิวมือถือ ทดสอบความเร็วในการชาร์จด้วยอุปกรณ์จริง",
            "analysis": {"title": "ฉบับแก้ไข"},
        }
        with patch("app.routes.analyze.SessionLocal", self.sessions), \
                patch("app.routes.analyze.pipeline_analyze", return_value=pipeline_result) as pipeline, \
                patch("app.routes.analyze._build_recommendation",
                      return_value=(child_recommendation, {})):
            result = analyze_revision_video_job(comparison_id)
            duplicate = analyze_revision_video_job(comparison_id)
            self.assertEqual(duplicate["content_id"], result["content_id"])
        self.assertEqual(pipeline.call_count, 1)
        self.assertTrue(result["saved"])
        with self.sessions() as db:
            row = db.get(ClipRevisionComparison, comparison_id)
            frozen = json.loads(row.comparison_result_json)
            self.assertEqual(frozen["plan"]["revision"], 1)
            self.assertEqual(len(frozen["topics"]), 1)
            self.assertEqual(db.query(UserContent).count(), 2)

    def test_restart_marks_only_inprocess_unfinished_jobs(self):
        self.post(request_id="restart-inprocess")
        self.post(request_id="restart-rq")
        with self.sessions() as db:
            rows = db.query(ClipRevisionComparison).order_by(ClipRevisionComparison.comparison_id).all()
            rows[0].status = "running"
            settings = json.loads(rows[0].settings_snapshot_json)
            settings["revision_process_owner"]["started_at"] = -1
            rows[0].settings_snapshot_json = json.dumps(settings)
            rows[1].status = "running"
            rows[1].job_backend = "rq"
            db.commit()
            self.assertEqual(mark_inprocess_jobs_interrupted(db), 1)
            self.assertEqual(rows[0].status, "interrupted")
            self.assertEqual(rows[1].status, "running")

    def test_live_process_is_not_interrupted_by_another_backend_start(self):
        self.post(request_id="live-process-check")
        with self.sessions() as db:
            self.assertEqual(mark_inprocess_jobs_interrupted(db), 0)
            self.assertEqual(db.query(ClipRevisionComparison).one().status, "queued")

    def test_claim_is_atomic_and_stale_attempt_cannot_run(self):
        job = self.post(request_id="claim-once-check").json()
        with self.sessions() as db:
            row = db.query(ClipRevisionComparison).one()
            with self.assertRaises(RuntimeError):
                claim_revision_job(db, row.comparison_id, expected_job_id="stale-attempt")
            claim_revision_job(db, row.comparison_id, expected_job_id=job["job_id"])
            with self.assertRaises(RuntimeError):
                claim_revision_job(db, row.comparison_id, expected_job_id=job["job_id"])
            self.assertEqual(db.get(ClipRevisionComparison, row.comparison_id).status, "running")

    def test_ordinary_analysis_does_not_require_revision_id(self):
        with patch("app.routes.analyze.SessionLocal", self.sessions), \
                patch("app.routes.analyze.pipeline_analyze", return_value={"transcript": "phone"}) as pipeline, \
                patch("app.routes.analyze._build_recommendation", return_value=({"domain": "phone"}, {})):
            result = analyze_video_job(str(self.file), "original.mp4", self.owner_id, settings_snapshot=self.settings())
        self.assertEqual(result["recommendation"]["domain"], "phone")
        self.assertEqual(pipeline.call_count, 1)

    def test_changed_plan_snapshot_stops_before_asr(self):
        self.post(request_id="corrupted-snapshot-check")
        with self.sessions() as db:
            row = db.query(ClipRevisionComparison).one()
            snapshot = json.loads(row.plan_snapshot_json)
            snapshot["topics"] = []
            row.plan_snapshot_json = json.dumps(snapshot)
            comparison_id = row.comparison_id
            db.commit()
        with patch("app.routes.analyze.SessionLocal", self.sessions), patch("app.routes.analyze.pipeline_analyze") as pipeline:
            with self.assertRaises(RuntimeError):
                analyze_revision_video_job(comparison_id)
            pipeline.assert_not_called()

    def test_interrupted_job_retries_with_new_job_id(self):
        accepted = self.post(request_id="retry-request").json()
        old_job_id = accepted["job_id"]
        with self.sessions() as db:
            row = db.query(ClipRevisionComparison).filter_by(job_id=old_job_id).one()
            row.status = "interrupted"
            row.stage = "interrupted"
            db.commit()
        with patch("app.routes.analyze.enqueue") as enqueue:
            enqueue.side_effect = lambda *args, **call: call["_job_id"]
            response = self.client.post(f"/revision-jobs/{old_job_id}/retry")
        self.assertEqual(response.status_code, 200, response.text)
        new_job_id = response.json()["job_id"]
        self.assertNotEqual(old_job_id, new_job_id)
        self.assertEqual(response.json()["status"], "queued")
        self.assertEqual(self.client.get(f"/revision-jobs/{old_job_id}").status_code, 404)
        self.assertEqual(self.client.get(f"/revision-jobs/{new_job_id}").status_code, 200)

    def test_generic_inprocess_job_status_hides_other_owner(self):
        _jobs["owned-test-job"] = {"status": "queued", "owner_user_id": self.owner_id}
        try:
            self.assertEqual(get_status("owned-test-job", requester_user_id=self.other_id)["status"], "not_found")
            self.assertEqual(get_status("owned-test-job", requester_user_id=self.owner_id)["status"], "queued")
        finally:
            _jobs.pop("owned-test-job", None)

    def test_parent_delete_removes_link_but_not_completed_child(self):
        self.test_worker_uses_captured_plan_after_plan_changes()
        with self.sessions() as db:
            row = db.query(ClipRevisionComparison).one()
            child_id = row.child_content_id
            db.delete(db.get(UserContent, self.content_id))
            db.commit()
            self.assertIsNotNone(db.get(UserContent, child_id))
            self.assertEqual(db.query(ClipRevisionComparison).count(), 0)

    def test_worker_failure_rolls_back_child_and_marks_job_failed(self):
        with self.sessions() as db:
            row, _ = create_revision_job(
                db,
                user_id=self.owner_id,
                parent_content_id=self.content_id,
                parent_analysis_id=self.analysis_id,
                parent_fingerprint=self.digest,
                expected_plan_revision=1,
                client_request_id="rollback-request",
                file_sha256=__import__("hashlib").sha256(self.file.read_bytes()).hexdigest(),
                file_path=str(self.file),
                filename="revision.mp4",
                settings_snapshot=self.settings(),
            )
            comparison_id = row.comparison_id
        result = {
            "transcript": "ทดสอบฉบับใหม่",
            "raw_transcript": "ทดสอบฉบับใหม่",
            "cleaned_transcript": "ทดสอบฉบับใหม่",
            "analysis": {"title": "ฉบับใหม่"},
        }
        child_recommendation = copy.deepcopy(self.parent_recommendation)
        child_recommendation["evidence_bundle"]["input"] = {
            "raw_transcript": "ทดสอบฉบับใหม่",
            "cleaned_transcript": "ทดสอบฉบับใหม่",
            "availability": "available",
            "scope": "full_clip",
            "segments": [],
            "analysis_settings": self.settings(),
        }
        def fail_after_child_added(db, **_kwargs):
            db.add(UserContent(user_id=self.owner_id, title="must rollback"))
            db.flush()
            raise ValueError("database write failed")
        with patch("app.routes.analyze.SessionLocal", self.sessions), \
                patch("app.routes.analyze.pipeline_analyze", return_value=result), \
                patch("app.routes.analyze._build_recommendation",
                      return_value=(child_recommendation, {})), \
                patch("app.routes.analyze.save_video_analysis_result",
                      side_effect=fail_after_child_added):
            with self.assertRaisesRegex(RuntimeError, "ประมวลผลฉบับแก้ไขไม่สำเร็จ"):
                analyze_revision_video_job(comparison_id)
        with self.sessions() as db:
            row = db.get(ClipRevisionComparison, comparison_id)
            self.assertEqual(row.status, "failed")
            self.assertIsNone(row.child_content_id)
            self.assertEqual(db.query(UserContent).count(), 1)

    def test_suspended_owner_stops_before_pipeline_and_creates_no_child(self):
        with self.sessions() as db:
            row, _ = create_revision_job(
                db,
                user_id=self.owner_id,
                parent_content_id=self.content_id,
                parent_analysis_id=self.analysis_id,
                parent_fingerprint=self.digest,
                expected_plan_revision=1,
                client_request_id="suspended-owner-request",
                file_sha256=__import__("hashlib").sha256(self.file.read_bytes()).hexdigest(),
                file_path=str(self.file),
                filename="revision.mp4",
                settings_snapshot=self.settings(),
            )
            comparison_id = row.comparison_id
            db.get(User, self.owner_id).is_active = False
            db.commit()

        with patch("app.routes.analyze.SessionLocal", self.sessions), \
                patch("app.routes.analyze.pipeline_analyze") as pipeline:
            with self.assertRaises(RuntimeError):
                analyze_revision_video_job(comparison_id)

        pipeline.assert_not_called()
        with self.sessions() as db:
            row = db.get(ClipRevisionComparison, comparison_id)
            self.assertEqual(row.status, "failed")
            self.assertIsNone(row.child_content_id)
            self.assertEqual(db.query(UserContent).count(), 1)


class RevisionComparisonMatrixTests(unittest.TestCase):
    def context(self, text, *, availability="available", model="small", segments=None):
        return {
            "raw_transcript": text,
            "cleaned_transcript": text,
            "availability": availability,
            "scope": "full_clip" if availability == "available" else "partial_clip",
            "reason": None if availability == "available" else "incomplete_or_weak_audio",
            "segments": segments or [],
            "analysis_settings": {"asr_model": model},
        }

    def compare(self, before, after, *, before_availability="available",
                after_availability="available", parent_model="small",
                child_model="small", child_domain="phone", child_unknown=False):
        topic = {
            "advice_id": "a1",
            "evidence_topic_id": "t1",
            "canonical_topic": "battery life",
            "title": "แบตเตอรี่",
            "aliases": ["battery life", "แบตเตอรี่", "แบต"],
            "context_terms": ["ใช้งานทั้งวัน", "เล่นเกม", "ทดสอบ"],
        }
        plan = {
            "parent_content_id": 1,
            "parent_analysis_id": 2,
            "parent_title": "ก่อนปรับ",
            "parent_created_at": "2026-09-29T10:00:00Z",
            "parent_category_accepted": True,
            "parent_domain": "phone",
            "parent_context": self.context(before, availability=before_availability,
                                             model=parent_model),
            "parent_analysis_settings": {"asr_model": parent_model},
            "parent_input_hashes": {},
            "plan_revision": 3,
            "selected_advice_ids": ["a1"],
            "topics": [topic],
        }
        child = {
            "domain": child_domain,
            "classification": {
                "taxonomy_leaf_key": child_domain,
                "is_unknown": child_unknown,
                "acceptance": {"accepted": not child_unknown},
            },
            "evidence_bundle": {
                "input": self.context(after, availability=after_availability,
                                        model=child_model)
            },
        }
        return build_revision_comparison(plan, child)

    def test_all_status_pairs_and_unassessable(self):
        cases = [
            ("รีวิวมือถือ", "ทดสอบแบตเตอรี่เล่นเกม", "ตรวจพบการกล่าวถึงในฉบับใหม่"),
            ("แบตเตอรี่ใช้งานทั้งวัน", "ทดสอบแบตเตอรี่เล่นเกม", "ตรวจพบในทั้งสองฉบับ"),
            ("แบตเตอรี่ใช้งานทั้งวัน", "รีวิวมือถือ", "ยังไม่ตรวจพบในข้อความฉบับใหม่"),
            ("รีวิวมือถือ", "รีวิวโทรศัพท์", "ยังไม่ตรวจพบในข้อความทั้งสองฉบับ"),
        ]
        for before, after, message in cases:
            with self.subTest(message=message):
                result = self.compare(before, after)
                self.assertEqual(result["topics"][0]["message"], message)
                self.assertFalse(result["topics"][0]["automatic_completion"])
        unavailable = self.compare("แบตเตอรี่", "แบตเตอรี่",
                                   after_availability="partial")
        self.assertEqual(unavailable["topics"][0]["after"]["status"], "unassessable")
        self.assertEqual(unavailable["topics"][0]["message"], "ข้อมูลยังไม่พอเปรียบเทียบ")

    def test_context_keyword_only_negative_and_real_timestamps(self):
        keyword_only = self.compare("รีวิวมือถือ", "พูดคำว่าแบตเตอรี่เท่านั้น")
        self.assertEqual(keyword_only["topics"][0]["after"]["context"]["status"], "keyword_only")
        negative = self.compare("รีวิวมือถือ", "ไม่มีแบตเตอรี่ที่ใช้งานทั้งวัน")
        self.assertEqual(negative["topics"][0]["after"]["status"], "detected")
        self.assertNotIn("มีฟังก์ชัน", json.dumps(negative, ensure_ascii=False))

    def test_asr_change_and_category_mismatch_are_visible(self):
        changed = self.compare("รีวิวมือถือ", "ทดสอบแบตเตอรี่",
                               parent_model="small", child_model="base")
        self.assertTrue(changed["compatibility"]["asr_method_changed"])
        self.assertTrue(any("asr_method_changed" in item for item in changed["limitations"]))
        mismatch = self.compare("แบตเตอรี่", "กล้อง", child_domain="camera")
        self.assertEqual(mismatch["status"], "withheld_category")
        self.assertEqual(mismatch["topics"][0]["before"]["status"], "unassessable")

    def test_method_mismatch_and_each_file_timestamp_are_explicit(self):
        missing = self.compare("รีวิวมือถือ", "ทดสอบแบตเตอรี่")
        plan = {
            "parent_content_id": 1,
            "parent_analysis_id": 2,
            "parent_domain": "phone",
            "parent_category_accepted": True,
            "topics": missing["topics"],
        }
        child = {
            "domain": "phone",
            "classification": {"taxonomy_leaf_key": "phone", "is_unknown": False},
            "evidence_bundle": {"input": self.context("battery gaming")},
        }
        self.assertEqual(build_revision_comparison(plan, child)["status"], "method_mismatch")

        topic = {
            "advice_id": "a1", "evidence_topic_id": "t1",
            "canonical_topic": "battery", "title": "Battery",
            "aliases": ["battery"], "context_terms": ["gaming"],
        }
        before = self.context("battery gaming", segments=[
            {"start": 5.0, "end": 9.0, "text": "battery gaming"}
        ])
        after = self.context("battery gaming", segments=[
            {"start": 70.0, "end": 76.0, "text": "battery gaming"}
        ])
        timed_plan = {
            "parent_content_id": 1, "parent_analysis_id": 2,
            "parent_title": "before", "parent_category_accepted": True,
            "parent_domain": "phone", "parent_context": before,
            "parent_analysis_settings": {"asr_model": "small"},
            "parent_input_hashes": {}, "plan_revision": 1,
            "selected_advice_ids": ["a1"], "topics": [topic],
        }
        timed_child = {
            "domain": "phone",
            "classification": {"taxonomy_leaf_key": "phone", "is_unknown": False},
            "evidence_bundle": {"input": after},
        }
        item = build_revision_comparison(timed_plan, timed_child)["topics"][0]
        self.assertEqual(item["before"]["occurrences"][0]["timestamp"]["start_seconds"], 5.0)
        self.assertEqual(item["after"]["occurrences"][0]["timestamp"]["start_seconds"], 70.0)


if __name__ == "__main__":
    unittest.main()
