import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.database.db import Base, get_db
from app.database.migrations import migrate_training_requestor_schema
from app.database.models import (
    AnalysisResult, Cluster, ClusterMembership, ClusterRun, ContentKeyword, DatasetContent,
    FollowedTopic, Keyword, ModelTrainingRun, Notification, Recommendation,
    SystemConfig, SystemLog, User, UserContent, UserTrendWatchSession,
)
from app.routes.auth import router as auth_router
from app.routes.user_management import router
from app.services import user_management as service


class UserManagementTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        @event.listens_for(self.engine, 'connect')
        def foreign_keys(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.db = self.sessions()
        self.admin = User(username='admin_one', email='admin@example.test', role='admin', password_hash=hash_password('test-password'))
        self.target = User(username='creator_one', email='creator@example.test', role='user', password_hash=hash_password('test-password'))
        self.db.add_all([self.admin, self.target, SystemConfig()])
        self.db.commit()
        self.admin_id, self.target_id = self.admin.user_id, self.target.user_id
        app = FastAPI()
        app.include_router(router)
        app.include_router(auth_router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.app = app
        self.client = TestClient(app)
        self.client.headers.update(self.token(self.admin))
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'videos').mkdir()
        self.patches = [patch.object(service, 'ROOT', self.root), patch.object(service, 'UPLOAD_ROOT', self.root / 'videos')]
        for item in self.patches:
            item.start()

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()
        for item in self.patches:
            item.stop()
        self.tmp.cleanup()

    def token(self, user):
        session = UserTrendWatchSession(user_id=user.user_id, session_key=f'session-{user.user_id}-{self.db.query(UserTrendWatchSession).count()}')
        self.db.add(session)
        self.db.commit()
        return {'Authorization': 'Bearer ' + create_access_token(str(user.user_id), user.role, session_key=session.session_key)}

    def detail(self, user_id=None):
        response = self.client.get(f'/admin/users/{user_id or self.target_id}')
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def update(self, user_id=None, **changes):
        data = self.detail(user_id)
        fields = {key: data[key] for key in ('username', 'email', 'role', 'is_active')}
        return self.client.put(f"/admin/users/{data['user_id']}", json={**fields, 'expected_revision': data['revision'], **changes})

    def delete(self, user_id=None, **changes):
        data = self.detail(user_id)
        return self.client.request('DELETE', f"/admin/users/{data['user_id']}", json={
            'expected_revision': data['revision'], 'confirmation': data['username'], **changes})

    def test_list_counts_search_filters_and_never_returns_secrets(self):
        self.db.add(UserContent(user_id=self.target_id, title='clip'))
        self.db.commit()
        response = self.client.get('/admin/users', params={'q': 'CREATOR', 'role': 'user', 'state': 'active', 'limit': 1})
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['summary'], {'total': 2, 'active': 2, 'active_admins': 1})
        self.assertEqual(result['items'][0]['stats']['contents'], 1)
        self.assertNotIn('password', response.text)
        self.assertNotIn('session_key', response.text)
        self.assertEqual(self.client.get('/admin/users?q=%25').json()['total'], 0)
        self.assertEqual(self.client.get('/admin/users?offset=2').json()['items'], [])
        self.assertTrue(self.detail(self.admin_id)['is_self'])
        self.assertEqual(self.client.get('/admin/users?limit=1000').status_code, 422)

    def test_create_and_edit_identity_hash_password_audit_and_conflict(self):
        fields = {'username': ' second_admin ', 'email': ' NEW@EXAMPLE.TEST ', 'password': ' a-test-password ', 'role': 'admin'}
        response = self.client.post('/admin/users', json=fields)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()['username'], 'second_admin')
        user = self.db.get(User, response.json()['user_id'])
        self.assertTrue(verify_password(fields['password'], user.password_hash))
        self.assertEqual(user.email, 'new@example.test')
        self.assertEqual(self.client.post('/admin/users', json=fields).status_code, 409)
        self.assertEqual(self.update(username='creator_updated', email='new-creator@example.test').status_code, 200)
        self.assertEqual(self.update(email='new@example.test').status_code, 409)
        self.assertNotIn(fields['password'], ' '.join(r.detail or '' for r in self.db.query(SystemLog)))
        self.assertEqual(self.db.query(SystemLog).filter_by(action='admin_user_create').one().user_id, self.admin_id)

    def test_old_tokens_end_on_promotion_demotion_suspend_and_reenable(self):
        old = self.token(self.target)
        self.assertEqual(self.update(role='admin').status_code, 200)
        self.assertEqual(self.client.get('/admin/users', headers=old).status_code, 401)
        self.db.refresh(self.target)
        promoted = self.token(self.target)
        self.assertEqual(self.client.get('/admin/users', headers=promoted).status_code, 200)
        self.assertEqual(self.update(role='user').status_code, 200)
        self.assertEqual(self.client.get('/admin/users', headers=promoted).status_code, 401)
        self.db.refresh(self.target)
        normal = self.token(self.target)
        self.assertEqual(self.update(is_active=False).status_code, 200)
        self.assertEqual(self.client.get('/auth/me', headers=normal).status_code, 403)
        self.assertEqual(self.client.post('/auth/login', json={'email': self.target.email, 'password': 'test-password'}).status_code, 403)
        self.assertEqual(self.update(is_active=True).status_code, 200)
        self.assertEqual(self.client.get('/auth/me', headers=normal).status_code, 401)
        self.assertEqual(self.client.post('/auth/login', json={'email': self.target.email, 'password': 'test-password'}).status_code, 200)

    def test_self_and_last_admin_protection_and_revoked_actor(self):
        self.assertEqual(self.update(self.admin_id, role='user').status_code, 409)
        self.assertEqual(self.update(self.admin_id, is_active=False).status_code, 409)
        self.assertEqual(self.delete(self.admin_id).status_code, 409)
        response = self.client.post(f'/admin/users/{self.admin_id}/revoke-sessions', json={'expected_revision': self.detail(self.admin_id)['revision']})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.db.query(User).filter_by(role='admin', is_active=True).count(), 1)
        # Recheck the actor inside the mutation lock, even after dependency evaluation.
        from fastapi import HTTPException
        self.admin.role = 'user'
        self.db.commit()
        with self.assertRaises(HTTPException) as caught:
            service._lock_admin(self.db, self.admin_id)
        self.assertEqual(caught.exception.status_code, 403)

    def test_stale_edit_delete_and_confirmation_do_not_modify_account(self):
        old = self.detail()
        self.assertEqual(self.update(username='new_name').status_code, 200)
        fields = {key: old[key] for key in ('username', 'email', 'role', 'is_active')}
        response = self.client.put(f'/admin/users/{self.target_id}', json={**fields, 'expected_revision': old['revision']})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.delete(confirmation='incorrect').status_code, 422)
        self.assertEqual(self.delete(expected_revision=old['revision']).status_code, 409)
        self.assertEqual(self.detail()['username'], 'new_name')

    def test_revoke_all_sessions_preserves_data_and_allows_fresh_login(self):
        tokens = [self.token(self.target), self.token(self.target)]
        response = self.client.post(f'/admin/users/{self.target_id}/revoke-sessions', json={'expected_revision': self.detail()['revision']})
        self.assertEqual(response.json()['revoked_sessions'], 2)
        for token in tokens:
            self.assertEqual(self.client.get('/auth/me', headers=token).status_code, 401)
        self.assertTrue(self.detail()['is_active'])
        self.assertEqual(self.client.post('/auth/login', json={'email': self.target.email, 'password': 'test-password'}).status_code, 200)

    def seed_private_data(self):
        self.token(self.target)
        content = UserContent(user_id=self.target_id, title='private', video_url='videos/' + 'a' * 32 + '_clip.mp4')
        dataset = DatasetContent(title='shared training')
        keyword = Keyword(keyword='camera')
        cluster = Cluster(cluster_name='shared cluster')
        run = ClusterRun(user_id=self.target_id, n_clusters=1)
        self.db.add_all([content, dataset, keyword, cluster, run])
        self.db.flush()
        self.db.add_all([
            AnalysisResult(content_id=content.content_id), Recommendation(content_id=content.content_id),
            ContentKeyword(content_id=content.content_id, keyword_id=keyword.keyword_id),
            ClusterMembership(run_id=run.run_id, cluster_id=cluster.cluster_id, content_id=content.content_id, item_text='private'),
            FollowedTopic(user_id=self.target_id, match_type='keyword', value='camera'),
            SystemConfig(user_id=self.target_id), SystemLog(user_id=self.target_id, action='video_analyze_save', status='success', detail='legacy log'),
            ModelTrainingRun(run_id='history', requested_by=self.target_id, status='completed', parameters_json='{}'),
        ])
        session = self.db.query(UserTrendWatchSession).filter_by(user_id=self.target_id).first()
        self.db.add(Notification(user_id=self.target_id, watch_session_id=session.watch_session_id, trend_key='key', platform='youtube', title='trend', detected_at=session.started_at))
        self.db.commit()
        path = self.root / content.video_url
        path.write_bytes(b'test upload')
        return path

    def test_delete_cleans_private_children_and_preserves_shared_and_audit(self):
        path = self.seed_private_data()
        result = self.delete()
        self.assertEqual(result.status_code, 200, result.text)
        self.db.expire_all()
        self.assertIsNone(self.db.get(User, self.target_id))
        for model in (UserContent, AnalysisResult, Recommendation, ContentKeyword, FollowedTopic, Notification, ClusterMembership):
            self.assertEqual(self.db.query(model).count(), 0, model.__name__)
        self.assertEqual(self.db.query(UserTrendWatchSession).filter_by(user_id=self.target_id).count(), 0)
        self.assertEqual(self.db.query(DatasetContent).count(), 1)
        self.assertEqual(self.db.query(Keyword).count(), 1)
        self.assertEqual(self.db.query(SystemConfig).count(), 1)
        self.assertIsNone(self.db.get(ModelTrainingRun, 'history').requested_by)
        old_log = self.db.query(SystemLog).filter_by(action='video_analyze_save').one()
        self.assertIsNone(old_log.user_id)
        self.assertEqual(json.loads(old_log.detail)['deleted_actor_user_id'], self.target_id)
        self.assertEqual(json.loads(self.db.query(SystemLog).filter_by(action='admin_user_delete').one().detail)['retained_training_run_ids'], ['history'])
        self.assertFalse(path.exists())
        self.assertEqual(self.client.post('/auth/login', json={'email': 'creator@example.test', 'password': 'test-password'}).status_code, 401)

    def test_delete_blocks_running_training_and_unknown_foreign_keys_roll_back(self):
        path = self.seed_private_data()
        run = self.db.get(ModelTrainingRun, 'history')
        run.status, run.active_slot = 'running', 1
        self.db.commit()
        self.assertEqual(self.delete().status_code, 409)
        self.assertTrue(path.exists())
        run.status, run.active_slot = 'completed', None
        self.db.commit()
        from sqlalchemy import text
        self.db.execute(text('CREATE TABLE future_reference (user_id INTEGER REFERENCES users(user_id))'))
        self.db.execute(text('INSERT INTO future_reference VALUES (:id)'), {'id': self.target_id})
        self.db.commit()
        self.assertEqual(self.delete().status_code, 409)
        self.assertEqual(self.db.query(UserContent).count(), 1)
        self.assertTrue(path.exists())

    def test_delete_shared_file_alias_and_outside_paths_are_retained(self):
        path = self.seed_private_data()
        self.db.add(UserContent(user_id=self.admin_id, title='shared', video_url=str(path)))
        outside = self.root / 'original.mp4'
        outside.write_bytes(b'original')
        self.db.add(UserContent(user_id=self.target_id, title='external', video_url=str(outside)))
        self.db.commit()
        self.assertEqual(self.delete().status_code, 200)
        self.assertTrue(path.exists())
        self.assertTrue(outside.exists())

    def test_file_cleanup_failure_is_reported_without_restoring_account(self):
        self.seed_private_data()
        with patch.object(Path, 'unlink', side_effect=PermissionError('locked')):
            response = self.delete()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['files_remaining'], 1)
        self.assertEqual(self.db.query(SystemLog).filter_by(action='admin_user_file_cleanup').one().status, 'warning')

    def test_all_routes_authorized_and_validation_cannot_write_privileged_fields(self):
        routes = [('GET', '/admin/users'), ('GET', f'/admin/users/{self.target_id}'), ('POST', '/admin/users'),
                  ('PUT', f'/admin/users/{self.target_id}'), ('DELETE', f'/admin/users/{self.target_id}'),
                  ('POST', f'/admin/users/{self.target_id}/revoke-sessions')]
        self.client.headers.pop('Authorization')
        for method, path in routes:
            self.assertEqual(self.client.request(method, path).status_code, 401)
        normal = self.token(self.target)
        for method, path in routes:
            self.assertEqual(self.client.request(method, path, headers=normal).status_code, 403)
        self.client.headers.update(self.token(self.admin))
        self.assertEqual(self.update(role='superadmin').status_code, 422)
        self.assertEqual(self.update(password_hash='unsafe').status_code, 422)
        self.assertEqual(self.update(is_active='false').status_code, 422)
        self.assertEqual(self.update(username='  ').status_code, 422)
        self.assertEqual(self.client.get('/admin/users/9999').status_code, 404)

    def test_nullable_training_requestor_migration_is_idempotent(self):
        self.assertTrue(next(c for c in inspect(self.engine).get_columns('model_training_runs') if c['name'] == 'requested_by')['nullable'])
        self.assertEqual(migrate_training_requestor_schema(self.engine), {'changed': False})
        self.assertEqual(migrate_training_requestor_schema(self.engine), {'changed': False})


if __name__ == '__main__':
    unittest.main()
