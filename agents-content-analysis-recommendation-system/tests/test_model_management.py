import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import joblib
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_current_user
from app.database.db import Base, get_db
from app.database.models import ClassificationModel, DatasetCollectionRun, ModelEvaluationMetric, ModelTrainingRun, SystemLog, User
from app.routes.model_management import router
from app.services import model_management as service
from tests import test_classification_training as fixtures
from tests import test_classification_acceptance as scope_fixtures
from app.services.classification_acceptance import POLICY_VERSION


class ModelManagementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self.tmp.name) / 'training.db'}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.db = self.sessions()
        self.user = User(username="trainer", email="trainer@example.test", password_hash="unused", role="admin")
        self.db.add(self.user)
        self.db.commit()
        self.launch = patch.object(service, "launch_training_worker").start()
        patch.object(service, "TRAINING_LEAVES", ("phone", "camera")).start()
        patch.object(service, "ARTIFACT_ROOT", Path(self.tmp.name) / "artifacts").start()
        self.addCleanup(patch.stopall)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.tmp.cleanup()

    def seed(self):
        fixture = fixtures.ClassificationTrainingTests()
        fixture.db = self.db
        fixture.run = DatasetCollectionRun(run_key='test-run', dataset_source='youtube_cc', dataset_version='test-v1', status='reviewed', region_code='TH', languages_json='["th"]', query_config_json='{}')
        self.db.add(fixture.run)
        self.db.commit()
        fixture._seed_covered_two_leaf_dataset()

    def start(self):
        fingerprint = service.training_dataset(self.db)["dataset_fingerprint"]
        return service.start_training_run(self.db, user_id=self.user.user_id, dataset_fingerprint=fingerprint)

    def test_readiness_has_real_splits_without_creating_artifacts(self):
        self.seed()
        before = self.db.query(ClassificationModel).count()
        overview = service.training_overview(self.db)
        self.assertEqual(overview['dataset']['sample_count'], 60)
        self.assertTrue(overview['dataset']['ready'])
        self.assertEqual(overview['dataset']['channel_leakage_count'], 0)
        self.assertFalse(overview['dataset']['phase22_ready'])
        self.assertEqual(self.db.query(ClassificationModel).count(), before)
        self.assertFalse(service.ARTIFACT_ROOT.exists())

    def test_rejects_incomplete_and_changed_dataset(self):
        with self.assertRaisesRegex(ValueError, 'minimum'):
            self.start()
        self.seed()
        with self.assertRaises(service.TrainingConflict):
            service.start_training_run(self.db, user_id=self.user.user_id, dataset_fingerprint='0' * 64)
        self.launch.assert_not_called()

    def test_one_run_at_a_time_and_database_enforces_slot(self):
        self.seed()
        first = self.start()
        self.assertEqual(first['status'], 'queued')
        self.assertTrue(first['parameters']['enforce_phase22_gate'])
        self.assertFalse(first['parameters']['allow_embedding_download'])
        with self.assertRaises(service.TrainingConflict):
            self.start()
        with self.sessions() as other:
            other.add(ModelTrainingRun(run_id='another', requested_by=self.user.user_id, active_slot=1, parameters_json='{}'))
            with self.assertRaises(IntegrityError):
                other.commit()
        self.launch.assert_called_once_with(first['run_id'])

    def test_failed_launch_and_stale_workers_release_slot(self):
        self.seed()
        self.launch.side_effect = OSError('cannot launch')
        failed = self.start()
        self.assertEqual(failed['status'], 'failed')
        self.launch.side_effect = None
        started = self.start()
        row = self.db.get(ModelTrainingRun, started['run_id'])
        row.updated_at = datetime.utcnow() - timedelta(seconds=service.STALE_SECONDS + 1)
        self.db.commit()
        stale = service.get_training_run(self.db, row.run_id)
        self.assertEqual(stale['status'], 'interrupted')
        self.assertIsNone(self.db.get(ModelTrainingRun, row.run_id).active_slot)
        self.assertEqual(self.start()['status'], 'queued')

    def test_worker_trains_and_persists_results_without_activation(self):
        self.seed()
        old = self.add_evaluated_model(active=True)
        started = self.start()
        service.execute_training_run(started['run_id'], session_factory=self.sessions)
        self.db.expire_all()
        result = service.get_training_run(self.db, started['run_id'])
        self.assertEqual(result['status'], 'completed', result.get('error'))
        self.assertGreaterEqual(len(result['result']['model_ids']), 2)
        self.assertFalse(result['result']['active_model_changed'])
        self.assertTrue(self.db.get(ClassificationModel, old.model_id).is_active)
        self.assertTrue(all(self.db.get(ClassificationModel, i).status == 'evaluated_below_threshold' for i in result['result']['model_ids']))
        self.assertIsNone(self.db.get(ModelTrainingRun, started['run_id']).active_slot)
        for i in result['result']['model_ids']:
            detail = service.model_detail(self.db, i)
            self.assertTrue(detail['metrics'])
            self.assertTrue(detail['per_category'])
            self.assertTrue(detail['confusion_matrices'])
            self.assertFalse(detail['can_activate'])
        # A second invocation cannot fit or create additional models for this run.
        count = self.db.query(ClassificationModel).count()
        service.execute_training_run(started['run_id'], session_factory=self.sessions)
        self.assertEqual(self.db.query(ClassificationModel).count(), count)
        with self.sessions() as reopened:
            self.assertEqual(service.get_training_run(reopened, started['run_id'])['status'], 'completed')

    def test_worker_failure_is_persisted_and_never_changes_active_model(self):
        self.seed()
        started = self.start()
        with patch.object(service, 'train_and_evaluate_classification_models', side_effect=RuntimeError('fit failed')):
            service.execute_training_run(started['run_id'], session_factory=self.sessions)
        result = service.get_training_run(self.db, started['run_id'])
        self.assertEqual(result['status'], 'failed')
        self.assertIn('fit failed', result['error'])
        self.assertEqual(self.db.query(ClassificationModel).count(), 0)
        self.assertEqual(self.db.query(SystemLog).filter_by(action='classification_training_failed').count(), 1)

    def test_worker_rejects_dataset_changes_while_queued(self):
        self.seed()
        started = self.start()
        with patch.object(service, 'training_dataset', return_value={'dataset_fingerprint': 'changed'}), patch.object(service, 'train_and_evaluate_classification_models') as train:
            service.execute_training_run(started['run_id'], session_factory=self.sessions)
        train.assert_not_called()
        self.assertEqual(service.get_training_run(self.db, started['run_id'])['status'], 'failed')

    def add_evaluated_model(self, *, active=False, status='qualified'):
        version = f'v-{self.db.query(ClassificationModel).count()}'
        folder = Path(self.tmp.name) / version
        folder.mkdir()
        artifact = folder / 'model.joblib'
        scope_fixture = scope_fixtures.ClassificationAcceptanceTests()
        scope_fixture.setUp()
        joblib.dump({'artifact_schema_version': 3, 'model_key': 'test-model', 'model_version': version,
                     'labels': list(scope_fixture.labels), 'unknown_leaf_key': 'unknown', 'unknown_threshold': 0.6,
                     'estimator': scope_fixture.estimator, 'scope_policy': scope_fixture.fit(),
                     'scope_test_passed': True}, artifact)
        (folder / 'evaluation.json').write_text(json.dumps({'artifact_sha256': hashlib.sha256(artifact.read_bytes()).hexdigest()}), encoding='utf-8')
        model = ClassificationModel(model_key='test-model', model_version=version, model_type='test', taxonomy_version='v1', status=status, is_active=active, artifact_path=str(artifact))
        self.db.add(model)
        self.db.flush()
        for split, name in [('promotion_gate', 'passed'), ('artifact_check', 'reload_classify_passed')]:
            self.db.add(ModelEvaluationMetric(model_id=model.model_id, dataset_split=split, language='all', taxonomy_level=3, taxonomy_leaf_key='__overall__', metric_name=name, metric_value=1, sample_size=20,
                                             details=json.dumps({'unknown_threshold': 0.6,
                                                                 'scope_validation_status': 'validated',
                                                                 'scope_policy_version': POLICY_VERSION})))
        self.db.commit()
        return model

    def test_activation_requires_evaluation_integrity_and_current_confirmation(self):
        original = self.add_evaluated_model(active=True)
        target = self.add_evaluated_model()
        with self.assertRaises(service.TrainingConflict):
            service.activate_evaluated_model(self.db, target.model_id, expected_active_model_id=None, user_id=self.user.user_id)
        self.db.rollback()
        evaluation = Path(target.artifact_path).with_name('evaluation.json')
        correct = evaluation.read_text()
        evaluation.write_text('{"artifact_sha256":"bad"}')
        with self.assertRaisesRegex(ValueError, 'differs'):
            service.activate_evaluated_model(self.db, target.model_id, expected_active_model_id=original.model_id, user_id=self.user.user_id)
        self.db.rollback()
        evaluation.write_text(correct)
        activated = service.activate_evaluated_model(self.db, target.model_id, expected_active_model_id=original.model_id, user_id=self.user.user_id)
        self.assertTrue(activated['is_active'])
        self.db.expire_all()
        self.assertFalse(self.db.get(ClassificationModel, original.model_id).is_active)
        service.activate_evaluated_model(self.db, original.model_id, expected_active_model_id=target.model_id, user_id=self.user.user_id)
        self.db.expire_all()
        self.assertTrue(self.db.get(ClassificationModel, original.model_id).is_active)
        self.assertEqual(self.db.query(SystemLog).filter_by(action='classification_model_activate').first().user_id, self.user.user_id)

    def test_below_threshold_and_missing_evaluation_are_not_activatable(self):
        model = self.add_evaluated_model(status='evaluated_below_threshold')
        with self.assertRaises(ValueError):
            service.activate_evaluated_model(self.db, model.model_id, expected_active_model_id=None, user_id=self.user.user_id)
        self.db.rollback()
        model.status = 'qualified'
        self.db.query(ModelEvaluationMetric).delete()
        self.db.commit()
        self.assertFalse(service.model_detail(self.db, model.model_id)['can_activate'])

    def test_old_qualification_without_scope_evaluation_cannot_be_activated(self):
        model = self.add_evaluated_model()
        gate = self.db.query(ModelEvaluationMetric).filter_by(model_id=model.model_id, dataset_split='promotion_gate').one()
        gate.details = '{"unknown_threshold":0.6}'
        self.db.commit()
        self.assertFalse(service.model_detail(self.db, model.model_id)['can_activate'])
        with self.assertRaises(ValueError):
            service.activate_evaluated_model(self.db, model.model_id, expected_active_model_id=None, user_id=self.user.user_id)

    def test_admin_pages_share_readiness_and_do_not_change_active_model(self):
        from app.services.analysis_settings import get_analysis_settings
        model = self.add_evaluated_model(active=True)
        with patch('app.services.analysis_settings.check_model_readiness', return_value={'ready': True}):
            settings = get_analysis_settings(self.db, admin=True)
        detail = service.model_detail(self.db, model.model_id)
        self.assertEqual(settings['classification_model']['readiness'], detail['readiness'])
        self.assertTrue(detail['readiness']['scope_policy_valid'])
        self.assertTrue(self.db.get(ClassificationModel, model.model_id).is_active)

    def test_registry_gate_cannot_hide_missing_scope_policy_in_artifact(self):
        model = self.add_evaluated_model()
        payload = joblib.load(model.artifact_path)
        payload.pop('scope_policy')
        joblib.dump(payload, model.artifact_path)
        detail = service.model_detail(self.db, model.model_id)
        self.assertFalse(detail['can_activate'])
        self.assertIn('scope_policy_missing', detail['readiness']['reason_codes'])

    def test_all_training_endpoints_require_admin(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        paths = [('GET', '/admin/training'), ('POST', '/admin/training/channel-preview'), ('POST', '/admin/training/runs'), ('GET', '/admin/training/runs/abc'), ('GET', '/admin/training/models'), ('GET', '/admin/training/models/1'), ('POST', '/admin/training/models/1/activate')]
        with TestClient(app) as client:
            for method, path in paths:
                self.assertEqual(client.request(method, path).status_code, 401)
            self.user.role = 'user'
            app.dependency_overrides[get_current_user] = lambda: self.user
            for method, path in paths:
                self.assertEqual(client.request(method, path).status_code, 403)
            self.user.role = 'admin'
            self.assertEqual(client.get('/admin/training').status_code, 200)
            preview = client.post('/admin/training/channel-preview', json={'channel_ids': ['UC' + 'a' * 22]})
            self.assertEqual(preview.status_code, 200)
            self.assertFalse(preview.json()['database_changed'])
            self.assertEqual(client.post('/admin/training/channel-preview', json={'channel_ids': ['@creator']}).status_code, 422)
            self.assertEqual(client.get('/admin/training/models/999').status_code, 404)
            self.assertEqual(client.post('/admin/training/runs', json={'dataset_fingerprint': 'a'*64, 'promotion_threshold': 0.1}).status_code, 422)
            self.seed()
            fingerprint = service.training_dataset(self.db)['dataset_fingerprint']
            self.assertEqual(client.post('/admin/training/runs', json={'dataset_fingerprint': fingerprint}).status_code, 202)
            self.assertEqual(client.post('/admin/training/runs', json={'dataset_fingerprint': fingerprint}).status_code, 409)


if __name__ == '__main__':
    unittest.main()
