import json
import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ.setdefault('CONTENT_AI_SKIP_DB_BOOTSTRAP', '1')
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.db import Base
from app.database.models import TrendSnapshotItem, TrendSnapshotRun, User, UserContent
from app.services.contents import get_user_content_detail
from app.services.persistence import save_video_analysis_result
from app.services.current_trend_ideas import build_current_trend_ideas
from app.services.recommendation import build_recommendation_from_analysis_data, _find_profile
from app.schemas.recommendation import RecommendationAnalysisResponse


class CurrentTrendIdeasTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.now = datetime(2026, 9, 25, 14)
        self.transcript = 'ทดสอบมือถือ Infinix GT50 เรื่องแบตเตอรี่ การเล่นเกม และการระบายความร้อน'

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def source(self, title='iPhone 27 Pro ทดสอบแบตเตอรี่', *, platform='youtube', age_hours=1,
               published_days=1, scope='global', mode='live', status='ok', region='TH',
               description='', video_id='abcde123456', published=True):
        at = self.now - timedelta(hours=age_hours)
        provider = {'mode': mode, 'status': status}
        if scope != 'global':
            provider['categories'] = {scope.split(':')[1]: {'mode': mode, 'status': status}}
        run = TrendSnapshotRun(region=region, snapshot_kind='global' if scope == 'global' else 'youtube_categories',
            status='failed' if status == 'error' else 'completed', started_at=at, completed_at=at,
            provider_status=json.dumps({platform: provider}))
        self.db.add(run)
        self.db.flush()
        row = TrendSnapshotItem(run_id=run.run_id, platform=platform, source_platform=platform,
            ranking_scope=scope, provider_rank=1, trend_key=str(run.run_id), category='Technology', title=title,
            description=description, video_url=f'https://youtu.be/{video_id}' if platform == 'youtube' else
            'https://trends.google.com/trending?geo=TH',
            published_at=(self.now - timedelta(days=published_days)).isoformat() if published else None)
        self.db.add(row)
        self.db.commit()
        return row

    def ideas(self, **kwargs):
        return build_current_trend_ideas(self.db, transcript=kwargs.pop('transcript', self.transcript),
            domain=kwargs.pop('domain', 'phone'), now=self.now, region='TH', **kwargs)

    def test_new_untrained_product_is_found_from_current_title_with_exact_proof(self):
        row = self.source()
        result = self.ideas()
        self.assertEqual(result['status'], 'ready')
        idea = result['items'][0]
        self.assertEqual(idea['topic'], 'iPhone 27 Pro')
        self.assertEqual(idea['related_aspects'], ['แบตเตอรี่'])
        source = idea['sources'][0]
        self.assertEqual(source['snapshot_item_id'], row.item_id)
        self.assertFalse(source['is_transcript_evidence'])
        span = source['topic_span']
        self.assertEqual(source['evidence_text'][span['start']:span['end']], span['text'])
        for part in idea['user_evidence']:
            self.assertEqual(self.transcript[part['start']:part['end']], part['text'])

    def test_stale_snapshot_is_not_current_even_if_video_date_is_new(self):
        self.source(age_hours=25)
        self.assertEqual(self.ideas()['status'], 'no_recent_sources')

    def test_old_video_in_fresh_snapshot_is_not_called_latest(self):
        self.source(published_days=8)
        self.assertEqual(self.ideas()['items'], [])

    def test_missing_and_future_publication_dates_abstain(self):
        self.source(published=False)
        self.assertEqual(self.ideas()['items'], [])
        self.source(published_days=-1, age_hours=0)
        self.assertEqual(self.ideas()['items'], [])

    def test_latest_failed_attempt_does_not_resurrect_old_success(self):
        self.source(age_hours=3)
        self.source(status='error', age_hours=1)
        self.assertEqual(self.ideas()['items'], [])

    def test_mock_empty_and_future_observations_are_not_sources(self):
        for kwargs in ({'mode': 'mock'}, {'status': 'empty'}, {'age_hours': -1}):
            self.source(**kwargs)
            self.assertEqual(self.ideas()['items'], [])

    def test_relevant_description_is_used_as_metadata_not_speech(self):
        self.source(title='ทดสอบมือถือรุ่นใหม่ แบตเตอรี่', description='ลอง iPhone 27 Pro เทียบกับรุ่นเดิม เรื่องแบตเตอรี่')
        item = self.ideas()['items'][0]['sources'][0]
        self.assertEqual(item['evidence_field'], 'description')
        self.assertFalse(item['is_transcript_evidence'])
        for span in item['related_evidence']:
            text = item['metadata_fields'][span['field']]
            self.assertEqual(text[span['start']:span['end']], span['text'])

    def test_music_title_with_phone_ad_description_is_not_phone_idea(self):
        self.source(title='เพลงใหม่วันนี้', description='iPhone 27 Pro แบตเตอรี่ลดราคา')
        self.assertEqual(self.ideas()['items'], [])

    def test_aspect_about_another_device_in_a_later_paragraph_is_not_transferred(self):
        self.source(title='iPhone 27 Pro ราคาสูง',
            description='iPhone 27 Pro มีราคาสูงมาก\n\nอีกเรื่องคือสมาร์ทโฟนจอพับของแบรนด์อื่น')
        self.assertEqual(self.ideas(transcript='ทดสอบมือถือ Infinix GT50 Pro เรื่องหน้าจอ AMOLED')['items'], [])

    def test_relevant_laptop_and_camera_products_have_their_own_evidence(self):
        for domain, title, transcript in [
            ('laptop', 'MacBook Pro M8 แบตเตอรี่', 'รีวิวโน้ตบุ๊ก ThinkPad X1 ทดสอบแบตเตอรี่ว่าใช้งานได้นานไหม'),
            ('camera', 'Canon EOS R9 ระบบกันสั่น', 'รีวิวกล้อง Sony A7 IV และทดสอบระบบกันสั่นในการถ่ายวิดีโอ'),
        ]:
            with self.subTest(domain=domain):
                self.source(title=title, age_hours=0)
                result = self.ideas(domain=domain, transcript=transcript)
                self.assertEqual(result['status'], 'ready')
                self.assertIn(result['items'][0]['topic'], title)

    def test_promotional_footer_not_mined_for_products(self):
        self.source(title='ทดสอบมือถือและแบตเตอรี่', description='รายละเอียด https://shop.test iPhone 27 Pro')
        self.assertEqual(self.ideas()['items'], [])

    def test_recent_google_query_uses_query_evidence_and_older_query_is_filtered(self):
        self.source(title='Galaxy S28 Ultra', platform='google')
        user = 'ผมกำลังรีวิว Samsung Galaxy S25 Ultra และทดสอบแบตเตอรี่ของมือถือรุ่นนี้'
        result = self.ideas(transcript=user)
        self.assertEqual(result['items'][0]['sources'][0]['evidence_field'], 'query')
        self.assertEqual(result['items'][0]['relationship'], 'same_product_family')
        self.source(title='Galaxy S29 Ultra', platform='google', published_days=3, age_hours=0)
        self.assertEqual(self.ideas(transcript=user)['items'], [])

    def test_phone_camera_does_not_leak_into_camera_category(self):
        self.source(title='iPhone 27 Pro ทดสอบกล้องและกันสั่น')
        result = self.ideas(domain='camera', transcript='รีวิวกล้อง Canon EOS R8 ทดสอบการถ่ายภาพ เซนเซอร์และระบบกันสั่น')
        self.assertEqual(result['items'], [])

    def test_laptop_does_not_use_phone_gaming_or_accessories(self):
        self.source(title='iPhone 27 Pro เล่นเกม แบตเตอรี่')
        result = self.ideas(domain='laptop', transcript='รีวิว MacBook Pro M6 แบตเตอรี่ในการเล่นเกมและพกพา')
        self.assertEqual(result['items'], [])
        self.source(title='เมาส์ iPhone 27 Pro DPI gaming', age_hours=0)
        self.assertEqual(self.ideas()['items'], [])

    def test_category_alone_is_not_enough_to_recommend(self):
        self.source(title='iPhone 27 Pro หน้าจอ OLED')
        self.assertEqual(self.ideas(transcript='รีวิวมือถือพร้อมทดสอบแบตเตอรี่ว่าใช้งานได้นานเพียงใด')['items'], [])

    def test_display_does_not_match_preorder_word_and_thai_adjacent_product_is_preserved(self):
        self.source(title='เปิดจอง iPhone 27 Pro')
        self.assertEqual(self.ideas(transcript='ทดสอบมือถือรุ่นนี้ว่าแสดงสีบนหน้าจอ AMOLED ได้ดีไหม')['items'], [])
        self.source(title='รีวิวiPhone27Proเรื่องแบตเตอรี่', age_hours=0)
        self.assertEqual(self.ideas()['items'][0]['topic'], 'iPhone27Pro')

    def test_unknown_category_and_empty_speech_do_not_query_sources(self):
        with patch('app.services.current_trend_ideas._latest_sources', side_effect=AssertionError('should abstain')):
            self.assertEqual(self.ideas(domain='unknown')['status'], 'unsupported_category')
            self.assertEqual(self.ideas(transcript='')['status'], 'insufficient_user_evidence')

    def test_product_already_spoken_is_not_suggested_again(self):
        self.source(title='Samsung Galaxy S28 Ultra แบตเตอรี่')
        self.assertEqual(self.ideas(transcript='รีวิว Galaxy S28 Ultra เรื่องแบตเตอรี่และการเล่นเกม')['items'], [])

    def test_scopes_deduplicate_the_same_video_but_keep_platform_provenance(self):
        self.source(title='Galaxy S28 Ultra แบตเตอรี่')
        self.source(title='Galaxy S28 Ultra แบตเตอรี่', scope='category:28')
        self.source(title='Galaxy S28 Ultra', platform='google')
        user = 'รีวิว Galaxy S25 Ultra เรื่องแบตเตอรี่และการเล่นเกมของมือถือ'
        idea = self.ideas(transcript=user)['items'][0]
        self.assertEqual(idea['support_count'], 2)
        self.assertEqual({source['platform'] for source in idea['sources']}, {'youtube', 'google'})

    def test_other_regions_and_invalid_source_links_are_excluded(self):
        self.source(region='US')
        self.assertEqual(self.ideas()['items'], [])
        self.source(video_id='not-valid')
        self.assertEqual(self.ideas()['items'], [])

    def test_recommendation_contract_keeps_live_ideas_out_of_keyword_gap(self):
        self.source()
        with patch('app.services.recommendation.build_dataset_profile_for_domain', return_value=_find_profile([], 'phone')), \
                patch('app.services.current_trend_ideas.build_current_trend_ideas',
                      side_effect=lambda db, **kwargs: build_current_trend_ideas(db, now=self.now, **kwargs)):
            result = build_recommendation_from_analysis_data(self.db, domain='phone',
                transcript=self.transcript, user_keywords=['battery life'], dimension_status=[], hook_terms=[])
        parsed = RecommendationAnalysisResponse.model_validate(result)
        self.assertEqual(parsed.missing_keywords, [])
        self.assertEqual(parsed.hook_keywords, [])
        self.assertEqual(parsed.current_trend_ideas['source_type'], 'live_metadata_not_transcript')
        self.assertEqual(parsed.current_trend_ideas['status'], 'ready')

    def test_saved_result_keeps_provenance_after_reopening_session(self):
        self.source()
        ideas = self.ideas()
        user = User(username='trend-test', email='trend-test@example.test', password_hash='test', role='user')
        self.db.add(user)
        self.db.commit()
        user_id = user.user_id
        saved = save_video_analysis_result(self.db, user=user, filename='1.mp4', file_path='1.mp4',
            transcript=self.transcript, analysis_payload={}, nlp_result={},
            recommendation_payload={'domain': 'phone', 'current_trend_ideas': ideas})
        self.db.close()
        self.db = sessionmaker(bind=self.engine)()
        with patch('app.services.current_trend_ideas.build_current_trend_ideas', side_effect=AssertionError('no recompute')):
            detail = get_user_content_detail(self.db, user_id=user_id, content_id=saved['content_id'])
        self.assertEqual(detail['recommendation']['current_trend_ideas'], ideas)

    def test_legacy_content_without_transcript_does_not_recompute_from_title(self):
        user = User(username='legacy-test', email='legacy@example.test', password_hash='test', role='user')
        self.db.add(user)
        self.db.flush()
        content = UserContent(user_id=user.user_id, title='iPhone 27 Pro battery review', transcript=None)
        self.db.add(content)
        self.db.commit()
        detail = get_user_content_detail(
            self.db, user_id=user.user_id, content_id=content.content_id
        )
        recommendation = detail['recommendation']
        self.assertEqual(recommendation['user_keywords'], [])
        self.assertNotIn('current_trend_ideas', recommendation)
        self.assertEqual(
            recommendation['evidence_bundle']['origin'],
            'historical_legacy_no_snapshot',
        )
        self.assertNotIn('iPhone', json.dumps(recommendation, ensure_ascii=False))

    def test_database_failure_does_not_break_reference_recommendation(self):
        from sqlalchemy.exc import OperationalError
        with patch('app.services.current_trend_ideas._latest_sources',
                   side_effect=OperationalError('SELECT', {}, RuntimeError('offline'))):
            self.assertEqual(self.ideas()['status'], 'unavailable')


if __name__ == '__main__':
    unittest.main()
