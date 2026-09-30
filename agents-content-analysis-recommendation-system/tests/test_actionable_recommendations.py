import copy
import json
import unittest
from unittest.mock import patch

from app.services.actionable_recommendations import build_actionable_recommendations, template_catalog
from app.services.recommendation_evidence import fingerprint, text_hash, user_context
from app.schemas.recommendation import RecommendationAnalysisResponse
from app.database.models import DatasetContent
from tests import test_recommendation_evidence as evidence_fixtures


def fixture_result(domain='phone', transcript='รีวิวมือถือ แบตเตอรี่อึด เหมาะกับการเดินทาง', *, reference_text=None):
    templates = template_catalog()['categories'][domain]
    reference_text = reference_text or '. '.join(t['aliases'][0] for t in templates)
    docs = [{
        'dataset_id': i, 'video_id': f'fixture-{i}', 'channel_id': f'channel-{i}',
        'title': f'TEST FIXTURE {i}', 'url': f'https://youtu.be/fixture-{i}',
        'source_type': 'dataset_transcript', 'taxonomy_leaf_key': domain, 'data_split': 'train',
        'transcript': reference_text, 'transcript_sha256': text_hash(reference_text),
        'segments': [], 'published_at': '2026-08-01T00:00:00Z',
        'statistics_captured_at': '2026-09-01T00:00:00Z', 'statistics': {'views': 1000, 'likes': 20, 'comments': 2},
    } for i in range(1, 5)]
    return {'domain': domain, 'dataset_profile': {'dataset_row_ids': [1, 2, 3, 4]},
            'evidence_bundle': {'input': user_context(transcript=transcript), 'reference_documents': docs,
                                'data_fingerprint': fingerprint(docs), 'topics': []}}


class ActionableAdviceTests(unittest.TestCase):
    def test_each_category_has_thai_actionable_advice_and_traceable_quotes(self):
        for domain, transcript in [('phone', 'รีวิวมือถือ แบตเตอรี่อึด เหมาะกับการเดินทาง'),
                                   ('camera', 'รีวิวกล้อง โฟกัสได้ไว เหมาะสำหรับถ่ายภาพท่องเที่ยว'),
                                   ('laptop', 'รีวิวโน้ตบุ๊ก ซีพียูสำหรับทำงานตัดต่อ')]:
            with self.subTest(domain=domain):
                result = fixture_result(domain, transcript)
                advice = build_actionable_recommendations(result)
                self.assertEqual(advice['status'], 'ready')
                self.assertGreaterEqual(len(advice['items']), 2)
                self.assertLessEqual(len(advice['items']), 3)
                topics = {t['topic_id']: t for t in result['evidence_bundle']['action_topics']}
                docs = {d['dataset_id']: d for d in result['evidence_bundle']['reference_documents']}
                for item in advice['items']:
                    for field in ('finding', 'proposal', 'condition', 'example', 'reason', 'title'):
                        self.assertRegex(item[field], '[ก-๙]')
                    self.assertTrue(item['steps'])
                    self.assertFalse(item['causal_engagement_claim'])
                    self.assertEqual(item['product_verification'], 'unverified_use_condition')
                    self.assertEqual(item['example_status'], 'suggested_script_not_observed_result')
                    topic = topics[item['evidence_topic_id']]
                    self.assertEqual(topic['user']['status'], 'not_detected')
                    self.assertEqual(item['support_count'], len(topic['references']))
                    for ref in topic['references']:
                        for hit in ref['occurrences']:
                            text = docs[ref['dataset_id']]['transcript']
                            self.assertEqual(text[hit['quote_start_char']:hit['quote_end_char']], hit['quote'])
                            self.assertIsNone(hit['timestamp'])

    def test_synonyms_negations_and_late_mentions_are_never_suggested_again(self):
        snippets = [('phone', 'Dimensity ใช้งานได้ทั้งวัน ชาร์จไว ไม่มีโหมดกลางคืน หน้าจอไม่สว่าง เครื่องร้อน'),
                    ('camera', 'โฟกัสไม่ได้ ไม่มีระบบกันสั่น ถ่ายกลางคืนมีนอยส์ เมนูไม่สะดวก คุณภาพภาพไม่ดี ถ่ายวิดีโอไม่ได้'),
                    ('laptop', 'ซีพียูช้า เครื่องร้อน แบตหมดเร็ว หน้าจอมืด ไม่มีพอร์ตนี้ เพิ่มแรมไม่ได้ ทัชแพดไม่ถนัด')]
        for domain, spoken in snippets:
            with self.subTest(domain=domain):
                text = 'รีวิว ' + ('เล่าเรื่องทั่วไป ' * 500) + spoken
                result = fixture_result(domain, text)
                output = build_actionable_recommendations(result)
                self.assertEqual(output['items'], [])
                self.assertEqual(output['status'], 'all_topics_detected')

    def test_unknown_incomplete_audio_or_failed_acceptance_withholds(self):
        for change in ('unknown', 'failed', 'partial', 'rejected'):
            result = fixture_result()
            if change == 'unknown':
                result['domain'] = 'unknown'
            elif change == 'rejected':
                result['evidence_bundle']['input']['classification'] = {'acceptance': {'accepted': False}}
            else:
                result['evidence_bundle']['input']['availability'] = 'partial' if change == 'partial' else 'unavailable'
            advice = build_actionable_recommendations(result)
            self.assertEqual(advice['items'], [])
            self.assertTrue(advice['status'].startswith('withheld_'))

    def test_no_relevance_or_title_only_evidence_does_not_force_advice(self):
        result = fixture_result(transcript='ไม่คิดว่าจะเจอสิ่งนี้ วันนี้ไปกันเลย')
        self.assertEqual(build_actionable_recommendations(result)['status'], 'insufficient_user_context')
        result = fixture_result(reference_text='เพียงแค่ทักทายผู้ชม')
        result['evidence_bundle']['current_trend_ideas'] = {'ideas': [{'title': 'ชาร์จไว'}]}
        for doc in result['evidence_bundle']['reference_documents']:
            doc['title'] = 'ชาร์จไว ความร้อน จอ'
        self.assertEqual(build_actionable_recommendations(result)['items'], [])

    def test_evidence_requires_distinct_videos_and_channels_and_correct_cohort(self):
        for modification in ('one_channel', 'duplicate_video', 'test', 'wrong_category', 'duration_only', 'hash_changed'):
            result = fixture_result()
            for doc in result['evidence_bundle']['reference_documents']:
                if modification == 'one_channel': doc['channel_id'] = 'same'
                if modification == 'duplicate_video': doc['video_id'] = 'same'
                if modification == 'test': doc['data_split'] = 'test'
                if modification == 'wrong_category': doc['taxonomy_leaf_key'] = 'camera'
                if modification == 'duration_only': doc['dataset_id'] += 100
                if modification == 'hash_changed': doc['transcript'] += 'changed'
            with self.subTest(modification=modification):
                self.assertEqual(build_actionable_recommendations(result)['items'], [])

    def test_rank_is_explainable_display_limit_does_not_limit_assessment(self):
        result = fixture_result(transcript='รีวิวมือถือ ชิป Snapdragon ใช้เล่นเกม')
        output = build_actionable_recommendations(result)
        self.assertEqual(len(output['items']), 3)
        self.assertGreater(output['eligible_count'], 3)
        self.assertEqual(output['assessed_topic_count'], len(template_catalog()['categories']['phone']))
        self.assertEqual(len(output['assessments']), output['assessed_topic_count'])
        ranks = [(i['ranking']['relevance_level'], i['ranking']['support_ratio'],
                  i['ranking']['channel_count'], i['ranking']['mean_log_frequency']) for i in output['items']]
        self.assertEqual(ranks, sorted(ranks, reverse=True))
        self.assertEqual(output, build_actionable_recommendations(copy.deepcopy(result)))

    def test_charging_example_proposes_measurement_without_inventing_results(self):
        result = fixture_result(reference_text='การชาร์จเร็ว charging และแบตเตอรี่')
        output = build_actionable_recommendations(result)
        self.assertEqual(len(output['items']), 1)
        item = output['items'][0]
        self.assertEqual(item['title'], 'ความเร็วในการชาร์จ')
        self.assertIn('ตรวจคู่มือ', item['condition'])
        self.assertIn('จับเวลา', item['example'])
        self.assertNotRegex(item['example'], r'\d')
        self.assertNotIn('พูดคำนี้บ่อย', json.dumps(item, ensure_ascii=False))


class ActionableAdviceIntegrationTests(unittest.TestCase):
    setUp = evidence_fixtures.EvidenceBundleTests.setUp
    tearDown = evidence_fixtures.EvidenceBundleTests.tearDown
    _add_phone_rows = evidence_fixtures.EvidenceBundleTests._add_phone_rows
    build = evidence_fixtures.EvidenceBundleTests.build

    def test_api_and_saved_result_preserve_templates_and_evidence(self):
        from app.database.models import User
        from app.services.persistence import save_video_analysis_result
        from app.services.recommendation import build_recommendation_from_saved_content
        result = self.build('รีวิวมือถือ แบตเตอรี่อึด เหมาะกับการเดินทาง')
        self.assertEqual(result['actionable_recommendations']['status'], 'ready')
        serialized = RecommendationAnalysisResponse.model_validate(result).model_dump()
        self.assertEqual(serialized['actionable_recommendations'], result['actionable_recommendations'])
        user = User(username='advice-user', email='advice@example.test', password_hash='fixture')
        self.db.add(user)
        self.db.commit()
        saved = save_video_analysis_result(self.db, user=user, filename='fixture.mp4', file_path='fixture.mp4',
            transcript='รีวิวมือถือ แบตเตอรี่อึด', analysis_payload={}, nlp_result={}, recommendation_payload=result)
        self.db.query(DatasetContent).update({'transcript': 'changed later'})
        self.db.commit()
        self.db.expire_all()
        with patch('app.services.actionable_recommendations.template_catalog', side_effect=AssertionError('Do not re-render old advice')):
            reloaded = build_recommendation_from_saved_content(self.db, content_id=saved['content_id'], user_id=user.user_id)
        self.assertEqual(reloaded['actionable_recommendations'], result['actionable_recommendations'])
        self.assertEqual(reloaded['evidence_bundle']['action_topics'], result['evidence_bundle']['action_topics'])


if __name__ == '__main__':
    unittest.main()
