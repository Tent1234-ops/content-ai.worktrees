import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_current_user
from app.database.db import Base, get_db
from app.database.models import (
    ClassificationModel,
    OutcomeModel,
    OutcomeTrainingRun,
    User,
)
from app.routes.outcome_model_management import router
from app.services import outcome_model_management as service


READY = {
    "ready": True, "reason_codes": [],
    "manifest_sha256": "a" * 64, "protocol_sha256": "b" * 64,
    "counts": {}, "rights": {"allowed": True}, "split_hashes": {},
    "independent_test_opened": False, "production_eligible": False,
}


def _metric(value=0.2):
    return {
        "status": "evaluated", "sample_count": 30,
        "positive_count": 15, "negative_count": 15,
        "brier_score": value, "log_loss": value + 0.2,
        "roc_auc": 0.8, "pr_auc": 0.8,
    }


def _evaluation(value=0.2):
    return {
        "overall": {"channel_balanced": _metric(value), "video_weighted": _metric(value)},
        "by_scope": {
            "accepted_category": {}, "confirmed_format": {}, "frozen_age_context": {},
        },
        "calibration": {"status": "evaluated", "passed": True, "bins": []},
    }


def fake_report(tmp: Path):
    artifact = tmp / "model.joblib"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"fixture")
    return {
        "artifact_created": True,
        "artifact_path": str(artifact), "artifact_sha256": "c" * 64,
        "target_version": "reference_relative_views_v1",
        "protocol_sha256": "b" * 64,
        "feature_schema_sha256": "d" * 64,
        "manifest_sha256": "a" * 64,
        "split_hashes": {"fit": "1", "tuning": "2", "calibration": "3", "independent_test": "4"},
        "partition_counts": {
            "fit": {"videos": 60}, "tuning": {"videos": 30},
            "calibration": {"videos": 36}, "independent_test": {"videos": 30},
        },
        "tuning_metrics": {
            "metadata_topics_logistic_regression": {
                "before": _evaluation(0.1), "after": _evaluation(0.09),
            }
        },
        "calibration_metrics": {
            "metadata_topics_logistic_regression": {
                "before": _evaluation(0.1), "after": _evaluation(0.08),
            }
        },
        "paired_channel_bootstrap": {"status": "evaluated"},
        "qualification": {"status": "validation_passed", "qualified": False},
        "library_versions": {"python": "test"},
    }


class OutcomeModelManagementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.tmp.name)
        self.engine = create_engine(
            f"sqlite:///{self.temp_path / 'outcome.db'}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.db = self.sessions()
        self.admin = User(
            username="outcome-admin", email="outcome@example.test",
            password_hash="unused", role="admin",
        )
        self.db.add(self.admin)
        self.db.commit()
        self.patchers = [
            patch.object(service, "ARTIFACT_ROOT", self.temp_path / "artifacts"),
            patch.object(service, "outcome_preflight", return_value=dict(READY)),
            patch.object(service, "launch_training_worker"),
        ]
        for item in self.patchers:
            item.start()

    def tearDown(self):
        for item in reversed(self.patchers):
            item.stop()
        self.db.close()
        self.engine.dispose()
        self.tmp.cleanup()

    def start(self):
        return service.start_training_run(
            self.db, user_id=self.admin.user_id, manifest_sha256="a" * 64
        )

    def test_single_slot_concurrency_and_stale_recovery(self):
        first = self.start()
        self.assertEqual(first["status"], "queued")
        with self.assertRaises(service.OutcomeTrainingConflict):
            self.start()
        with self.sessions() as other:
            other.add(OutcomeTrainingRun(
                run_id="duplicate", requested_by=self.admin.user_id,
                active_slot=1, manifest_sha256="a" * 64,
                protocol_sha256="b" * 64, parameters_json="{}",
            ))
            with self.assertRaises(IntegrityError):
                other.commit()
        row = self.db.get(OutcomeTrainingRun, first["run_id"])
        row.updated_at = datetime.utcnow() - timedelta(seconds=service.STALE_SECONDS + 1)
        self.db.commit()
        recovered = service.get_training_run(self.db, row.run_id)
        self.assertEqual(recovered["status"], "interrupted")
        self.assertIsNone(self.db.get(OutcomeTrainingRun, row.run_id).active_slot)

    def test_failed_launch_releases_slot(self):
        service.launch_training_worker.side_effect = OSError("cannot launch")
        result = self.start()
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(self.db.get(OutcomeTrainingRun, result["run_id"]).active_slot)

    def test_worker_persists_separate_candidate_without_touching_classifier(self):
        classifier = ClassificationModel(
            model_key="classifier", model_version="active-v1", taxonomy_version="v1",
            model_type="test", status="qualified", is_active=True,
        )
        self.db.add(classifier)
        self.db.commit()
        started = self.start()
        report = fake_report(self.temp_path / "worker-artifact")
        with patch.object(service, "_find_manifest", return_value=(Path("manifest"), Path("features"))), \
             patch.object(service, "train_and_validate_outcome_model", return_value=report):
            service.execute_training_run(started["run_id"], session_factory=self.sessions)
        self.db.expire_all()
        result = service.get_training_run(self.db, started["run_id"])
        self.assertEqual(result["status"], "completed", result["error"])
        model = self.db.query(OutcomeModel).one()
        self.assertEqual(model.status, "validation_passed")
        self.assertFalse(model.is_active)
        self.assertFalse(model.independent_test_passed)
        self.assertFalse(model.production_eligible)
        self.assertTrue(self.db.get(ClassificationModel, classifier.model_id).is_active)
        detail = service.model_detail(self.db, model.model_id)
        self.assertFalse(detail["can_activate"])
        self.assertFalse(detail["force_override_supported"])

    def test_worker_failure_is_durable_and_classifier_stays_active(self):
        classifier = ClassificationModel(
            model_key="classifier", model_version="active-v1", taxonomy_version="v1",
            model_type="test", status="qualified", is_active=True,
        )
        self.db.add(classifier)
        self.db.commit()
        started = self.start()
        with patch.object(service, "_find_manifest", return_value=(Path("manifest"), Path("features"))), \
             patch.object(service, "train_and_validate_outcome_model", side_effect=RuntimeError("fit failed")):
            service.execute_training_run(started["run_id"], session_factory=self.sessions)
        result = service.get_training_run(self.db, started["run_id"])
        self.assertEqual(result["status"], "failed")
        self.assertIn("fit failed", result["error"])
        self.assertEqual(self.db.query(OutcomeModel).count(), 0)
        self.assertTrue(self.db.get(ClassificationModel, classifier.model_id).is_active)

    def test_admin_authorization_validation_and_no_activation_route(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        with TestClient(app) as client:
            paths = [
                ("GET", "/admin/outcome-training/preflight"),
                ("GET", "/admin/outcome-training/runs"),
                ("POST", "/admin/outcome-training/runs"),
                ("GET", "/admin/outcome-training/models"),
            ]
            for method, path in paths:
                self.assertEqual(client.request(method, path).status_code, 401)
            self.admin.role = "user"
            app.dependency_overrides[get_current_user] = lambda: self.admin
            for method, path in paths:
                self.assertEqual(client.request(method, path).status_code, 403)
            self.admin.role = "admin"
            self.assertEqual(client.get("/admin/outcome-training/preflight").status_code, 200)
            injected = client.post("/admin/outcome-training/runs", json={
                "manifest_sha256": "a" * 64,
                "force": True,
                "artifact_path": "C:/untrusted/model.joblib",
            })
            self.assertEqual(injected.status_code, 422)
            self.assertIn(
                client.post("/admin/outcome-training/models/1/activate", json={"force": True}).status_code,
                {404, 405},
            )


if __name__ == "__main__":
    unittest.main()
