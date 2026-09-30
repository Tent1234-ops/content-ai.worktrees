import unittest
import hashlib
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy.orm import sessionmaker

from app.database.models import (DatasetContent, ReferenceStatisticsConfig, ReferenceStatisticsRun,
                                 ReferenceVideoStatistic)
from app.services.reference_statistics import (refresh_reference_statistics, statistics_settings,
    video_statistics_history, ReferenceStatisticsParameters, save_statistics_settings)
from app.services.youtube_cc_dataset import YouTubeQuotaExceededError
from tests import test_phase20_keyword_gap_evidence as fixtures


class ReferenceStatisticsTests(unittest.TestCase):
    setUp = fixtures.Phase20KeywordGapEvidenceTests.setUp
    tearDown = fixtures.Phase20KeywordGapEvidenceTests.tearDown
    _add_phone_rows = fixtures.Phase20KeywordGapEvidenceTests._add_phone_rows

    def refresh(self, at, **kwargs):
        self.db.expire_all()
        return refresh_reference_statistics(session_factory=sessionmaker(bind=self.engine),
            now=at, actor='test', force=True, **kwargs)

    def fetch(self, ids, views=1000):
        return {'items': [{'id': v, 'statistics': {'viewCount': str(views), 'likeCount': '50',
                                                  'commentCount': '10'}} for v in ids]}

    def row(self):
        self.db.expire_all()
        return self.db.query(DatasetContent).order_by(DatasetContent.dataset_id).first()

    def test_refresh_by_id_preserves_transcript_split_and_records_growth(self):
        at = datetime.utcnow() + timedelta(seconds=1)
        row = self.row()
        before = row.transcript, row.transcript_sha256, row.data_split, row.taxonomy_leaf_key
        self.assertEqual(self.refresh(at, fetch=self.fetch)['status'], 'completed')
        self.assertEqual(self.row().views, 1000)
        self.assertEqual((row.transcript, row.transcript_sha256, row.data_split, row.taxonomy_leaf_key), before)
        self.refresh(at + timedelta(hours=2), fetch=lambda ids: self.fetch(ids, 1600))
        history = video_statistics_history(self.db, row.dataset_id, now=at + timedelta(hours=2))
        self.assertEqual(len(history['points']), 2)
        self.assertEqual(history['latest']['growth']['views_delta'], 600)
        self.assertEqual(history['latest']['growth']['views_per_hour'], 300)
        self.assertEqual(history['latest']['growth']['elapsed_hours'], 2)
        self.assertTrue(history['latest']['source_url'].endswith(row.source_youtube_id))

    def test_missing_counts_are_null_not_zero_or_mixed_latest_bundle(self):
        row = self.row()
        before = row.views, row.likes, row.statistics_captured_at
        at = datetime.utcnow() + timedelta(seconds=1)
        self.refresh(at, fetch=lambda ids: {'items': [{'id': v, 'statistics': {'viewCount': '500'}} for v in ids]})
        history = video_statistics_history(self.db, row.dataset_id, now=at)
        self.assertIsNone(history['latest']['likes'])
        self.assertIsNone(history['latest']['comments'])
        self.assertFalse(history['has_growth'])
        self.assertEqual((self.row().views, row.likes, row.statistics_captured_at), before)

    def test_failed_call_persists_gap_and_does_not_erase_previous_counts(self):
        at = datetime.utcnow() + timedelta(seconds=1)
        self.refresh(at, fetch=self.fetch)
        def fail(_):
            raise TimeoutError('do not expose sensitive URL')
        result = self.refresh(at + timedelta(hours=1), fetch=fail)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['requests_used'], 1)
        self.refresh(at + timedelta(hours=2), fetch=self.fetch)
        history = video_statistics_history(self.db, self.row().dataset_id, now=at + timedelta(hours=2))
        self.assertIsNone(history['points'][1]['views'])
        self.assertIsNone(history['points'][1]['growth'].get('views_delta'))
        self.assertIsNone(history['points'][2]['growth'])
        self.assertEqual(self.row().views, 1000)

    def test_empty_provider_response_means_unavailable_not_zero(self):
        at = datetime.utcnow() + timedelta(seconds=1)
        self.refresh(at, fetch=lambda _: {'items': []})
        latest = video_statistics_history(self.db, self.row().dataset_id, now=at)['latest']
        self.assertEqual(latest['status'], 'unavailable')
        self.assertIsNone(latest['views'])

    def test_holdout_and_shared_channels_never_requested(self):
        holdout = self.row()
        holdout.data_split = 'test'
        self.db.commit()
        protected = {r.source_youtube_id for r in self.db.query(DatasetContent).filter_by(source_channel_id=holdout.source_channel_id)}
        ids = []
        def fetch(batch):
            ids.extend(batch)
            return self.fetch(batch)
        self.refresh(datetime.utcnow() + timedelta(seconds=1), fetch=fetch)
        self.assertFalse(protected.intersection(ids))
        self.assertTrue(ids)

    def test_daily_budget_and_interval_survive_new_sessions(self):
        at = datetime.utcnow() + timedelta(seconds=1)
        save_statistics_settings(self.db, ReferenceStatisticsParameters(enabled=True, interval_seconds=3600,
                                                                          daily_request_budget=1), user_id=None)
        self.refresh(at, fetch=self.fetch)
        with patch('app.services.reference_statistics._fetch') as fetch:
            self.assertEqual(self.refresh(at + timedelta(seconds=10))['status'], 'not_due')
            result = self.refresh(at + timedelta(minutes=2))
            self.assertEqual(result['error_code'], 'daily_budget')
            fetch.assert_not_called()
        self.assertEqual(statistics_settings(self.db, now=at)['requests_used_today'], 1)

    def test_quota_error_stops_calls_and_persists_cooldown(self):
        at = datetime.utcnow() + timedelta(seconds=1)
        def quota(_):
            raise YouTubeQuotaExceededError('videos', 403, 'quotaExceeded')
        self.refresh(at, fetch=quota)
        with patch('app.services.reference_statistics._fetch') as fetch:
            self.assertEqual(self.refresh(at + timedelta(hours=1))['status'], 'quota_wait')
            fetch.assert_not_called()

    def test_negative_counter_correction_is_not_negative_growth_rate(self):
        at = datetime.utcnow() + timedelta(seconds=1)
        self.refresh(at, fetch=self.fetch)
        self.refresh(at + timedelta(hours=1), fetch=lambda ids: self.fetch(ids, 800))
        latest = video_statistics_history(self.db, self.row().dataset_id, now=at + timedelta(hours=1))['latest']
        self.assertEqual(latest['growth']['views_delta'], -200)
        self.assertIsNone(latest['growth']['views_per_hour'])
        self.assertEqual(latest['growth']['status'], 'counter_correction')

    def test_metric_change_blocks_growth_and_big_counts_survive(self):
        at = datetime.utcnow() + timedelta(seconds=1)
        self.refresh(at, fetch=lambda ids: self.fetch(ids, 5000000000))
        self.refresh(at + timedelta(hours=1), fetch=lambda ids: self.fetch(ids, 5000000100))
        first = self.db.query(ReferenceVideoStatistic).filter_by(dataset_id=self.row().dataset_id).first()
        first.view_metric_version = 'unknown_v1'
        self.db.commit()
        latest = video_statistics_history(self.db, self.row().dataset_id, now=at + timedelta(hours=1))['latest']
        self.assertEqual(latest['views'], 5000000100)
        self.assertIsNone(latest['growth']['views_delta'])

    def test_malformed_response_is_not_successful_empty(self):
        at = datetime.utcnow() + timedelta(seconds=1)
        result = self.refresh(at, fetch=lambda _: {})
        self.assertEqual(result['error_code'], 'provider_error')
        self.assertEqual(result['status'], 'failed')

    def test_interrupted_attempt_is_not_retried_immediately(self):
        at = datetime.utcnow() + timedelta(seconds=1)
        self.db.add(ReferenceStatisticsRun(actor='test', status='running', started_at=at))
        self.db.commit()
        self.assertEqual(self.refresh(at + timedelta(minutes=1), fetch=self.fetch)['status'], 'busy')
        self.refresh(at + timedelta(minutes=20), fetch=self.fetch)
        self.db.expire_all()
        self.assertEqual(self.db.query(ReferenceStatisticsRun).first().status, 'interrupted')

    def test_batches_at_most_fifty_ids_and_small_budget_rotates(self):
        template = self.row()
        for i in range(25):
            values = {column.name: getattr(template, column.name) for column in DatasetContent.__table__.columns
                      if column.name != 'dataset_id'}
            video_id = f'newtest{i:04d}'
            values.update(source_youtube_id=video_id, source_record_id=video_id,
                          video_url=f'https://www.youtube.com/watch?v={video_id}',
                          transcript_sha256=hashlib.sha256(video_id.encode()).hexdigest())
            self.db.add(DatasetContent(**values))
        self.db.commit()
        save_statistics_settings(self.db, ReferenceStatisticsParameters(enabled=True, interval_seconds=3600,
                                                                        daily_request_budget=1), user_id=None)
        at = datetime.utcnow() + timedelta(seconds=1)
        requested = []
        def fetch(ids):
            requested.append(ids)
            return self.fetch(ids)
        self.refresh(at, fetch=fetch)
        self.assertEqual(len(requested), 1)
        self.assertEqual(len(requested[0]), 50)
        self.refresh(at + timedelta(days=1), fetch=fetch)
        self.assertEqual(len(requested), 2)
        self.assertEqual(len(set(requested[0] + requested[1])), 55)
        self.assertGreater(statistics_settings(self.db, now=at)['effective_interval_seconds'], 3600)
        self.assertEqual(statistics_settings(self.db, now=at)['estimated_requests_per_day'], 1)

    def test_scheduler_callback_runs_with_shared_worker_not_http_read(self):
        from app.services.trend_scheduler import collect_due
        from unittest.mock import Mock
        callback = Mock(return_value={'status': 'completed'})
        result = collect_due(session_factory=sessionmaker(bind=self.engine),
            global_fetch=Mock(), category_fetch=Mock(), reference_fetch=callback,
            actor='task_scheduler')
        callback.assert_called_once()
        self.assertEqual(result['reference_statistics']['status'], 'completed')


if __name__ == '__main__':
    unittest.main()
