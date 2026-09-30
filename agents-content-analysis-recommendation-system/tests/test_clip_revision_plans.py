import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_current_user
from app.database.db import Base, get_db
from app.database.models import AnalysisResult, ClipRevisionPlan, Recommendation, SystemLog, User, UserContent
from app.routes.contents import router
from app.schemas.recommendation import RecommendationAnalysisResponse
from app.services.actionable_recommendations import build_actionable_recommendations
from app.services.persistence import save_video_analysis_result
from app.services.recommendation import build_recommendation_from_saved_content
from tests.test_actionable_recommendations import fixture_result


class ClipRevisionPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.url = f"sqlite:///{Path(self.temp.name) / 'plans.db'}"
        self._engine()
        Base.metadata.create_all(self.engine)
        with self.sessions() as db:
            user = User(username='plan-owner', email='plan@example.test', password_hash='test')
            other = User(username='other', email='other@example.test', password_hash='test')
            db.add_all([user, other])
            db.commit()
            self.user_id, self.other_id = user.user_id, other.user_id
            self.snapshot = fixture_result()
            self.snapshot['actionable_recommendations'] = build_actionable_recommendations(self.snapshot)
            saved = save_video_analysis_result(db, user=user, filename='plan.mp4', file_path='plan.mp4',
                transcript='รีวิวมือถือ แบตเตอรี่อึด', analysis_payload={}, nlp_result={}, recommendation_payload=self.snapshot)
            self.content_id = saved['content_id']
        self.actor = self.user_id
        self.app = FastAPI()
        self.app.include_router(router)
        def database():
            with self.sessions() as db:
                yield db
        self.app.dependency_overrides[get_db] = database
        self.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id=self.actor)
        self.client = TestClient(self.app)
        self.path = f'/contents/{self.content_id}/revision-plan'
        self.empty = self.client.get(self.path).json()

    def _engine(self):
        self.engine = create_engine(self.url, connect_args={'check_same_thread': False})
        @event.listens_for(self.engine, 'connect')
        def foreign_keys(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
        self.sessions = sessionmaker(bind=self.engine)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        self.temp.cleanup()

    def payload(self, *, revision=0, notes='ถ่ายฉากทดสอบเพิ่มเติม', selected=None):
        return {'analysis_id': self.empty['analysis_id'],
                'recommendation_fingerprint': self.empty['recommendation_fingerprint'],
                'expected_revision': revision, 'notes': notes,
                'selected_advice_ids': selected if selected is not None else
                    [self.snapshot['actionable_recommendations']['items'][0]['id']]}

    def test_save_restart_and_dataset_independent_snapshot(self):
        original = self.client.get(f'/contents/{self.content_id}').json()
        self.assertEqual(self.empty['revision'], 0)
        saved = self.client.put(self.path, json=self.payload())
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()['status'], 'planning')
        self.assertTrue(saved.json()['saved_at'])
        with self.sessions() as db:
            row = db.get(AnalysisResult, self.empty['analysis_id'])
            self.assertEqual(json.loads(row.summary)['recommendation'], self.snapshot)
        self.engine.dispose()
        self._engine()
        with patch('app.services.actionable_recommendations.template_catalog', side_effect=AssertionError('No rendering on read')):
            self.assertEqual(self.client.get(self.path).json(), saved.json())
            self.assertEqual(self.client.get(f'/contents/{self.content_id}').json(), original)

    def test_edit_and_deselect_round_trip_with_log(self):
        self.client.put(self.path, json=self.payload())
        response = self.client.put(self.path, json=self.payload(revision=1, notes='แผนฉบับแก้ไข', selected=[]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['revision'], 2)
        self.assertEqual(self.client.get(self.path).json()['selected_advice_ids'], [])
        with self.sessions() as db:
            self.assertEqual(db.query(ClipRevisionPlan).count(), 1)
            self.assertEqual(db.query(SystemLog).filter_by(action='clip_revision_plan_save', status='success').count(), 2)

    def test_ownership_and_authentication(self):
        self.actor = self.other_id
        self.assertEqual(self.client.get(self.path).status_code, 404)
        self.assertEqual(self.client.put(self.path, json=self.payload()).status_code, 404)
        self.app.dependency_overrides.pop(get_current_user)
        self.assertEqual(self.client.get(self.path).status_code, 401)

    def test_rejects_stale_tabs_source_and_invalid_advice_or_completed_state(self):
        saved = self.client.put(self.path, json=self.payload()).json()
        self.assertEqual(self.client.put(self.path, json=self.payload()).status_code, 409)
        for changed in [dict(self.payload(revision=1), analysis_id=9999),
                        dict(self.payload(revision=1), recommendation_fingerprint='a' * 64)]:
            self.assertEqual(self.client.put(self.path, json=changed).status_code, 409)
        for changed in [self.payload(revision=1, selected=['not-in-snapshot']),
                        dict(self.payload(revision=1), completed=True),
                        self.payload(revision=1, notes='ก' * 4001),
                        self.payload(revision=1, selected=self.payload()['selected_advice_ids'] * 2)]:
            self.assertEqual(self.client.put(self.path, json=changed).status_code, 422)
        self.assertEqual(self.client.get(self.path).json(), saved)
        self.assertEqual(self.client.put(self.path, json=self.payload(revision=1)).status_code, 200)
        self.assertEqual(self.client.put(self.path, json=self.payload(revision=1, notes='stale tab')).status_code, 409)

    def test_failed_commit_rolls_back_and_does_not_log_success(self):
        saved = self.client.put(self.path, json=self.payload()).json()
        with patch.object(Session, 'commit', side_effect=SQLAlchemyError('database unavailable')):
            response = self.client.put(self.path, json=self.payload(revision=1, notes='must not persist'))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.client.get(self.path).json(), saved)
        with self.sessions() as db:
            self.assertEqual(db.query(SystemLog).filter_by(action='clip_revision_plan_save').count(), 1)

    def test_tampered_snapshot_is_not_silently_substituted(self):
        self.client.put(self.path, json=self.payload())
        with self.sessions() as db:
            row = db.get(AnalysisResult, self.empty['analysis_id'])
            summary = json.loads(row.summary)
            summary['recommendation']['actionable_recommendations']['items'][0]['example'] = 'changed later'
            row.summary = json.dumps(summary)
            db.commit()
        self.assertEqual(self.client.get(self.path).status_code, 409)
        self.assertEqual(self.client.put(self.path, json=self.payload(revision=1)).status_code, 409)

    def test_withheld_snapshot_cannot_select_stale_advice_but_can_save_notes(self):
        with self.sessions() as db:
            row = db.get(AnalysisResult, self.empty['analysis_id'])
            summary = json.loads(row.summary)
            summary['recommendation']['classification'] = {'is_unknown': True}
            row.summary = json.dumps(summary)
            db.commit()
        self.empty = self.client.get(self.path).json()
        self.assertEqual(self.client.put(self.path, json=self.payload()).status_code, 422)
        self.assertEqual(self.client.put(self.path, json=self.payload(selected=[])).status_code, 200)

    def test_legacy_output_remains_readable_without_recomputing(self):
        with self.sessions() as db:
            row = db.get(AnalysisResult, self.empty['analysis_id'])
            row.summary = '{}'
            recommendation = db.query(Recommendation).filter_by(content_id=self.content_id).one()
            recommendation.recommended_keywords = json.dumps({'domain': 'phone', 'missing_keywords': ['battery']})
            recommendation.recommended_duration = 123
            db.commit()
        with patch('app.services.recommendation.build_recommendation_from_text', side_effect=AssertionError('Never recompute history')):
            response = self.client.get(f'/contents/{self.content_id}')
            self.assertEqual(response.status_code, 200)
            snapshot = response.json()['recommendation']
            self.assertEqual(snapshot['missing_keywords'][0]['keyword'], 'battery')
            self.assertEqual(snapshot['recommended_duration']['historical_seconds'], 123)
            self.assertIsNone(snapshot['recommended_duration']['recommended_seconds'])
            RecommendationAnalysisResponse.model_validate(snapshot)
            with self.sessions() as db:
                self.assertEqual(build_recommendation_from_saved_content(db, content_id=self.content_id, user_id=self.user_id), snapshot)
        self.empty = self.client.get(self.path).json()
        self.assertEqual(self.client.put(self.path, json=self.payload(selected=[])).status_code, 200)

    def test_owner_deletion_cascades_to_plan(self):
        self.client.put(self.path, json=self.payload())
        with self.sessions() as db:
            db.delete(db.get(UserContent, self.content_id))
            db.commit()
            self.assertEqual(db.query(ClipRevisionPlan).count(), 0)


if __name__ == '__main__':
    unittest.main()
