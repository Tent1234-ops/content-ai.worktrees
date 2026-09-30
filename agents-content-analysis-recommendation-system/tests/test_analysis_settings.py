import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_current_user
from app.database.db import Base, get_db
from app.database.migrations import migrate_analysis_settings_schema
from app.database.models import AnalysisResult, ClassificationModel, SystemLog, User
from app.routes import admin, analyze
from app.schemas.admin_config import AdminConfigUpdate
from app.schemas.analysis_settings import AnalysisParameters
from app.services.admin_settings import (
    apply_config_from_backup, reset_admin_config, save_admin_config,
)
from app.services.analysis_settings import (
    capture_analysis_settings, get_analysis_settings, save_analysis_settings,
)
from app.services.classification import _classify_with_active_model
from app.services.classification_training import ClassificationTrainingError
from app.services.contents import get_user_content_detail
from app.services.media_validation import MediaValidationError, validate_user_upload_duration


class AnalysisSettingsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.url = f"sqlite:///{Path(self.directory.name) / 'settings.db'}"
        self.engine = create_engine(self.url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.sessions()
        self.user = User(username="settings-admin", email="settings@example.test", password_hash="unused", role="admin")
        self.db.add(self.user)
        self.db.commit()
        self.ready = patch("app.services.analysis_settings.check_model_readiness", return_value={"ready": True}).start()
        self.load = patch("app.services.analysis_settings.ModelManager.get_model").start()
        self.addCleanup(patch.stopall)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.directory.cleanup()

    def save(self, **kwargs):
        return save_analysis_settings(self.db, AnalysisParameters(**kwargs), user_id=self.user.user_id)

    def test_settings_persist_after_dispose_and_reopen(self):
        self.save(upload_max_duration_seconds=180, asr_model="base", hook_duration_seconds=30)
        self.db.close()
        self.engine.dispose()
        engine = create_engine(self.url)
        try:
            with sessionmaker(bind=engine)() as reopened:
                saved = get_analysis_settings(reopened)
                self.assertEqual(saved["upload_max_duration_seconds"], 180)
                self.assertEqual(saved["asr_model"], "base")
                self.assertEqual(saved["hook_duration_seconds"], 30)
                audit = reopened.query(SystemLog).filter_by(action="admin_analysis_settings_update").one()
                self.assertEqual(json.loads(audit.detail)["before"]["hook_duration_seconds"], 60)
                self.assertEqual(audit.user_id, self.user.user_id)
        finally:
            engine.dispose()

    def test_missing_or_corrupt_whisper_never_changes_saved_values(self):
        before = get_analysis_settings(self.db)
        self.ready.return_value = {"ready": False}
        with self.assertRaisesRegex(ValueError, "not installed"):
            self.save(asr_model="medium")
        self.load.assert_not_called()
        self.ready.return_value = {"ready": True}
        self.load.side_effect = RuntimeError("corrupt local model")
        with self.assertRaisesRegex(ValueError, "not saved"):
            self.save(asr_model="base")
        self.assertEqual(get_analysis_settings(self.db), before)

    def test_parameters_reject_invalid_limits_and_unassessed_model_changes(self):
        for values in [
            {"upload_max_duration_seconds": 29}, {"upload_max_duration_seconds": 1801},
            {"upload_max_duration_seconds": 300.5}, {"hook_duration_seconds": 4},
            {"hook_duration_seconds": 301}, {"upload_max_duration_seconds": 30, "hook_duration_seconds": 60},
            {"asr_model": "small.en"}, {"asr_model": "../../model"},
            {"unknown_threshold": 0.1}, {"classification_model_id": 99},
        ]:
            with self.subTest(values=values), self.assertRaises(ValidationError):
                AnalysisParameters(**values)

    def test_legacy_settings_cannot_break_analysis_constraints(self):
        self.save(upload_max_duration_seconds=30, hook_duration_seconds=10)
        with self.assertRaises(ValidationError):
            save_admin_config(self.db, AdminConfigUpdate(hook_analysis_duration=60))
        with self.assertRaises(ValidationError):
            apply_config_from_backup(self.db, {"configuration": {"hook_duration": 60}})
        self.assertEqual(get_analysis_settings(self.db)["hook_duration_seconds"], 10)
        reset_admin_config(self.db)
        self.assertEqual(get_analysis_settings(self.db)["hook_duration_seconds"], 30)

    def test_model_details_use_artifact_threshold_and_no_active_is_explicit(self):
        self.assertIsNone(get_analysis_settings(self.db, admin=True)["classification_model"]["model_id"])
        model = self.add_model()
        with patch("app.services.analysis_settings.load_classification_artifact", return_value={
            "model_key": model.model_key, "model_version": model.model_version, "unknown_threshold": 0.72,
        }), patch("app.services.analysis_settings.classification_artifact_sha256", return_value="abc"):
            snapshot = capture_analysis_settings(self.db)
        self.assertEqual(snapshot["classification_model"]["unknown_threshold"], 0.72)
        self.assertEqual(snapshot["classification_model"]["artifact_sha256"], "abc")
        with patch("app.services.analysis_settings.load_classification_artifact", side_effect=EOFError("bad artifact")):
            self.assertEqual(get_analysis_settings(self.db, admin=True)["classification_model"]["status"], "artifact_unavailable")
            with self.assertRaisesRegex(ValueError, "artifact is unavailable"):
                capture_analysis_settings(self.db)

    def add_model(self):
        model = ClassificationModel(model_key="test", model_version="v1", model_type="tfidf", taxonomy_version="v1", status="qualified", is_active=True, artifact_path="unused.joblib")
        self.db.add(model)
        self.db.commit()
        return model

    def test_queued_model_can_be_inactive_but_artifact_cannot_change(self):
        model = self.add_model()
        snapshot = {"model_id": model.model_id, "artifact_sha256": "abc"}
        model.is_active = False
        self.db.commit()
        prediction = {"taxonomy_leaf_key": "phone", "raw_taxonomy_leaf_key": "phone", "confidence": 0.9, "probabilities": {"phone": 0.9}, "unknown_threshold": 0.72}
        with patch("app.services.classification.classification_artifact_sha256", return_value="abc"), patch(
            "app.services.classification.classify_with_artifact", return_value=prediction
        ) as predict, patch("app.services.classification.ready_leaf_keys", return_value={"phone"}):
            result = _classify_with_active_model(self.db, text="camera battery phone", title=None, model_snapshot=snapshot)
            self.assertEqual(result["model_id"], model.model_id)
            self.assertEqual(result["unknown_threshold"], 0.72)
            predict.assert_called_once()
        with patch("app.services.classification.classification_artifact_sha256", return_value="changed"):
            with self.assertRaisesRegex(ClassificationTrainingError, "changed"):
                _classify_with_active_model(self.db, text="phone", title=None, model_snapshot=snapshot)

    def test_saved_job_uses_queued_settings_and_history_keeps_them(self):
        self.save(upload_max_duration_seconds=180, hook_duration_seconds=30, asr_model="base")
        snapshot = capture_analysis_settings(self.db)
        self.save(upload_max_duration_seconds=600, hook_duration_seconds=120, asr_model="small")
        with patch("app.routes.analyze.SessionLocal", self.sessions), patch(
            "app.routes.analyze.pipeline_analyze", return_value={"transcript": "phone camera battery", "analysis": {}}
        ) as pipeline, patch("app.routes.analyze._build_recommendation", return_value=({"domain": "phone"}, {"top_keywords": []})) as recommend:
            result = analyze.analyze_and_save_video_job("clip.mp4", "1.mp4", self.user.user_id, settings_snapshot=snapshot)
        pipeline.assert_called_once_with("clip.mp4", display_name="1.mp4", hook_duration_seconds=30, asr_model_size="base")
        self.assertEqual(recommend.call_args.kwargs["settings_snapshot"], snapshot)
        self.assertEqual(result["analysis_settings"], snapshot)
        self.db.expire_all()
        history = get_user_content_detail(self.db, user_id=self.user.user_id, content_id=result["content_id"])
        self.assertEqual(history["analysis"]["analysis_settings"], snapshot)
        row = self.db.query(AnalysisResult).one()
        self.assertIsNone(row.classification_model_id)

    def test_backend_duration_uses_selected_limit_not_old_five_minutes(self):
        with patch("app.services.media_validation.probe_media_duration_seconds", return_value=200):
            with self.assertRaises(MediaValidationError):
                validate_user_upload_duration("clip.mp4", max_duration_seconds=180)
            self.assertEqual(validate_user_upload_duration("clip.mp4", max_duration_seconds=600), 200)

    def client(self, *, role="admin"):
        app = FastAPI()
        app.include_router(admin.router)
        app.include_router(analyze.router)
        app.dependency_overrides[get_db] = lambda: self.db
        if role is not None:
            self.user.role = role
            app.dependency_overrides[get_current_user] = lambda: self.user
        return TestClient(app)

    def test_api_permissions_and_ready_model_validation(self):
        for role, expected in [(None, 401), ("user", 403), ("admin", 200)]:
            with self.subTest(role=role), self.client(role=role) as client:
                self.assertEqual(client.get("/admin/analysis-settings").status_code, expected)
                self.assertEqual(client.put("/admin/analysis-settings", json=AnalysisParameters().model_dump()).status_code, expected)
                self.assertEqual(client.get("/analyze/settings").status_code, 401 if role is None else 200)
        with self.client() as client:
            self.ready.return_value = {"ready": False}
            self.assertEqual(client.put("/admin/analysis-settings", json=AnalysisParameters().model_dump()).status_code, 422)

    def test_upload_freezes_settings_before_queue_and_rejects_unready(self):
        self.save(upload_max_duration_seconds=120, hook_duration_seconds=20)
        with self.client(role="user") as client, patch("app.routes.analyze._save_validated_upload", return_value="clip.mp4") as validate, patch("app.routes.analyze.enqueue", return_value="queued") as queue:
            for path in ("/analyze", "/analyze/save"):
                response = client.post(path, files={"file": ("1.mp4", b"test", "video/mp4")})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(validate.call_args.kwargs["max_duration_seconds"], 120)
                self.assertEqual(queue.call_args.kwargs["settings_snapshot"]["hook_duration_seconds"], 20)
            queue.reset_mock()
            self.ready.return_value = {"ready": False}
            self.assertEqual(client.post("/analyze/save", files={"file": ("1.mp4", b"test")}).status_code, 503)
            queue.assert_not_called()


class AnalysisSettingsMigrationTests(unittest.TestCase):
    def test_existing_rows_get_default_and_migration_is_idempotent(self):
        engine = create_engine("sqlite://")
        try:
            with engine.begin() as connection:
                connection.execute(text("CREATE TABLE system_configs (config_id INT PRIMARY KEY, hook_duration INT)"))
                connection.execute(text("INSERT INTO system_configs VALUES (1, 25)"))
            self.assertEqual(migrate_analysis_settings_schema(engine)["added_columns"], ["upload_max_duration_seconds"])
            self.assertEqual(migrate_analysis_settings_schema(engine)["added_columns"], [])
            with engine.connect() as connection:
                self.assertEqual(tuple(connection.execute(text("SELECT hook_duration, upload_max_duration_seconds FROM system_configs")).one()), (25, 300))
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
