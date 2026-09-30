import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database.db import Base
from app.database.migrations import migrate_trend_scheduler_schema
from app.database.models import SystemConfig, SystemLog, TrendCollectionSlot
from app.services.trend_scheduler import collect_due, collector_lock
from app.services.trend_settings import TrendScheduleParameters, save_trend_schedule, trend_schedule


class TrendSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.now = datetime(2026, 9, 20, 7)  # 14:00 in Bangkok
        self.parameters = TrendScheduleParameters(enabled=True, schedule_mode='hourly_window',
            global_interval_seconds=3600, category_interval_seconds=3600)
        with self.sessions() as db:
            save_trend_schedule(db, self.parameters, user_id=None)
        self.global_fetch = Mock(return_value={'status': 'completed', 'run_id': 10, 'total_items': 100})
        self.category_fetch = Mock(return_value={'status': 'completed', 'run_id': 11, 'total_items': 550})

    def tearDown(self):
        self.engine.dispose()

    def collect(self, when=None, actor='backend'):
        return collect_due(session_factory=self.sessions, now=when or self.now, actor=actor,
                           global_fetch=self.global_fetch, category_fetch=self.category_fetch)

    def test_ten_hourly_rounds_with_explicit_bangkok_boundaries(self):
        self.assertEqual(self.collect(self.now - timedelta(seconds=1))['status'], 'not_due')
        for hour in range(10):
            self.assertEqual(self.collect(self.now + timedelta(hours=hour))['status'], 'completed')
        self.assertEqual(self.collect(self.now + timedelta(hours=10))['status'], 'not_due')
        self.assertEqual(self.global_fetch.call_count, 10)
        self.assertEqual(self.category_fetch.call_count, 10)
        with self.sessions() as db:
            self.assertEqual(db.query(TrendCollectionSlot).count(), 10)
            next_day = trend_schedule(db, now=self.now + timedelta(hours=10))['window']
            self.assertEqual(next_day['next_at'], '2026-09-21T07:00:00Z')

    def test_backend_and_external_worker_share_slot_across_sessions(self):
        self.collect(actor='backend')
        self.assertEqual(self.collect(self.now + timedelta(minutes=10), 'task_scheduler')['executed'], [])
        self.global_fetch.assert_called_once()
        with self.sessions() as db:
            self.assertEqual(db.query(TrendCollectionSlot).one().actor, 'backend')
            config = db.query(SystemConfig).filter(SystemConfig.user_id.is_(None)).one()
            self.assertIsNotNone(config.trend_worker_seen_at)
            self.assertEqual(config.trend_worker_status, 'not_due')
            self.assertEqual(db.query(SystemLog).filter_by(action='trend_scheduled_collection').count(), 1)

    def test_late_start_collects_current_hour_only_without_backdating(self):
        now = self.now + timedelta(hours=6, minutes=45)
        self.collect(now, 'task_scheduler')
        with self.sessions() as db:
            row = db.query(TrendCollectionSlot).one()
            self.assertEqual(row.scheduled_for, self.now + timedelta(hours=6))
            self.assertEqual(row.started_at, now)
            slots = trend_schedule(db, now=now)['window']['slots_today']
            self.assertEqual(sum(s['status'] == 'missed' for s in slots), 6)
            self.assertEqual(sum(s['status'] == 'completed' for s in slots), 1)

    def test_partial_failure_keeps_success_and_does_not_retry_same_slot(self):
        self.global_fetch.return_value = {'status': 'failed', 'run_id': 10}
        result = self.collect()
        self.assertEqual(result['status'], 'partial')
        self.category_fetch.assert_called_once()
        self.assertEqual(self.collect()['executed'], [])
        with self.sessions() as db:
            self.assertEqual(db.query(TrendCollectionSlot).one().status, 'partial')

    def test_exception_is_audited_without_persisting_secrets(self):
        self.global_fetch.side_effect = RuntimeError('secret API key should not be saved')
        self.category_fetch.side_effect = TimeoutError('secret password')
        self.assertEqual(self.collect()['status'], 'failed')
        with self.sessions() as db:
            row = db.query(TrendCollectionSlot).one()
            self.assertNotIn('secret', row.result_json)
            self.assertIn('RuntimeError', row.result_json)

    def test_pause_and_window_edits_are_read_from_database(self):
        self.parameters.enabled = False
        with self.sessions() as db:
            save_trend_schedule(db, self.parameters, user_id=None)
        self.assertEqual(self.collect()['status'], 'paused')
        self.parameters.enabled = True
        self.parameters.start_hour = 16
        with self.sessions() as db:
            save_trend_schedule(db, self.parameters, user_id=None)
        self.assertEqual(self.collect()['status'], 'not_due')
        self.assertEqual(self.collect(self.now + timedelta(hours=2))['status'], 'completed')

    def test_pause_during_global_request_prevents_category_request(self):
        def pause():
            with self.sessions() as db:
                config = db.query(SystemConfig).filter(SystemConfig.user_id.is_(None)).one()
                config.trend_refresh_enabled = False
                db.commit()
            return {'status': 'completed'}
        self.global_fetch.side_effect = pause
        self.assertEqual(self.collect()['status'], 'partial')
        self.category_fetch.assert_not_called()

    def test_busy_lock_prevents_second_worker(self):
        with collector_lock(self.sessions) as locked:
            self.assertTrue(locked)
            self.assertEqual(self.collect()['status'], 'busy')
        self.global_fetch.assert_not_called()

    def test_crashed_slot_is_not_replayed_after_restart(self):
        with self.sessions() as db:
            db.add(TrendCollectionSlot(region='TH', scheduled_for=self.now,
                actor='task_scheduler', status='running', started_at=self.now))
            db.commit()
        self.assertEqual(self.collect(self.now + timedelta(minutes=20))['status'], 'not_due')
        with self.sessions() as db:
            state = trend_schedule(db, now=self.now + timedelta(minutes=20))
            self.assertEqual(state['window']['slots_today'][0]['status'], 'interrupted')
        self.assertEqual(self.collect(self.now + timedelta(hours=1))['status'], 'completed')

    def test_external_runner_does_not_run_legacy_interval_mode(self):
        self.parameters.schedule_mode = 'interval'
        with self.sessions() as db:
            save_trend_schedule(db, self.parameters, user_id=None)
        self.assertEqual(self.collect(actor='task_scheduler')['status'], 'interval_mode')
        self.global_fetch.assert_not_called()

    def test_validation_and_hourly_intervals_are_consistent(self):
        with self.assertRaises(ValueError):
            TrendScheduleParameters(enabled=True, global_interval_seconds=60,
                category_interval_seconds=60, start_hour=23, end_hour=14)
        self.assertEqual(TrendScheduleParameters(enabled=True, global_interval_seconds=60,
            category_interval_seconds=120, schedule_mode='hourly_window').global_interval_seconds, 3600)

    def test_migration_is_idempotent_and_does_not_change_existing_mode(self):
        engine = create_engine('sqlite:///:memory:')
        with engine.begin() as connection:
            connection.execute(text('CREATE TABLE system_configs (config_id INTEGER PRIMARY KEY)'))
            connection.execute(text('INSERT INTO system_configs VALUES (1)'))
        self.assertEqual(len(migrate_trend_scheduler_schema(engine)['added_columns']), 5)
        self.assertEqual(migrate_trend_scheduler_schema(engine)['added_columns'], [])
        with engine.connect() as connection:
            self.assertEqual(connection.execute(text('SELECT trend_schedule_mode FROM system_configs')).scalar(), 'interval')
        engine.dispose()


if __name__ == '__main__':
    unittest.main()
