import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import joblib
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.db import Base
from app.database.models import ClassificationModel, ModelEvaluationMetric, SystemLog, User
from app.services.classification import classify_text_domain, get_active_classification_model
from app.services.classification_acceptance import (
    CONTRAST_POLICY_VERSION, acceptance_summary, apply_acceptance_policy, fit_acceptance_policy,
    is_validated_acceptance_policy,
)
from app.services.classification_presentation import PRESENTATION_WARNING, presentation_authorization
from app.services.classification_readiness import classification_model_snapshot
from app.services.classification_training import _dataset_fingerprint, classify_with_artifact
from app.services.model_management import activate_evaluated_model
from scripts import presentation_classification_model as command
from tests import test_classification_acceptance as fixtures


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.admin = User(username="admin", email="admin@example.test", password_hash="unused", role="admin")
        self.previous = ClassificationModel(model_key="old", model_version="old", model_type="test",
                                            taxonomy_version="test", status="qualified", is_active=True)
        self.db.add_all([self.admin, self.previous])
        self.db.commit()
        self.fixture = fixtures.ClassificationAcceptanceTests()
        self.fixture.setUp()
        self.policy = fit_acceptance_policy(self.fixture.estimator, self.fixture.train, self.fixture.validation,
            self.fixture.outside, labels=self.fixture.labels, confidence_threshold=0.6, policy_version=CONTRAST_POLICY_VERSION)
        self.policy.update(status="failed_validation", similarity_threshold=None, contrast_margin_threshold=None)
        for candidate in self.policy["selection_candidates"]:
            candidate["passes"] = False
        self.fixture.estimator.named_steps = {"classifier": SimpleNamespace(C=16)}
        self.source = self.root / "source"
        self.source.mkdir()
        joblib.dump({"development_only": True, "estimator": self.fixture.estimator,
                     "scope_policy": self.policy}, self.source / f"{CONTRAST_POLICY_VERSION}.joblib")
        self.rows = [*self.fixture.train, *self.fixture.validation, *self.fixture.outside]
        report = {"protocol": "laptop-scope-20261004-hybrid", "test_accessed": False,
                  "development_fingerprint": _dataset_fingerprint(self.rows),
                  "selected": {"C": 16, "grouped_cv": {"accuracy": 0.9, "f1_macro": 0.9}},
                  "policies": [{"policy": acceptance_summary(self.policy)}]}
        (self.source / "report.json").write_text(json.dumps(report), encoding="utf-8")
        self.loader = patch.object(command, "load_development_rows", return_value=(
            self.fixture.train, self.fixture.validation, self.fixture.outside))
        self.loader.start()

    def tearDown(self):
        self.loader.stop()
        self.db.close()
        self.engine.dispose()
        self.tmp.cleanup()

    def enable(self, **kwargs):
        arguments = dict(source=self.source, admin_id=self.admin.user_id, expected_active_id=self.previous.model_id,
                         hours=48, reason="User authorized a presentation with acknowledged limitations",
                         confirmed=True, output_root=self.root / "output")
        arguments.update(kwargs)
        return command.enable(self.db, **arguments)

    def test_requires_admin_confirmation_and_unchanged_active(self):
        for change in ({"confirmed": False}, {"reason": ""}, {"hours": 73}, {"expected_active_id": 999}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.enable(**change)
            self.db.rollback()
        self.admin.role = "user"
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "administrator"):
            self.enable()
        self.assertTrue(self.db.get(ClassificationModel, self.previous.model_id).is_active)

    def test_activation_preserves_failed_gate_and_can_restore(self):
        result = self.enable()
        model = get_active_classification_model(self.db)
        self.assertEqual(model.model_id, result["model_id"])
        self.assertEqual(model.status, "presentation_only")
        gate = self.db.query(ModelEvaluationMetric).filter_by(model_id=model.model_id, dataset_split="promotion_gate").one()
        self.assertEqual(gate.metric_value, 0)
        self.assertEqual(self.db.query(ModelEvaluationMetric).filter_by(model_id=model.model_id, dataset_split="test").count(), 0)
        with self.assertRaises(ValueError):
            activate_evaluated_model(self.db, model.model_id, expected_active_model_id=model.model_id, user_id=self.admin.user_id)
        self.db.rollback()
        restored = command.disable(self.db, admin_id=self.admin.user_id, expected_active_id=model.model_id)
        self.assertEqual(restored["restored_model_id"], self.previous.model_id)
        self.assertEqual(get_active_classification_model(self.db).model_id, self.previous.model_id)
        self.assertEqual(self.db.query(SystemLog).count(), 2)

    def test_presentation_is_explicit_preserves_unknown_and_has_warning(self):
        result = self.enable()
        model = self.db.get(ClassificationModel, result["model_id"])
        payload = joblib.load(result["artifact_path"])
        self.assertFalse(is_validated_acceptance_policy(payload["scope_policy"]))
        self.assertFalse(is_validated_acceptance_policy(self.policy))
        snapshot = classification_model_snapshot(model)
        self.assertEqual(snapshot["readiness"]["status"], "presentation")
        self.assertFalse(snapshot["readiness"]["scope_policy_valid"])
        self.assertTrue(snapshot["readiness"]["can_accept_predictions"])
        default = classify_with_artifact(result["artifact_path"], text=fixtures.TEXTS["phone"])
        self.assertEqual(default["taxonomy_leaf_key"], "unknown")
        accepted = classify_with_artifact(result["artifact_path"], text=fixtures.TEXTS["phone"], allow_presentation=True)
        self.assertEqual(accepted["taxonomy_leaf_key"], "phone")
        self.assertTrue(accepted["acceptance"]["presentation_only"])
        self.assertFalse(accepted["acceptance"]["validation_passed"])
        rejected = classify_with_artifact(result["artifact_path"], text=fixtures.TEXTS["unknown"], allow_presentation=True)
        self.assertEqual(rejected["taxonomy_leaf_key"], "unknown")
        with patch("app.services.classification.ready_leaf_keys", return_value=set(self.fixture.labels)), \
                patch("app.services.classification.taxonomy_coverage", return_value={"ready": True}):
            live = classify_text_domain(self.db, text=fixtures.TEXTS["phone"], model_snapshot=snapshot)
        self.assertEqual(live["domain"], "phone")
        self.assertIn(PRESENTATION_WARNING, live["warning"])

    def test_expired_tampered_or_missing_authorization_fails_closed(self):
        result = self.enable()
        payload = joblib.load(result["artifact_path"])
        expiry = datetime.fromisoformat(payload["presentation_authorization"]["expires_at"])
        self.assertFalse(presentation_authorization(payload, now=expiry)["authorized"])
        for kind in ("expired", "wrong_model", "missing", "unconfirmed", "bad_policy"):
            value = copy.deepcopy(payload)
            if kind == "expired":
                now = datetime.now(timezone.utc)
                value["presentation_authorization"].update(issued_at=(now - timedelta(hours=49)).isoformat(),
                                                          expires_at=(now - timedelta(hours=1)).isoformat())
            elif kind == "wrong_model":
                value["model_version"] = "different"
            elif kind == "missing":
                value.pop("presentation_authorization")
            elif kind == "unconfirmed":
                value["presentation_authorization"]["risk_acknowledged"] = False
            else:
                value["scope_policy"].pop("contrast_margin_threshold")
            with self.subTest(kind=kind), patch("app.services.classification_training.load_classification_artifact", return_value=value):
                prediction = classify_with_artifact("unused", text=fixtures.TEXTS["phone"],
                    allow_presentation=True, require_scope_validation=False)
                self.assertEqual(prediction["taxonomy_leaf_key"], "unknown")
                self.assertFalse(prediction["acceptance"]["accepted"])

    def test_changed_data_cannot_activate_stale_development_fit(self):
        with patch.object(command, "_dataset_fingerprint", return_value="changed"):
            with self.assertRaisesRegex(ValueError, "data changed"):
                self.enable()
        self.assertEqual(self.db.query(ClassificationModel).count(), 1)


if __name__ == "__main__":
    unittest.main()
