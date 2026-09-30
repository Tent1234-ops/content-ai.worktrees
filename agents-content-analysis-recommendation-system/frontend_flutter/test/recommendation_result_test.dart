import 'package:content_ai_web/models/recommendation_result.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('keyword gap keeps traceable dataset evidence', () {
    final result = RecommendationResult.fromJson({
      'domain': 'phone',
      'user_keywords': ['camera quality'],
      'missing_keywords': [
        {
          'keyword': 'battery life',
          'score': 0.82,
          'support_count': 9,
          'sample_size': 12,
          'support_ratio': 0.75,
          'total_frequency': 31,
          'supporting_dataset_row_ids': [101, 104, 109],
          'supporting_examples': [
            {
              'dataset_id': 101,
              'source_record_id': 'youtube-id-101',
              'title': 'Phone battery endurance review',
              'video_url': 'https://www.youtube.com/watch?v=youtube-id-101',
              'platform': 'youtube',
              'frequency': 6,
            },
          ],
        },
      ],
      'hook_keywords': [],
      'missing_dimensions': [],
      'recommended_duration': {
        'recommended_seconds': 75,
        'recommended_range': '60-90 sec',
        'sample_size': 12,
        'source': 'youtube_metadata',
        'evidence_status': 'sufficient',
        'minimum_sample_size': 10,
        'target_sample_size': 15,
        'cohort': 'upload_compatible_under_5m',
        'median_seconds': 75,
        'percentile_low_seconds': 60,
        'percentile_high_seconds': 90,
      },
      'dataset_profile': {
        'domain': 'phone',
        'sample_size': 12,
        'source': 'youtube_public_human_verified',
        'source_platform_counts': {'youtube': 12},
        'exemplar_titles': [],
      },
      'evidence': {},
    });

    final keyword = result.missingKeywords.single;
    expect(keyword.keyword, 'battery life');
    expect(keyword.supportCount, 9);
    expect(keyword.sampleSize, 12);
    expect(keyword.totalFrequency, 31);
    expect(keyword.supportingDatasetRowIds, [101, 104, 109]);
    expect(keyword.supportingExamples.single.datasetId, 101);
    expect(
      keyword.supportingExamples.single.title,
      'Phone battery endurance review',
    );
    expect(keyword.hasDatasetEvidence, isTrue);
    expect(result.duration.hasSufficientEvidence, isTrue);
    expect(result.duration.medianSeconds, 75);
    expect(result.duration.percentileLowSeconds, 60);
    expect(result.duration.percentileHighSeconds, 90);
  });

  test('duration parser preserves insufficient evidence without a number', () {
    final duration = DurationRecommendation.fromJson({
      'recommended_seconds': null,
      'recommended_range': 'Insufficient evidence',
      'sample_size': 7,
      'source': 'youtube_metadata',
      'evidence_status': 'insufficient_evidence',
      'minimum_sample_size': 10,
      'target_sample_size': 15,
      'cohort': 'upload_compatible_under_5m',
    });

    expect(duration.hasSufficientEvidence, isFalse);
    expect(duration.recommendedSeconds, isNull);
    expect(duration.medianSeconds, isNull);
    expect(duration.recommendedRange, 'Insufficient evidence');
    expect(duration.sampleSize, 7);
    expect(duration.minimumSampleSize, 10);
  });
}
