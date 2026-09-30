import json
import unittest
from datetime import datetime, timedelta

from app.database.models import DatasetContent, TrendSnapshotRun, TrendSnapshotItem
from app.schemas.admin_report import AdminDatasetUpdate
from app.schemas.recommendation import RecommendationAnalysisResponse
from app.services.admin_report import update_admin_dataset
from app.services.dataset_eligibility import production_transcript_query, reference_transcript_rows, validate_training_eligibility_values
from app.services.dataset_readiness import dataset_readiness
from app.services.recommendation import build_dataset_profile_for_domain, build_recommendation_from_analysis_data
from tests import test_phase20_keyword_gap_evidence as fixtures


class DatasetReadinessTests(unittest.TestCase):
    setUp = fixtures.Phase20KeywordGapEvidenceTests.setUp
    tearDown = fixtures.Phase20KeywordGapEvidenceTests.tearDown
    _add_phone_rows = fixtures.Phase20KeywordGapEvidenceTests._add_phone_rows

    def rows(self):
        return self.db.query(DatasetContent).order_by(DatasetContent.dataset_id).all()

    def test_test_and_validation_clips_and_channels_never_enter_keyword_or_duration_evidence(self):
        rows = self.rows()
        rows[0].data_split = 'test'
        rows[1].data_split = 'validation'
        rows[0].trend_score = rows[1].trend_score = 999999
        for row in rows:
            row.raw_metadata_json = json.dumps({'contentDetails': {'duration': 'PT180S'}})
        self.db.commit()
        protected_channels = {rows[0].source_channel_id, rows[1].source_channel_id}
        blocked_ids = {r.dataset_id for r in rows if r.source_channel_id in protected_channels}
        profile = build_dataset_profile_for_domain(self.db, domain='phone')
        self.assertTrue(profile['dataset_row_ids'])
        self.assertFalse(blocked_ids.intersection(profile['dataset_row_ids']))
        self.assertFalse(blocked_ids.intersection(profile['duration_dataset_row_ids']))
        for keyword in profile['top_keywords']:
            self.assertFalse(blocked_ids.intersection(keyword['supporting_dataset_row_ids']))
        self.assertTrue(profile['reference_period']['statistics_from'])
        for record in profile['reference_records']:
            self.assertEqual(record['data_split'], 'train')
            self.assertTrue(record['published_at'])
            self.assertTrue(record['statistics_captured_at'])

    def test_archiving_or_disabling_holdout_does_not_release_channel(self):
        rows = self.rows()
        rows[0].data_split = 'test'
        rows[0].is_training_eligible = False
        rows[0].deleted_at = datetime.utcnow()
        self.db.commit()
        self.assertNotIn(rows[0].source_channel_id, {r.source_channel_id for r in reference_transcript_rows(self.db)})

    def test_reference_requires_source_and_valid_observation_period(self):
        rows = self.rows()
        rows[0].published_at = None
        rows[1].statistics_captured_at = datetime.utcnow() + timedelta(days=1)
        rows[2].statistics_captured_at = rows[2].published_at - timedelta(days=1)
        rows[3].video_url = 'https://www.youtube.com/watch?v=other000001'
        rows[4].video_url = 'https://example.org/watch?v=' + rows[4].source_youtube_id
        self.db.commit()
        eligible = {r.dataset_id for r in reference_transcript_rows(self.db)}
        self.assertFalse(eligible.intersection(r.dataset_id for r in rows[:5]))
        self.assertIn(rows[5].dataset_id, eligible)

    def test_classification_and_reference_permissions_are_independent(self):
        rows = self.rows()
        rows[0].is_keyword_recommendation_eligible = False
        rows[0].is_duration_recommendation_eligible = False
        rows[1].is_training_eligible = False
        self.db.commit()
        validate_training_eligibility_values(rows[0])
        self.assertIn(rows[0].dataset_id, {r.dataset_id for r in production_transcript_query(self.db)})
        self.assertNotIn(rows[0].dataset_id, {r.dataset_id for r in reference_transcript_rows(self.db)})
        self.assertIn(rows[1].dataset_id, {r.dataset_id for r in reference_transcript_rows(self.db)})

    def test_assigned_split_cannot_be_changed_by_admin_editor(self):
        row = self.rows()[0]
        row.data_split = 'test'
        self.db.commit()
        with self.assertRaisesRegex(ValueError, 'split is locked'):
            update_admin_dataset(self.db, dataset_id=row.dataset_id, payload=AdminDatasetUpdate(data_split='train'))
        self.assertEqual(row.data_split, 'test')

    def test_audit_roles_and_collection_plan_are_observed_not_assumed(self):
        row = self.rows()[0]
        row.data_split = 'test'
        self.db.commit()
        report = dataset_readiness(self.db, category='phone', limit=100)
        holdout = next(item for item in report['items'] if item['dataset_id'] == row.dataset_id)
        self.assertIn('evaluation', holdout['roles'])
        self.assertNotIn('reference', holdout['roles'])
        self.assertTrue(holdout['reference_blockers'])
        plan = next(p for p in report['plans'] if p['category'] == 'phone')
        self.assertEqual(plan['classification_count'], 30)
        self.assertEqual(plan['channels'], 8)
        self.assertEqual(plan['topic_comparison']['eligible_video_count'], 26)
        self.assertTrue(plan['topic_comparison']['topics'])
        self.assertEqual(plan['topic_comparison']['policy_version'], 'topic-comparison-policy-v2')
        self.assertTrue(plan['actions'])
        self.assertEqual(report['summary']['current_trend'], 0)
        self.assertEqual(report['policy']['reference_splits'], ['train'])
        self.assertFalse(report['policy']['causal_claim'])

    def snapshot(self, *, when, mode='live', present=True):
        row = self.rows()[0]
        run = TrendSnapshotRun(region='TH', snapshot_kind='global', status='completed',
            started_at=when, completed_at=when, provider_status=json.dumps({'youtube': {'mode': mode, 'status': 'ok'}}))
        self.db.add(run)
        self.db.flush()
        if present:
            self.db.add(TrendSnapshotItem(run_id=run.run_id, platform='youtube', ranking_scope='global',
                provider_rank=1, trend_key='a'*40, title=row.title, category='phone',
                source_platform='youtube_live', video_url=row.video_url))
        self.db.commit()
        return run

    def test_current_trend_requires_latest_live_snapshot_and_timestamp(self):
        now = datetime.utcnow()
        self.snapshot(when=now - timedelta(hours=1))
        report = dataset_readiness(self.db, now=now, role='current_trend')
        self.assertEqual(report['total'], 1)
        self.assertEqual(report['items'][0]['trend_evidence'][0]['rank'], 1)
        self.snapshot(when=now, present=False)
        self.assertEqual(dataset_readiness(self.db, now=now, role='current_trend')['total'], 0)

    def test_stale_and_mock_trends_never_become_current(self):
        now = datetime.utcnow()
        self.snapshot(when=now - timedelta(days=2))
        self.assertEqual(dataset_readiness(self.db, now=now)['summary']['current_trend'], 0)
        self.snapshot(when=now, mode='mock')
        self.assertEqual(dataset_readiness(self.db, now=now)['summary']['current_trend'], 0)

    def test_filters_pagination_and_missing_fields(self):
        row = self.rows()[0]
        row.published_at = None
        self.db.commit()
        report = dataset_readiness(self.db, category='phone', role='needs_attention')
        self.assertEqual(report['total'], 1)
        self.assertIn('published_at', {c['key'] for c in report['items'][0]['checks'] if not c['ok']})
        first = dataset_readiness(self.db, limit=10)
        second = dataset_readiness(self.db, limit=10, offset=10)
        self.assertFalse({i['dataset_id'] for i in first['items']} & {i['dataset_id'] for i in second['items']})
        self.assertEqual(dataset_readiness(self.db, category='laptop')['total'], 0)

    def test_serialized_recommendation_preserves_dates_and_row_provenance(self):
        result = build_recommendation_from_analysis_data(self.db, domain='phone',
            user_keywords=[], dimension_status=[], hook_terms=[], source_prefix='youtube',
            transcript='รีวิวมือถือและการใช้งานทั่วไป')
        result = RecommendationAnalysisResponse.model_validate(result).model_dump()
        self.assertTrue(result['evidence']['reference_records'])
        example = result['missing_keywords'][0]['supporting_examples'][0]
        self.assertTrue(example['statistics_captured_at'])
        self.assertTrue(example['published_at'])
        self.assertEqual(example['data_split'], 'train')

    def test_trend_archive_is_not_reported_as_broken_training_data(self):
        row = DatasetContent(title='Search topic', dataset_source='legacy', dataset_version='legacy-v1',
            source_platform='google_live', statistics_captured_at=datetime.utcnow())
        self.db.add(row)
        self.db.commit()
        report = dataset_readiness(self.db, role='trend_archive')
        self.assertEqual(report['total'], 1)
        self.assertEqual(report['items'][0]['issues'], [])
        self.assertNotIn('reference', report['items'][0]['roles'])


if __name__ == '__main__':
    unittest.main()
