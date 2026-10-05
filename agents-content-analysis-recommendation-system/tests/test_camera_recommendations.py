import unittest
from unittest.mock import patch

from app.database.models import DatasetContent
from app.services.actionable_recommendations import build_actionable_recommendations
from app.services.nlp import extract_comparable_keyword_candidates
from app.services.recommendation import build_recommendation_from_analysis_data, _should_recommend_keyword
from app.services.recommendation_evidence import text_hash, user_context
from tests.test_actionable_recommendations import fixture_result
from tests import test_phase20_keyword_gap_evidence as fixtures


class CameraVocabularyTests(unittest.TestCase):
    def test_camera_variants_are_observed_not_suggested_again(self):
        for focus in ('auto focus', 'auto-focus', 'autofocus'):
            transcript = f'sensor full frame {focus} ถ่ายภาพและวีดีโอ'
            candidates = extract_comparable_keyword_candidates(transcript, 'camera')
            self.assertEqual({c['keyword'] for c in candidates}, {'image quality', 'autofocus', 'video recording'})
            result = fixture_result('camera', transcript)
            output = build_actionable_recommendations(result)
            decisions = {a['template_key']: a['decision'] for a in output['assessments']}
            self.assertEqual(decisions['autofocus'], 'already_detected')
            self.assertEqual(decisions['video recording'], 'already_detected')
            self.assertIn('low light', {a['template_key'] for a in output['items']})

    def test_camera_rejects_filler_but_keeps_supported_concepts(self):
        for word in ('ผม', 'ดู', 'อ่ะ', 'ถ่าย', 'today', 'subscribe'):
            self.assertFalse(_should_recommend_keyword(word, 'camera'))
        for word in ('low light', 'autofocus', 'image quality', 'video recording'):
            self.assertTrue(_should_recommend_keyword(word, 'camera'))

    def test_variant_evidence_uses_original_text_and_real_segment_time(self):
        transcript = 'sensor auto focus และวีดีโอ'
        result = fixture_result('camera', transcript)
        result['evidence_bundle']['input'] = user_context(
            transcript=transcript, segments=[{'text': transcript, 'start': 1, 'end': 8}],
            stt_meta={'hook_seconds_analyzed': 60})
        build_actionable_recommendations(result)
        topics = {t['canonical_topic']: t for t in result['evidence_bundle']['action_topics']}
        for key, term in [('autofocus', 'auto focus'), ('video recording', 'วีดีโอ')]:
            observation = topics[key]['user']
            self.assertEqual(observation['status'], 'detected')
            hit = observation['occurrences'][0]
            self.assertEqual(transcript[hit['start_char']:hit['end_char']], term)
            self.assertEqual(hit['timestamp']['start_seconds'], 1)
            self.assertEqual(hit['timestamp']['precision'], 'segment')


class CameraEvidenceIntegrationTests(unittest.TestCase):
    setUp = fixtures.Phase20KeywordGapEvidenceTests.setUp
    tearDown = fixtures.Phase20KeywordGapEvidenceTests.tearDown
    _add_phone_rows = fixtures.Phase20KeywordGapEvidenceTests._add_phone_rows

    def test_camera_profile_uses_canonical_evidence_and_excludes_spoken_topics(self):
        for row in self.db.query(DatasetContent).all():
            row.taxonomy_leaf_key = 'camera'
            row.category = 'camera'
            row.category_level_3 = 'Camera'
            row.transcript = f'sensor auto focus วีดีโอ แสงน้อย นอยส์ เมนู ผม ดู อ่ะ ถ่าย sample {row.dataset_id}'
            row.transcript_sha256 = text_hash(row.transcript)
        self.db.commit()
        with patch('app.services.recommendation.ready_leaf_keys', return_value={'camera'}):
            result = build_recommendation_from_analysis_data(
                self.db, domain='camera', user_keywords=[], dimension_status=[], hook_terms=[],
                transcript='sensor auto focus ถ่ายภาพและวีดีโอ')
        gaps = {item['keyword'] for item in result['missing_keywords']}
        self.assertIn('low light', gaps)
        self.assertTrue(gaps.isdisjoint({'ผม', 'ดู', 'อ่ะ', 'ถ่าย', 'autofocus', 'video recording', 'image quality'}))
        self.assertTrue(result['hook_keywords'])
        for item in result['missing_keywords']:
            self.assertTrue(item['supporting_dataset_row_ids'])
            self.assertGreater(item['support_count'], 0)
        self.assertEqual(result['evidence_bundle']['canonicalization'], 'curated_synonyms')
        self.assertEqual(result['actionable_recommendations']['status'], 'ready')
