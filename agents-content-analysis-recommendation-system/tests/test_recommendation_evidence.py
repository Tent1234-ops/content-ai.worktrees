import json
import unittest
from unittest.mock import patch

from sqlalchemy.orm import sessionmaker

from app.database.models import DatasetContent, User, UserContent
from app.services.contents import get_user_content_detail
from app.schemas.recommendation import RecommendationAnalysisResponse
from app.services.persistence import save_video_analysis_result
from app.services.recommendation import build_recommendation_from_analysis_data, build_recommendation_from_saved_content
from app.services.recommendation_evidence import (
    _observation, freeze_reference, locate_terms, text_hash, user_context, valid_segments,
)
from tests import test_phase20_keyword_gap_evidence as fixtures


class SourceSpanTests(unittest.TestCase):
    def test_overlapping_aliases_count_once_and_offsets_address_source(self):
        text = 'battery life, battery. Not a batteryless word.'
        hits = locate_terms(text, ['battery', 'battery life'])
        self.assertEqual([hit['matched_text'] for hit in hits], ['battery life', 'battery'])
        for hit in hits:
            self.assertEqual(text[hit['start_char']:hit['end_char']], hit['matched_text'])
            self.assertEqual(text[hit['quote_start_char']:hit['quote_end_char']], hit['quote'])
            self.assertIsNone(hit['timestamp'])

    def test_repeated_segments_keep_actual_times_not_estimated_word_times(self):
        segments = [{'text': 'camera', 'start': 4, 'end': 8},
                    {'text': 'camera', 'start': 61, 'duration': 3}]
        hits = locate_terms('camera camera', ['camera'], segments=segments)
        self.assertEqual([hit['timestamp']['start_seconds'] for hit in hits], [4, 61])
        self.assertEqual(hits[1]['timestamp']['precision'], 'segment')
        self.assertEqual(valid_segments([{'text': 'bad', 'start': True, 'end': 5}]), [])
        self.assertEqual(valid_segments([{'text': 'bad', 'start': float('nan'), 'end': 5}]), [])

    def test_hook_requires_real_aligned_times_and_does_not_guess_across_boundary(self):
        plain = user_context(transcript='camera')
        self.assertEqual(_observation(plain, ['camera'], hook=True)['status'], 'unassessable')
        for text, start, end in [('different words', 0, 20), ('camera', 55, 65)]:
            context = user_context(transcript='camera', segments=[{'text': text, 'start': start, 'end': end}],
                                   stt_meta={'hook_seconds_analyzed': 60})
            self.assertEqual(_observation(context, ['camera'], hook=True)['status'], 'unassessable')
        context = user_context(transcript='camera later battery', stt_meta={'hook_seconds_analyzed': 60},
                               segments=[{'text': 'camera', 'start': 2, 'end': 5},
                                         {'text': 'later battery', 'start': 65, 'end': 70}])
        self.assertEqual(_observation(context, ['camera'], hook=True)['status'], 'detected')
        self.assertEqual(_observation(context, ['battery'], hook=True)['status'], 'not_detected')

    def test_partial_transcript_can_prove_presence_but_not_absence(self):
        context = user_context(transcript='camera', stt_meta={'weak_audio': True})
        self.assertEqual(_observation(context, ['camera'])['status'], 'detected')
        self.assertEqual(_observation(context, ['battery'])['status'], 'unassessable')
        context = user_context(transcript='camera', stt_meta={'transcript_source': 'fallback_filename'})
        self.assertEqual(_observation(context, ['camera'])['status'], 'unassessable')


class EvidenceBundleTests(unittest.TestCase):
    setUp = fixtures.Phase20KeywordGapEvidenceTests.setUp
    tearDown = fixtures.Phase20KeywordGapEvidenceTests.tearDown
    _add_phone_rows = fixtures.Phase20KeywordGapEvidenceTests._add_phone_rows

    def build(self, transcript='camera photo', **kwargs):
        return build_recommendation_from_analysis_data(self.db, domain='phone', user_keywords=[],
            dimension_status=[], hook_terms=[], transcript=transcript, **kwargs)

    def test_all_supports_trace_back_to_frozen_rows_and_missing_has_real_evidence(self):
        for row in self.db.query(DatasetContent).all():
            row.transcript = '  \n' + row.transcript + '\n '
        self.db.commit()
        result = self.build()
        bundle = result['evidence_bundle']
        documents = {doc['dataset_id']: doc for doc in bundle['reference_documents']}
        topics = {topic['canonical_topic']: topic for topic in bundle['topics']}
        self.assertEqual(topics['camera quality']['user']['status'], 'detected')
        self.assertEqual(topics['battery life']['user']['status'], 'not_detected')
        self.assertNotIn('camera quality', [item['keyword'] for item in result['missing_keywords']])
        self.assertTrue(result['missing_keywords'])
        for topic in bundle['topics']:
            self.assertEqual(topic['support_count'], len(topic['references']))
            self.assertEqual(topic['channel_count'], len({documents[r['dataset_id']]['channel_id'] for r in topic['references']}))
            for support in topic['references']:
                doc = documents[support['dataset_id']]
                self.assertEqual(doc['transcript_sha256'], text_hash(doc['transcript']))
                for hit in support['occurrences']:
                    self.assertEqual(doc['transcript'][hit['start_char']:hit['end_char']], hit['matched_text'])
                    self.assertEqual(doc['transcript'][hit['quote_start_char']:hit['quote_end_char']], hit['quote'])
                    self.assertIsNone(hit['timestamp'])
        self.assertGreater(topics['battery life']['support_count'], 3)
        self.assertFalse(bundle['metadata_is_transcript'])
        serialized = RecommendationAnalysisResponse.model_validate(result).model_dump()
        self.assertEqual(serialized['evidence_bundle'], bundle)

    def test_reference_split_and_category_guards_remain_in_force(self):
        rows = self.db.query(DatasetContent).order_by(DatasetContent.dataset_id).all()
        rows[0].data_split = 'test'
        rows[1].data_split = 'validation'
        rows[2].taxonomy_leaf_key = 'camera'
        self.db.commit()
        # Isolate holdout selection from the independent minimum training-count gate.
        with patch('app.services.recommendation.ready_leaf_keys', return_value={'phone'}):
            bundle = self.build()['evidence_bundle']
        self.assertTrue(bundle['reference_documents'])
        heldout_channels = {rows[0].source_channel_id, rows[1].source_channel_id}
        for doc in bundle['reference_documents']:
            self.assertEqual(doc['taxonomy_leaf_key'], 'phone')
            self.assertEqual(doc['data_split'], 'train')
            self.assertNotIn(doc['channel_id'], heldout_channels)
        for comparison in bundle['topic_comparisons']['items']:
            for record in comparison['records']:
                self.assertEqual(record['taxonomy_leaf_key'], 'phone')
                self.assertEqual(record['data_split'], 'train')
                self.assertNotIn(record['channel_id'], heldout_channels)

    def test_real_reference_segments_survive_and_untimed_window_is_never_used(self):
        row = self.db.query(DatasetContent).first()
        row.transcript = 'camera battery'
        row.transcript_timestamps_available = True
        row.raw_metadata_json = json.dumps({'transcript_segments': [
            {'text': 'camera battery', 'start': 15, 'end': 22}]})
        doc = freeze_reference(row)
        hits = locate_terms(doc['transcript'], ['camera'], segments=doc['segments'])
        self.assertEqual(hits[0]['timestamp']['start_seconds'], 15)
        row.transcript_timestamps_available = False
        self.assertEqual(freeze_reference(row)['segments'], [])

    def test_failed_asr_does_not_create_missing_or_opening_suggestions(self):
        for transcript, meta in [('', {}), ('camera', {'transcript_source': 'fallback_filename'}),
                                 ('camera', {'weak_audio': True})]:
            result = self.build(transcript, evidence_context=user_context(transcript=transcript, stt_meta=meta))
            self.assertEqual(result['status'], 'withheld_input_unassessable')
            self.assertEqual(result['missing_keywords'], [])
            self.assertEqual(result['hook_keywords'], [])
            self.assertEqual(result['missing_dimensions'], [])
            self.assertEqual(result['current_trend_ideas']['ideas'], [])

    def test_statistic_omission_is_not_a_measured_zero(self):
        row = self.db.query(DatasetContent).first()
        row.raw_metadata_json = json.dumps({'statistics': {'viewCount': '900', 'likeCount': '0'}})
        row.views, row.likes, row.comments = 900, 0, 0
        stats = freeze_reference(row)['statistics']
        self.assertEqual(stats, {'views': 900, 'likes': 0, 'comments': None})

    def test_unknown_never_loads_wrong_category_reference(self):
        result = build_recommendation_from_analysis_data(self.db, domain='unknown', user_keywords=['dpi'],
                    dimension_status=[], hook_terms=[], transcript='mouse dpi')
        self.assertEqual(result['evidence_bundle']['reference_documents'], [])
        self.assertEqual(result['evidence_bundle']['recommendations'], [])

    def test_title_trend_is_separate_from_transcript_evidence(self):
        trend = {'status': 'ready', 'method_version': 'trend-v1', 'ideas': [
            {'topic': 'New Phone', 'source_type': 'youtube_title', 'snapshot_item_id': 34,
             'source_excerpt': 'Phone launch', 'captured_at': '2026-09-28T00:00:00Z'}]}
        with patch('app.services.current_trend_ideas.build_current_trend_ideas', return_value=trend):
            result = self.build()
        self.assertEqual(result['evidence_bundle']['current_trend_ideas'], trend)
        self.assertNotIn('New Phone', [t['canonical_topic'] for t in result['evidence_bundle']['topics']])

    def test_persistence_keeps_evidence_after_source_edits_and_enforces_owner(self):
        user = User(username='evidence-user', email='evidence@example.test', password_hash='fixture')
        self.db.add(user)
        self.db.commit()
        user_id = user.user_id
        result = self.build()
        saved = save_video_analysis_result(self.db, user=user, filename='fixture.mp4', file_path='fixture.mp4',
                    transcript='camera photo', analysis_payload={'analysis_settings': {'version': 'test'}},
                    nlp_result={'top_keywords': []}, recommendation_payload=result)
        self.db.query(DatasetContent).update({'transcript': 'source edited', 'views': 1})
        self.db.commit()
        self.db.close()
        self.db = sessionmaker(bind=self.engine)()
        reloaded = build_recommendation_from_saved_content(self.db, content_id=saved['content_id'], user_id=user_id)
        self.assertEqual(reloaded['evidence_bundle'], result['evidence_bundle'])
        self.assertIsNone(build_recommendation_from_saved_content(self.db, content_id=saved['content_id'], user_id=user_id + 1))

    def test_legacy_without_saved_recommendation_never_recomputes(self):
        user = User(username='legacy-user', email='legacy@example.test', password_hash='fixture')
        self.db.add(user)
        self.db.flush()
        content = UserContent(user_id=user.user_id, title='Legacy', transcript='camera photo')
        self.db.add(content)
        self.db.commit()
        with patch('app.services.recommendation.build_recommendation_from_text', side_effect=AssertionError('Never rebuild history')):
            detail = get_user_content_detail(self.db, user_id=user.user_id, content_id=content.content_id)
            result = build_recommendation_from_saved_content(self.db, user_id=user.user_id, content_id=content.content_id)
        self.assertEqual(detail['recommendation']['evidence_bundle']['origin'], 'historical_legacy_no_snapshot')
        self.assertEqual(result, detail['recommendation'])


if __name__ == '__main__':
    unittest.main()
