import hashlib
import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.database.db import Base, get_db
from app.database.migrations import migrate_scope_completion_schema
from app.database.models import (
    AnalysisResult, DatasetContent, FollowedTopic, Notification, SystemConfig,
    SystemLog, TrendSnapshotItem, TrendSnapshotRun, User, UserContent,
)
from app.routes.admin import router as admin_router
from app.routes.contents import router as contents_router
from app.routes.follows import router as follows_router
from app.services.admin_report import delete_admin_dataset, list_admin_datasets, update_admin_dataset
from app.services.dataset_eligibility import production_transcript_query
from app.services.follows import follow_topic, save_follow_preferences, unfollow_topic
from app.services.live_trend_notifications import compare_live_trend_snapshot
from app.services.live_trend_snapshots import YOUTUBE_CATEGORY_TITLES, _youtube_category_scope
from app.services.trend_watch_sessions import start_trend_watch_session
from app.services.trend_settings import TrendScheduleParameters, save_trend_schedule, trend_schedule
from app.services.trending_fetcher import run_scheduled_refreshes
from app.services.usage_statistics import usage_statistics
from app.schemas.admin_report import AdminDatasetUpdate


class ScopeCompletionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        @event.listens_for(self.engine, 'connect')
        def foreign_keys(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.db = self.sessions()
        self.admin = User(username='admin', email='admin@test.invalid', role='admin', password_hash='unused')
        self.user = User(username='creator', email='creator@test.invalid', role='user', password_hash='unused')
        self.db.add_all([self.admin, self.user, SystemConfig()])
        self.db.commit()
        app = FastAPI()
        for router in (admin_router, contents_router, follows_router):
            app.include_router(router)
        self.actor = self.user
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[get_current_user] = lambda: self.actor
        self.app = app
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def test_dataset_readiness_is_admin_only_and_validates_filters(self):
        self.assertEqual(self.client.get('/admin/datasets/readiness').status_code, 403)
        self.actor = self.admin
        response = self.client.get('/admin/datasets/readiness')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['total'], 0)
        self.assertEqual(response.json()['policy']['reference_splits'], ['train'])
        self.assertEqual(self.client.get('/admin/datasets/readiness?role=made_up').status_code, 422)
        self.assertEqual(self.client.get('/admin/datasets/readiness?limit=101').status_code, 422)

    def test_trash_restore_admin_api_requires_permission_and_confirmation(self):
        row = DatasetContent(title='Legacy record', source_platform='youtube',
            deleted_at=datetime.utcnow(), is_active=False, is_training_eligible=False)
        self.db.add(row)
        self.db.commit()
        url = f'/admin/datasets/{row.dataset_id}/restore'
        self.assertEqual(self.client.post(url, params={'confirmation_id': row.dataset_id}).status_code, 403)
        self.assertEqual(self.client.get('/admin/sources/health').status_code, 403)
        self.actor = self.admin
        self.assertEqual(self.client.get('/admin/datasets').json()['total'], 0)
        trash = self.client.get('/admin/datasets?trashed=true').json()
        self.assertEqual(trash['total'], 1)
        self.assertEqual(trash['items'][0]['quality']['status'], 'archived')
        self.assertEqual(self.client.post(url, params={'confirmation_id': row.dataset_id + 1}).status_code, 422)
        result = self.client.post(url, params={'confirmation_id': row.dataset_id})
        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.json()['deleted_at'])
        self.assertFalse(result.json()['is_training_eligible'])
        self.assertFalse(row.is_keyword_recommendation_eligible)
        self.assertEqual(self.client.post(url, params={'confirmation_id': row.dataset_id}).status_code, 404)
        self.assertEqual(self.client.get('/admin/datasets?trashed=true').json()['total'], 0)
        self.assertEqual(self.client.get('/admin/sources/health').status_code, 200)

    def test_reference_statistics_admin_auth_validation_and_background_job(self):
        self.assertEqual(self.client.get('/admin/reference-statistics').status_code, 403)
        self.assertEqual(self.client.post('/admin/reference-statistics/refresh').status_code, 403)
        self.actor = self.admin
        values = {'enabled': True, 'interval_seconds': 10800, 'daily_request_budget': 20}
        self.assertEqual(self.client.put('/admin/reference-statistics/settings', json=values).status_code, 200)
        self.assertEqual(self.client.get('/admin/reference-statistics/settings').json()['interval_seconds'], 10800)
        self.assertEqual(self.client.put('/admin/reference-statistics/settings', json={**values, 'interval_seconds': 1}).status_code, 422)
        self.assertEqual(self.client.get('/admin/reference-statistics?offset=-1').status_code, 422)
        self.assertEqual(self.client.get('/admin/datasets/999/statistics').status_code, 404)
        with patch('app.services.jobs.enqueue', return_value='queued-test') as enqueue:
            result = self.client.post('/admin/reference-statistics/refresh')
            self.assertEqual(result.status_code, 202)
            enqueue.assert_called_once()

    def analysis(self, user, when, *, leaf='phone', unknown=False, dataset=None):
        content = UserContent(user_id=user.user_id, title='saved clip')
        self.db.add(content)
        self.db.flush()
        result = AnalysisResult(content_id=content.content_id, created_at=when,
                                taxonomy_leaf_key=leaf, classification_is_unknown=unknown,
                                summary='{}', dataset_id=dataset.dataset_id if dataset else None)
        self.db.add(result)
        self.db.commit()
        return result

    def snapshot(self, kind='global', entries=(), *, states=None, when=None):
        if states is None:
            states = ({'youtube': {'status': 'ok'}, 'google': {'status': 'empty'}} if kind == 'global'
                      else {'youtube': {'status': 'ok', 'categories': {
                          '20': {'status': 'ok'}, '24': {'status': 'ok'}}}})
        run = TrendSnapshotRun(snapshot_kind=kind, region='TH', status='completed',
                               provider_status=json.dumps(states),
                               started_at=when or datetime.utcnow(), completed_at=when or datetime.utcnow())
        self.db.add(run)
        self.db.flush()
        for rank, (title, category) in enumerate(entries, 1):
            self.db.add(TrendSnapshotItem(
                run_id=run.run_id, platform='youtube', source_platform='youtube_live', title=title,
                trend_key=hashlib.sha1(title.encode()).hexdigest(), category_id=category,
                category=YOUTUBE_CATEGORY_TITLES[category], provider_rank=rank,
                ranking_scope='global' if kind == 'global' else _youtube_category_scope(category),
                video_url=f'https://youtube.example/{title}', views=100, likes=10,
            ))
        self.db.commit()
        return run

    def watch(self):
        return start_trend_watch_session(self.db, user=self.user, region='TH')

    def compare(self, session):
        return compare_live_trend_snapshot(self.db, user=self.user, watch_session=session, region='TH', limit=50)

    def test_statistics_bangkok_boundary_leap_month_and_user_isolation(self):
        self.analysis(self.user, datetime(2024, 2, 28, 17), leaf='camera')
        self.analysis(self.user, datetime(2024, 2, 29, 16, 59), unknown=True)
        self.analysis(self.user, datetime(2024, 2, 29, 17))  # March in Bangkok.
        self.analysis(self.admin, datetime(2024, 2, 1))
        data = usage_statistics(self.db, user_id=self.user.user_id, year=2024, month=2)
        self.assertEqual(data['total'], 2)
        self.assertEqual(len(data['series']), 29)
        self.assertEqual(data['series'][-1], {'index': 29, 'count': 2})
        self.assertEqual({r['category'] for r in data['categories']}, {'camera', 'unknown'})
        data = self.client.get('/contents/statistics?year=2024&month=2&user_id=1').json()
        self.assertEqual(data['total'], 2)
        self.assertEqual(data['scope'], 'personal')
        self.assertNotIn('transcript', data)
        self.assertEqual(self.client.get('/admin/usage-statistics?year=2024').status_code, 403)
        self.actor = self.admin
        admin = self.client.get('/admin/usage-statistics?year=2024').json()
        self.assertEqual(admin['total'], 4)
        self.assertEqual(admin['series'][2]['count'], 1)

    def test_statistics_empty_period_zero_filled_and_invalid_dates(self):
        data = self.client.get('/contents/statistics?year=2025').json()
        self.assertEqual(len(data['series']), 12)
        self.assertEqual(data['total'], 0)
        for path in ('year=1999', 'year=9999', 'year=2025&month=13', 'year=2025&month=0'):
            self.assertEqual(self.client.get('/contents/statistics?' + path).status_code, 422)
        self.app.dependency_overrides.pop(get_current_user)
        self.assertEqual(self.client.get('/contents/statistics?year=2025').status_code, 401)

    def test_schedule_is_admin_only_persisted_and_used_after_reopening_session(self):
        payload = {'enabled': True, 'global_interval_seconds': 120, 'category_interval_seconds': 900}
        self.assertEqual(self.client.put('/admin/trend-settings', json=payload).status_code, 403)
        self.actor = self.admin
        self.assertEqual(self.client.put('/admin/trend-settings', json={**payload, 'global_interval_seconds': 1}).status_code, 422)
        self.assertEqual(self.client.put('/admin/trend-settings', json=payload).status_code, 200)
        now = datetime(2025, 6, 1)
        self.snapshot(when=now)
        self.snapshot('youtube_categories', when=now)
        global_fetch, category_fetch = Mock(), Mock()
        def execute(seconds):
            return run_scheduled_refreshes(session_factory=self.sessions, now=now + timedelta(seconds=seconds),
                                           global_fetch=global_fetch, category_fetch=category_fetch)
        self.assertEqual(execute(119), [])
        self.assertEqual(execute(120), ['global'])
        self.assertEqual(execute(900), ['global', 'youtube_categories'])
        self.assertEqual(category_fetch.call_count, 1)
        with self.sessions() as other:
            self.assertEqual(trend_schedule(other)['category_interval_seconds'], 900)
        self.assertEqual(self.db.query(SystemLog).filter_by(action='admin_trend_schedule_update').count(), 1)

    def test_schedule_pause_and_failed_attempt_backoff(self):
        config = TrendScheduleParameters(enabled=False, global_interval_seconds=60, category_interval_seconds=60)
        save_trend_schedule(self.db, config, user_id=self.admin.user_id)
        fetch = Mock()
        self.assertEqual(run_scheduled_refreshes(session_factory=self.sessions, global_fetch=fetch, category_fetch=fetch), [])
        fetch.assert_not_called()
        config.enabled = True
        save_trend_schedule(self.db, config, user_id=self.admin.user_id)
        now = datetime(2025, 6, 1)
        run = self.snapshot(when=now)
        run.status = 'failed'
        self.db.commit()
        state = trend_schedule(self.db, now=now + timedelta(seconds=20))
        self.assertFalse(state['runs']['global']['due'])
        self.assertIsNone(state['runs']['global']['last_success_at'])

    def test_hourly_schedule_api_validates_and_reopens_saved_window(self):
        payload = {'enabled': True, 'schedule_mode': 'hourly_window',
                   'start_hour': 14, 'end_hour': 23,
                   'global_interval_seconds': 60, 'category_interval_seconds': 60}
        self.assertEqual(self.client.put('/admin/trend-settings', json=payload).status_code, 403)
        self.actor = self.admin
        self.assertEqual(self.client.put('/admin/trend-settings', json={**payload, 'end_hour': 13}).status_code, 422)
        response = self.client.put('/admin/trend-settings', json=payload)
        self.assertEqual(response.status_code, 200)
        data = self.client.get('/admin/trend-settings').json()
        self.assertEqual(data['schedule_mode'], 'hourly_window')
        self.assertEqual(data['window']['collections_per_day'], 10)
        self.assertEqual(data['global_interval_seconds'], 3600)

    def test_scheduler_failure_does_not_starve_category_refresh(self):
        global_fetch = Mock(side_effect=RuntimeError('provider unavailable'))
        category_fetch = Mock()
        with self.assertRaisesRegex(RuntimeError, 'global: provider unavailable'):
            run_scheduled_refreshes(session_factory=self.sessions,
                                    global_fetch=global_fetch, category_fetch=category_fetch)
        category_fetch.assert_called_once()

    def test_scheduler_applies_pause_saved_during_inflight_fetch(self):
        def pause():
            with self.sessions() as db:
                config = db.query(SystemConfig).filter(SystemConfig.user_id.is_(None)).one()
                config.trend_refresh_enabled = False
                db.commit()
        category_fetch = Mock()
        self.assertEqual(run_scheduled_refreshes(session_factory=self.sessions,
                         global_fetch=pause, category_fetch=category_fetch), ['global'])
        category_fetch.assert_not_called()

    def test_dataset_delete_preserves_history_and_hides_from_new_use(self):
        row = DatasetContent(title='reference', category='phone', source_platform='youtube')
        self.db.add(row)
        self.db.commit()
        result = self.analysis(self.user, datetime(2025, 1, 1), dataset=row)
        url = f'/admin/datasets/{row.dataset_id}?confirmation_id={row.dataset_id}'
        self.assertEqual(self.client.delete(url).status_code, 403)
        self.actor = self.admin
        self.assertEqual(self.client.delete(f'/admin/datasets/{row.dataset_id}?confirmation_id=999').status_code, 422)
        self.assertIsNone(row.deleted_at)
        self.assertEqual(self.client.delete(url).status_code, 200)
        self.db.refresh(row)
        self.assertIsNotNone(row.deleted_at)
        self.assertFalse(row.is_active or row.is_training_eligible or row.is_keyword_recommendation_eligible or row.is_duration_recommendation_eligible)
        self.assertEqual(list_admin_datasets(self.db)[0], 0)
        self.assertEqual(production_transcript_query(self.db).count(), 0)
        self.assertIsNotNone(self.db.get(AnalysisResult, result.result_id))
        self.assertEqual(result.dataset_id, row.dataset_id)
        self.assertEqual(self.client.delete(url).status_code, 404)
        self.assertIsNone(update_admin_dataset(self.db, dataset_id=row.dataset_id, payload=AdminDatasetUpdate(title='restore')))
        self.assertEqual(self.db.query(SystemLog).filter_by(action='admin_dataset_delete').count(), 1)

    def test_follow_validation_duplicates_and_account_isolation(self):
        request = {'match_type': 'category', 'platform': 'youtube', 'value': '20'}
        first = self.client.post('/follows/topic', json=request)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(self.client.post('/follows/topic', json=request).json()['id'], first.json()['id'])
        for invalid in ({**request, 'platform': 'google'}, {**request, 'value': 'phone'},
                        {'match_type': 'keyword', 'value': '   '}):
            self.assertEqual(self.client.post('/follows/topic', json=invalid).status_code, 400)
        self.actor = self.admin
        self.assertEqual(self.client.get('/follows/topics').json()['total'], 0)
        self.assertEqual(self.client.delete(f"/follows/topic/{first.json()['id']}").json()['deleted'], 0)

    def test_category_notifications_baseline_new_items_and_global_deduplication(self):
        self.snapshot(entries=[('old', '20')])
        self.snapshot('youtube_categories', [('old', '20')])
        session = self.watch()
        follow_topic(self.db, user_id=self.user.user_id, match_type='category', platform='youtube', value='20')
        save_follow_preferences(self.db, user_id=self.user.user_id, mode='following')
        self.assertEqual(self.compare(session)['new_count'], 0)
        self.snapshot(entries=[('new', '20'), ('unrelated', '24')])
        self.snapshot('youtube_categories', [('old', '20'), ('new', '20'), ('unrelated', '24')])
        result = self.compare(session)
        self.assertEqual(result['new_count'], 1)
        self.assertEqual(result['new_notifications'][0].title, 'new')
        payload = json.loads(result['new_notifications'][0].payload)
        self.assertEqual(payload['matched_interests'], ['Gaming'])
        self.assertEqual(self.compare(session)['new_count'], 0)

    def test_category_failure_recovery_and_no_global_snapshot(self):
        self.snapshot('youtube_categories', [('old', '20')])
        session = self.watch()
        follow_topic(self.db, user_id=self.user.user_id, match_type='category', platform='youtube', value='20')
        self.snapshot('youtube_categories', states={'youtube': {'status': 'partial', 'categories': {'20': {'status': 'error'}}}})
        self.assertEqual(self.compare(session)['new_count'], 0)
        self.snapshot('youtube_categories', [('old', '20'), ('new', '20')])
        self.assertEqual(self.compare(session)['new_count'], 1)

    def test_following_mode_no_matches_and_unfollow_do_not_notify(self):
        self.snapshot()
        self.snapshot('youtube_categories')
        session = self.watch()
        save_follow_preferences(self.db, user_id=self.user.user_id, mode='following')
        topic = follow_topic(self.db, user_id=self.user.user_id, match_type='category', platform='youtube', value='20')
        unfollow_topic(self.db, user_id=self.user.user_id, id=topic.id)
        self.snapshot(entries=[('gaming', '20')])
        self.snapshot('youtube_categories', [('gaming', '20')])
        self.assertEqual(self.compare(session)['new_count'], 0)
        self.assertEqual(self.db.query(Notification).count(), 0)

    def test_off_mode_advances_cursor_without_creating_notifications(self):
        self.snapshot()
        session = self.watch()
        save_follow_preferences(self.db, user_id=self.user.user_id, mode='off')
        latest = self.snapshot(entries=[('a', '20')])
        self.assertEqual(self.compare(session)['new_count'], 0)
        self.assertEqual(session.last_seen_run_id, latest.run_id)
        save_follow_preferences(self.db, user_id=self.user.user_id, mode='all')
        self.assertEqual(self.compare(session)['new_count'], 0)
        self.snapshot(entries=[('a', '20'), ('b', '24')])
        self.assertEqual(self.compare(session)['new_count'], 1)

    def test_new_follow_does_not_backfill_already_captured_items(self):
        old = datetime.utcnow() - timedelta(minutes=10)
        self.snapshot(when=old)
        self.snapshot('youtube_categories', when=old)
        session = self.watch()
        self.snapshot('youtube_categories', [('existing', '20')], when=old + timedelta(minutes=1))
        follow_topic(self.db, user_id=self.user.user_id, match_type='category', platform='youtube', value='20')
        save_follow_preferences(self.db, user_id=self.user.user_id, mode='following')
        self.assertEqual(self.compare(session)['new_count'], 0)

    def test_reenable_without_polling_while_off_does_not_replay_backlog(self):
        self.snapshot()
        session = self.watch()
        save_follow_preferences(self.db, user_id=self.user.user_id, mode='off')
        self.snapshot(entries=[('captured_while_off', '20')])
        save_follow_preferences(self.db, user_id=self.user.user_id, mode='all')
        self.assertEqual(self.compare(session)['new_count'], 0)


class ScopeMigrationTests(unittest.TestCase):
    def test_additive_migration_keeps_existing_data_and_is_repeatable(self):
        engine = create_engine('sqlite://')
        with engine.begin() as connection:
            for table in ('dataset_contents', 'system_configs', 'followed_topics', 'user_trend_watch_sessions'):
                connection.execute(text(f'CREATE TABLE {table} (id INTEGER PRIMARY KEY)'))
                connection.execute(text(f'INSERT INTO {table} (id) VALUES (7)'))
            added = migrate_scope_completion_schema(engine)['added_columns']
            self.assertEqual(len(added), 8)
            self.assertIn('dataset_contents.deletion_state_json', added)
        self.assertEqual(migrate_scope_completion_schema(engine)['added_columns'], [])
        with engine.begin() as connection:
            self.assertEqual(connection.execute(text('SELECT trend_notification_mode FROM system_configs')).scalar(), 'all')
            self.assertEqual(connection.execute(text('SELECT id FROM dataset_contents')).scalar(), 7)
        engine.dispose()


if __name__ == '__main__':
    unittest.main()
