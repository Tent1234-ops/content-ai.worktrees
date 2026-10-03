import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.db import Base, get_db
from app.database.models import TrendHistoryAttempt, TrendHistoryBucket, TrendSnapshotItem, TrendSnapshotRun
from app.routes import dashboard
from app.services.trend_history import (
    archive_snapshot_run, backfill_retained_history, load_trend_history, prune_trend_history,
)


class TrendHistoryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.now = datetime(2026, 9, 19, 12, 30)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def run_sample(self, at, items=(('video-a', 1, 'Gaming'),), platform='youtube',
                   scope='global', status='ok', mode='live', region='TH', views=None,
                   views_available=True, metric='youtube_play_start_view_v2'):
        provider = {'status': status, 'mode': mode}
        if scope != 'global':
            provider['categories'] = {scope.split(':')[1]: {'status': status}}
        run = TrendSnapshotRun(region=region,
            snapshot_kind='global' if scope == 'global' else 'youtube_categories',
            status='partial' if status == 'error' else 'completed',
            provider_status=json.dumps({platform: provider}), started_at=at, completed_at=at)
        run.items = [TrendSnapshotItem(platform=platform, ranking_scope=scope,
            trend_key=key, provider_rank=rank, title=key, category=category,
            source_platform=platform, views=(views or {}).get(key, 0),
            views_available=views_available if key in (views or {}) else False,
            view_metric_version=metric) for key, rank, category in items]
        self.db.add(run)
        self.db.flush()
        archive_snapshot_run(self.db, run)
        self.db.commit()
        return run

    def history(self, **kwargs):
        return load_trend_history(self.db, region='TH', platform='youtube', now=self.now, **kwargs)

    def test_hour_keeps_first_and_last_real_time_not_average_rank(self):
        self.run_sample(self.now - timedelta(minutes=20), (('a', 8, 'Gaming'),))
        self.run_sample(self.now - timedelta(minutes=10), (('a', 2, 'Gaming'),))
        self.run_sample(self.now, (('a', 4, 'Gaming'),))
        points = self.history()['points']
        self.assertEqual([p['ranks']['a'] for p in points], [8, 4])
        self.assertEqual(self.db.query(TrendHistoryBucket).count(), 1)
        self.assertTrue(points[0]['observed_at'].endswith('Z'))

    def test_backfill_idempotent_and_survives_deleting_raw_snapshots(self):
        run = self.run_sample(self.now)
        backfill_retained_history(self.db, now=self.now)
        backfill_retained_history(self.db, now=self.now)
        self.assertEqual(self.db.query(TrendHistoryBucket).count(), 1)
        self.db.delete(run)
        self.db.commit()
        self.assertEqual(self.history()['coverage']['sample_count'], 1)

    def test_regions_platforms_and_ranking_scopes_never_mix(self):
        self.run_sample(self.now, (('global', 3, 'Gaming'),))
        self.run_sample(self.now, (('category', 1, 'Gaming'),), scope='category:20')
        self.run_sample(self.now, (('search', 2, 'Search'),), platform='google')
        self.run_sample(self.now, (('foreign', 1, 'Gaming'),), region='US')
        self.assertEqual(self.history()['points'][0]['ranks'], {'global': 3})
        category = self.history(category_id='20')['points'][0]
        self.assertEqual(category['ranks'], {'category': 1})
        self.assertEqual(category['category_counts'], {})

    def test_provider_failure_or_mock_not_recorded_as_zero(self):
        self.run_sample(self.now - timedelta(minutes=20))
        self.run_sample(self.now, (), status='error')
        self.run_sample(self.now, (), mode='mock')
        self.assertEqual(self.history()['coverage']['sample_count'], 1)
        self.assertEqual(self.history()['points'][0]['total'], 1)

    def test_confirmed_empty_response_is_distinct_from_fetch_failure(self):
        self.run_sample(self.now - timedelta(minutes=20))
        self.run_sample(self.now, (), status='empty')
        points = self.history()['points']
        self.assertEqual(len(points), 2)
        self.assertEqual(points[-1]['ranks'], {})
        self.assertEqual(points[-1]['total'], 0)

    def test_failed_run_with_successful_provider_metadata_still_breaks_history(self):
        self.run_sample(self.now - timedelta(hours=1), views={'video-a': 100})
        at = self.now - timedelta(minutes=30)
        run = TrendSnapshotRun(region='TH', snapshot_kind='global', status='failed',
            started_at=at, completed_at=at,
            provider_status=json.dumps({'youtube': {'mode': 'live', 'status': 'ok'}}))
        self.db.add(run)
        archive_snapshot_run(self.db, run)
        self.db.commit()
        attempt = self.db.query(TrendHistoryAttempt).filter_by(run_id=run.run_id).one()
        self.assertEqual(attempt.status, 'failed')
        self.run_sample(self.now, views={'video-a': 200})
        history = self.history()
        self.assertEqual(history['coverage']['failed_attempts'], 1)
        self.assertEqual(len(history['points']), 2)
        self.assertTrue(history['points'][-1]['break_before'])
        self.assertEqual(history['points'][-1]['view_intervals']['video-a']['status'], 'collection_gap')

    def test_category_mock_is_excluded_even_with_live_parent_metadata(self):
        run = TrendSnapshotRun(region='TH', snapshot_kind='youtube_categories',
            status='completed', started_at=self.now, completed_at=self.now,
            provider_status=json.dumps({'youtube': {'mode': 'live', 'status': 'ok',
                'categories': {'20': {'status': 'ok', 'mode': 'mock'}}}}))
        self.db.add(run)
        archive_snapshot_run(self.db, run)
        self.db.commit()
        self.assertEqual(self.history(category_id='20')['points'], [])

    def test_missing_video_has_no_invented_rank_and_gap_is_marked(self):
        self.run_sample(self.now - timedelta(days=2))
        self.run_sample(self.now, (('different', 1, 'Music'),))
        data = self.history()
        self.assertTrue(data['points'][1]['break_before'])
        self.assertNotIn('video-a', data['points'][1]['ranks'])
        old = next(i for i in data['items'] if i['key'] == 'video-a')
        self.assertIsNone(old['latest_rank'])
        self.assertEqual(data['coverage']['gap_count'], 1)

    def test_top_fifty_actual_denominator_not_category_collection_limit(self):
        self.run_sample(self.now, (('a', 1, 'Gaming'), ('b', 2, 'Music'), ('c', 51, 'Gaming')))
        point = self.history()['points'][0]
        self.assertEqual(point['total'], 2)
        self.assertEqual(point['category_counts'], {'Gaming': 1, 'Music': 1})

    def test_window_includes_only_real_observation_times_not_bucket_start(self):
        self.run_sample(self.now - timedelta(days=1, minutes=1))
        self.run_sample(self.now - timedelta(hours=23))
        self.assertEqual(self.history(days=1)['coverage']['sample_count'], 1)
        self.assertTrue(self.history(days=1)['coverage']['is_stale'])

    def test_prune_removes_only_expired_archive(self):
        self.run_sample(self.now - timedelta(days=91))
        self.run_sample(self.now)
        prune_trend_history(self.db, now=self.now)
        self.db.commit()
        self.assertEqual(self.db.query(TrendHistoryBucket).count(), 1)
        self.assertEqual(self.db.query(TrendSnapshotRun).count(), 2)

    def test_empty_history_does_not_generate_points(self):
        data = self.history()
        self.assertEqual(data['points'], [])
        self.assertEqual(data['items'], [])
        self.assertTrue(data['coverage']['is_stale'])

    def test_seven_calendar_days_and_daily_coverage_keep_gaps_honest(self):
        self.run_sample(self.now - timedelta(days=2))
        self.run_sample(self.now, (), status='error')
        data = self.history(days=7)
        self.assertEqual(len(data['daily_coverage']), 7)
        self.assertEqual(sum(d['observed_hours'] for d in data['daily_coverage']), 1)
        self.assertEqual(data['daily_coverage'][-1]['failed_attempts'], 1)
        self.assertEqual(data['daily_coverage'][-1]['observed_hours'], 0)
        self.assertEqual(len(data['points']), 1)
        self.assertEqual(data['requested_from'], '2026-09-12T17:00:00Z')

    def test_default_selects_longer_history_but_explicit_item_wins(self):
        self.run_sample(self.now - timedelta(days=2), (('old', 4, 'Gaming'),))
        self.run_sample(self.now - timedelta(days=1), (('old', 3, 'Gaming'),))
        self.run_sample(self.now, (('new', 1, 'Gaming'), ('old', 2, 'Gaming')))
        data = self.history()
        self.assertEqual(data['selected_key'], 'old')
        self.assertEqual(data['items'][0]['key'], 'new')  # Rankings stay untouched.
        self.assertEqual(next(i for i in data['items'] if i['key'] == 'old')['observation_count'], 3)
        self.assertEqual(self.history(item_key='new')['selected_key'], 'new')

    def test_failure_survives_raw_prune_and_breaks_line_inside_one_hour(self):
        self.run_sample(self.now - timedelta(minutes=20))
        failed = self.run_sample(self.now - timedelta(minutes=10), (), status='error')
        self.run_sample(self.now)
        self.db.delete(failed)
        self.db.commit()
        data = self.history()
        self.assertEqual(data['coverage']['failed_attempts'], 1)
        self.assertTrue(data['points'][-1]['break_before'])
        hour = data['hours'][-1]
        self.assertEqual(hour['status'], 'partial')
        self.assertIsNone(self.db.query(TrendHistoryAttempt).filter_by(status='failed').one().sample_count)

    def test_long_term_archive_distinguishes_unobserved_from_failed(self):
        self.run_sample(self.now - timedelta(days=60))
        self.run_sample(self.now, (), status='error')
        data = self.history(days=90)
        self.assertEqual(data['coverage']['sample_count'], 1)
        self.assertTrue(any(h['status'] == 'no_observation' for h in data['hours']))
        self.assertEqual(data['hours'][-1]['status'], 'failed')
        self.assertFalse(data['hours'][-1]['observed'])

    def test_cleanup_archives_unarchived_run_before_deletion(self):
        from app.services.live_trend_snapshots import _cleanup_old_runs
        from app.core.config import settings
        run = self.run_sample(self.now)
        self.db.query(TrendHistoryBucket).delete()
        self.db.query(TrendHistoryAttempt).delete()
        self.db.commit()
        with patch.object(settings, 'live_trend_snapshot_retention_runs', 0):
            _cleanup_old_runs(self.db, region='TH', snapshot_kind='global')
        self.db.commit()
        self.assertEqual(self.db.query(TrendSnapshotRun).count(), 0)
        self.assertEqual(self.history()['points'][0]['run_id'], run.run_id)

    def test_google_does_not_expose_category_shares_or_add_search_volumes(self):
        self.run_sample(self.now, platform='google')
        data = load_trend_history(self.db, region='TH', platform='google', now=self.now)
        self.assertEqual(data['points'][0]['category_counts'], {})
        self.assertNotIn('search_volume', data['points'][0])

    def test_public_endpoint_and_invalid_parameters(self):
        app = FastAPI()
        app.include_router(dashboard.router)
        app.dependency_overrides[get_db] = lambda: MagicMock()
        with TestClient(app) as client:
            with patch('app.routes.dashboard.load_trend_history', return_value={'points': []}) as load:
                self.assertEqual(client.get('/dashboard/public/history?platform=youtube').status_code, 200)
                load.assert_called_once()
            for query in ['platform=tiktok', 'platform=youtube&days=91',
                          'platform=youtube&region=THH', 'platform=youtube&video_category_id=abc']:
                self.assertEqual(client.get(f'/dashboard/public/history?{query}').status_code, 422)
            self.assertEqual(client.get('/dashboard/public/history?platform=google&video_category_id=20').status_code, 400)
            self.assertEqual(client.get('/dashboard/public/history?platform=youtube&days=2').status_code, 400)

    def test_view_delta_actual_interval_rate_and_source_ids(self):
        first = self.run_sample(self.now - timedelta(minutes=30), views={'video-a': 1000})
        last = self.run_sample(self.now, views={'video-a': 1300})
        interval = self.history()['points'][-1]['view_intervals']['video-a']
        self.assertEqual(interval['status'], 'measured')
        self.assertEqual(interval['delta'], 300)
        self.assertEqual(interval['per_hour'], 600)
        self.assertEqual(interval['elapsed_seconds'], 1800)
        self.assertEqual(interval['from_views'], 1000)
        self.assertEqual(interval['to_views'], 1300)
        self.assertEqual(interval['from_run_id'], first.run_id)
        self.assertEqual(interval['to_item_id'], last.items[0].item_id)

    def test_growth_does_not_cross_failure_or_offline_gap(self):
        self.run_sample(self.now - timedelta(minutes=30), views={'video-a': 1000})
        self.run_sample(self.now - timedelta(minutes=10), (), status='error')
        self.run_sample(self.now, views={'video-a': 1300})
        self.assertEqual(self.history()['points'][-1]['view_intervals']['video-a']['status'], 'collection_gap')
        self.db.query(TrendHistoryAttempt).filter_by(status='failed').delete()
        self.db.commit()
        late = load_trend_history(self.db, region='TH', platform='youtube', now=self.now + timedelta(hours=3))
        self.assertTrue(late['coverage']['is_stale'])
        self.assertEqual(late['items'][0]['movement']['status'], 'stale')
        self.run_sample(self.now + timedelta(hours=3), views={'video-a': 1500})
        late = load_trend_history(self.db, region='TH', platform='youtube', now=self.now + timedelta(hours=3))
        self.assertIsNone(late['points'][-1]['view_intervals']['video-a']['delta'])

    def test_absence_and_reentry_do_not_imply_zero_views_or_rank_51(self):
        self.run_sample(self.now - timedelta(hours=2), views={'video-a': 1000})
        self.run_sample(self.now - timedelta(hours=1), (('other', 1, 'Gaming'),), views={'other': 100})
        data = load_trend_history(self.db, region='TH', platform='youtube', now=self.now - timedelta(hours=1))
        old = next(item for item in data['items'] if item['key'] == 'video-a')
        self.assertEqual(old['movement']['status'], 'not_in_latest')
        self.assertIsNone(old['movement']['current_rank'])
        self.run_sample(self.now, views={'video-a': 1300})
        data = self.history()
        self.assertEqual(data['points'][-1]['view_intervals']['video-a']['status'], 'not_in_both_samples')
        self.assertEqual(data['items'][0]['movement']['status'], 'new_entry')

    def test_unavailable_counts_metric_changes_and_counter_corrections_are_not_growth(self):
        self.run_sample(self.now - timedelta(minutes=30), views={'video-a': 1000})
        for kwargs, expected in [
            ({'views': {'video-a': 1100}, 'views_available': False}, 'missing_views'),
            ({'views': {'video-a': 1100}, 'views_available': None}, 'missing_views'),
            ({'views': {'video-a': 1100}, 'metric': 'unknown_v1'}, 'metric_changed'),
            ({'views': {'video-a': 1100}, 'metric': 'youtube_qualified_view_v1'}, 'metric_changed'),
            ({'views': {'video-a': 900}}, 'counter_decreased'),
        ]:
            with self.subTest(expected=expected, kwargs=kwargs):
                self.run_sample(self.now, **kwargs)
                interval = self.history()['points'][-1]['view_intervals']['video-a']
                self.assertEqual(interval['status'], expected)
                self.assertIsNone(interval['delta'])
                self.assertIsNone(interval['per_hour'])

    def test_real_zero_growth_is_preserved_and_category_counters_never_mix(self):
        self.run_sample(self.now - timedelta(minutes=30), views={'video-a': 0})
        self.run_sample(self.now, views={'video-a': 0})
        self.run_sample(self.now, scope='category:20', views={'video-a': 5000})
        interval = self.history()['points'][-1]['view_intervals']['video-a']
        self.assertEqual(interval['delta'], 0)
        self.assertEqual(interval['status'], 'measured')
        self.assertEqual(self.history(category_id='20')['points'][0]['views']['video-a'], 5000)

    def test_backfill_only_enriches_same_run_and_counters_survive_raw_deletion(self):
        run = self.run_sample(self.now, views={'video-a': 1234})
        bucket = self.db.query(TrendHistoryBucket).one()
        original = json.loads(bucket.first_sample)
        for item in original['items']:
            for field in ('views', 'view_metric_version', 'snapshot_item_id'):
                item.pop(field)
        bucket.first_sample = bucket.last_sample = json.dumps(original)
        self.db.commit()
        backfill_retained_history(self.db, now=self.now)
        self.assertEqual(self.history()['points'][0]['views']['video-a'], 1234)
        run.items[0].views = 9999
        self.db.commit()
        backfill_retained_history(self.db, now=self.now)
        self.assertEqual(self.history()['points'][0]['views']['video-a'], 1234)
        self.db.delete(run)
        self.db.commit()
        self.db.close()
        self.db = sessionmaker(bind=self.engine)()
        self.assertEqual(self.history()['points'][0]['views']['video-a'], 1234)

    def test_missing_archived_counters_stay_missing_when_raw_row_is_gone(self):
        run = self.run_sample(self.now)
        self.db.delete(run)
        self.db.commit()
        backfill_retained_history(self.db, now=self.now)
        self.assertEqual(self.history()['points'][0]['views'], {})

    def test_movements_and_latest_failure_do_not_claim_current_growth(self):
        self.run_sample(self.now - timedelta(minutes=30), (('a', 10, 'Gaming'),))
        self.run_sample(self.now, (('a', 4, 'Gaming'),))
        movement = self.history()['items'][0]['movement']
        self.assertEqual(movement['status'], 'up')
        self.assertEqual(movement['change'], 6)
        self.run_sample(self.now, (), status='error')
        self.assertTrue(self.history()['coverage']['latest_unavailable'])
        self.assertEqual(self.history()['items'][0]['movement']['status'], 'latest_unavailable')

    def test_boundary_bucket_without_in_window_observation_is_not_covered(self):
        self.run_sample(self.now - timedelta(days=1, minutes=1))
        data = self.history(days=1)
        self.assertEqual(data['coverage']['hours_observed'], 0)
        self.assertEqual(data['points'], [])

    def test_google_never_exposes_video_growth_even_with_a_counter_in_raw_input(self):
        self.run_sample(self.now, platform='google', views={'video-a': 9999})
        data = load_trend_history(self.db, region='TH', platform='google', now=self.now)
        self.assertEqual(data['points'][0]['views'], {})
        self.assertEqual(data['points'][0]['view_intervals'], {})

    def test_selected_item_only_counter_payload_preserves_all_rank_and_category_evidence(self):
        rows = (('a', 1, 'Gaming'), ('b', 2, 'Music'))
        self.run_sample(self.now - timedelta(minutes=30), rows, views={'a': 100, 'b': 200})
        self.run_sample(self.now, rows, views={'a': 110, 'b': 600})
        data = self.history(item_key='b')
        self.assertEqual(data['selected_key'], 'b')
        self.assertEqual(data['points'][-1]['views'], {'b': 600})
        self.assertEqual(data['points'][-1]['view_intervals']['b']['delta'], 400)
        self.assertEqual(data['points'][-1]['ranks'], {'a': 1, 'b': 2})
        self.assertEqual(data['points'][-1]['category_counts'], {'Gaming': 1, 'Music': 1})

    def test_mock_between_successes_also_breaks_a_line(self):
        self.run_sample(self.now - timedelta(minutes=30), views={'video-a': 100})
        self.run_sample(self.now - timedelta(minutes=15), (), mode='mock')
        self.run_sample(self.now, views={'video-a': 110})
        self.assertTrue(self.history()['points'][-1]['break_before'])
        self.assertEqual(self.history()['points'][-1]['view_intervals']['video-a']['status'], 'collection_gap')


if __name__ == '__main__':
    unittest.main()
