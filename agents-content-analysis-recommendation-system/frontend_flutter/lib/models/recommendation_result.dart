import 'common_models.dart';
import 'current_trend_ideas.dart';
import 'actionable_recommendations.dart';
import 'outcome_prediction.dart';

class DurationRecommendation {
  const DurationRecommendation({
    required this.recommendedSeconds,
    required this.recommendedRange,
    required this.sampleSize,
    required this.source,
    required this.evidenceStatus,
    required this.minimumSampleSize,
    required this.targetSampleSize,
    required this.cohort,
    required this.medianSeconds,
    required this.percentileLow,
    required this.percentileHigh,
    required this.percentileLowSeconds,
    required this.percentileHighSeconds,
  });

  final int? recommendedSeconds;
  final String recommendedRange;
  final int sampleSize;
  final String source;
  final String evidenceStatus;
  final int minimumSampleSize;
  final int targetSampleSize;
  final String cohort;
  final int? medianSeconds;
  final int percentileLow;
  final int percentileHigh;
  final int? percentileLowSeconds;
  final int? percentileHighSeconds;

  bool get hasSufficientEvidence => evidenceStatus == 'sufficient';

  factory DurationRecommendation.fromJson(Map<String, dynamic> json) {
    final sampleSize = (json['sample_size'] as num?)?.toInt() ?? 0;
    final minimumSampleSize =
        (json['minimum_sample_size'] as num?)?.toInt() ?? 10;
    final recommendedRange =
        json['recommended_range']?.toString() ?? 'Insufficient evidence';
    final evidenceStatus = json['evidence_status']?.toString() ??
        (sampleSize >= minimumSampleSize &&
                recommendedRange != 'Insufficient evidence'
            ? 'sufficient'
            : 'insufficient_evidence');
    return DurationRecommendation(
      recommendedSeconds: (json['recommended_seconds'] as num?)?.toInt(),
      recommendedRange: recommendedRange,
      sampleSize: sampleSize,
      source: json['source']?.toString() ?? 'none',
      evidenceStatus: evidenceStatus,
      minimumSampleSize: minimumSampleSize,
      targetSampleSize: (json['target_sample_size'] as num?)?.toInt() ?? 15,
      cohort: json['cohort']?.toString() ?? 'upload_compatible_under_5m',
      medianSeconds: (json['median_seconds'] as num?)?.toInt() ??
          (json['recommended_seconds'] as num?)?.toInt(),
      percentileLow: (json['percentile_low'] as num?)?.toInt() ?? 25,
      percentileHigh: (json['percentile_high'] as num?)?.toInt() ?? 75,
      percentileLowSeconds: (json['percentile_low_seconds'] as num?)?.toInt(),
      percentileHighSeconds: (json['percentile_high_seconds'] as num?)?.toInt(),
    );
  }
}

class ClassificationCandidate {
  const ClassificationCandidate({
    required this.domain,
    required this.score,
    required this.sampleSize,
    required this.matchedTerms,
  });

  final String domain;
  final double score;
  final int sampleSize;
  final List<String> matchedTerms;

  factory ClassificationCandidate.fromJson(Map<String, dynamic> json) {
    return ClassificationCandidate(
      domain: json['domain']?.toString() ?? '-',
      score: (json['score'] as num?)?.toDouble() ?? 0,
      sampleSize: (json['sample_size'] as num?)?.toInt() ?? 0,
      matchedTerms: (json['matched_terms'] as List<dynamic>? ?? const [])
          .map((item) => item.toString())
          .toList(),
    );
  }
}

class ClassificationResult {
  const ClassificationResult({
    required this.domain,
    required this.confidence,
    required this.ruleDomain,
    required this.source,
    required this.candidates,
    required this.taxonomyVersion,
    required this.taxonomyLeafKey,
    required this.categoryLevel1,
    required this.categoryLevel2,
    required this.categoryLevel3,
    required this.isUnknown,
    required this.taxonomyReady,
    required this.warning,
    this.rawTaxonomyLeafKey = '',
    this.acceptanceReason = '',
  });

  final String domain;
  final double confidence;
  final String ruleDomain;
  final String source;
  final List<ClassificationCandidate> candidates;
  final String taxonomyVersion;
  final String taxonomyLeafKey;
  final String categoryLevel1;
  final String categoryLevel2;
  final String categoryLevel3;
  final bool isUnknown;
  final bool taxonomyReady;
  final String warning;
  final String rawTaxonomyLeafKey;
  final String acceptanceReason;

  String get displayCategory {
    if (isUnknown) return 'Unknown/Other';
    final levels = <String>[
      categoryLevel1,
      categoryLevel2,
      categoryLevel3,
    ].where((value) => value.trim().isNotEmpty).toList();
    return levels.isEmpty ? domain : levels.join(' > ');
  }

  factory ClassificationResult.fromJson(Map<String, dynamic> json) {
    return ClassificationResult(
      domain: json['domain']?.toString() ?? '-',
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0,
      ruleDomain: json['rule_domain']?.toString() ?? '-',
      source: json['source']?.toString() ?? 'youtube',
      taxonomyVersion: json['taxonomy_version']?.toString() ?? 'legacy-v1',
      taxonomyLeafKey: json['taxonomy_leaf_key']?.toString() ?? 'unknown',
      categoryLevel1: json['category_level_1']?.toString() ?? '',
      categoryLevel2: json['category_level_2']?.toString() ?? '',
      categoryLevel3: json['category_level_3']?.toString() ?? '',
      isUnknown: json['is_unknown'] == true,
      taxonomyReady: json['taxonomy_ready'] == true,
      warning: json['warning']?.toString() ?? '',
      rawTaxonomyLeafKey: json['raw_taxonomy_leaf_key']?.toString() ?? '',
      acceptanceReason: json['acceptance'] is Map
          ? (json['acceptance'] as Map)['reason']?.toString() ?? ''
          : '',
      candidates: (json['candidates'] as List<dynamic>? ?? const [])
          .map((item) => ClassificationCandidate.fromJson(
              Map<String, dynamic>.from(item as Map)))
          .toList(),
    );
  }
}

class MissingDimension {
  const MissingDimension({
    required this.name,
    required this.score,
    required this.userStatus,
  });

  final String name;
  final double score;
  final String userStatus;

  factory MissingDimension.fromJson(Map<String, dynamic> json) {
    return MissingDimension(
      name: json['name']?.toString() ?? '-',
      score: (json['score'] as num?)?.toDouble() ?? 0,
      userStatus: json['user_status']?.toString() ?? '-',
    );
  }
}

class RecommendationResult {
  const RecommendationResult({
    required this.domain,
    required this.userKeywords,
    required this.contentKeywords,
    required this.comparableKeywords,
    required this.hookTerms,
    required this.missingKeywords,
    required this.hookKeywords,
    required this.missingDimensions,
    required this.duration,
    required this.datasetProfile,
    required this.evidence,
    this.classification,
    this.currentTrendIdeas = const CurrentTrendIdeas(),
    this.evidenceBundle = const {},
    this.actionableRecommendations,
  });

  final String domain;
  final List<String> userKeywords;
  final List<String> contentKeywords;
  final List<String> comparableKeywords;
  final List<String> hookTerms;
  final List<KeywordScore> missingKeywords;
  final List<KeywordScore> hookKeywords;
  final List<MissingDimension> missingDimensions;
  final DurationRecommendation duration;
  final DatasetProfile datasetProfile;
  final RecommendationEvidence evidence;
  final ClassificationResult? classification;
  final CurrentTrendIdeas currentTrendIdeas;
  final Map<String, dynamic> evidenceBundle;
  final ActionableRecommendations? actionableRecommendations;

  factory RecommendationResult.fromJson(Map<String, dynamic> json) {
    return RecommendationResult(
      domain: json['domain']?.toString() ?? '-',
      userKeywords: (json['user_keywords'] as List<dynamic>? ?? const [])
          .map((item) => item.toString())
          .toList(),
      contentKeywords: (json['content_keywords'] as List<dynamic>? ?? const [])
          .map((item) => item.toString())
          .toList(),
      comparableKeywords:
          (json['comparable_keywords'] as List<dynamic>? ?? const [])
              .map((item) => item.toString())
              .toList(),
      hookTerms: (json['hook_terms'] as List<dynamic>? ?? const [])
          .map((item) => item.toString())
          .toList(),
      missingKeywords: (json['missing_keywords'] as List<dynamic>? ?? const [])
          .map((item) =>
              KeywordScore.fromJson(Map<String, dynamic>.from(item as Map)))
          .toList(),
      hookKeywords: (json['hook_keywords'] as List<dynamic>? ?? const [])
          .map((item) =>
              KeywordScore.fromJson(Map<String, dynamic>.from(item as Map)))
          .toList(),
      missingDimensions: (json['missing_dimensions'] as List<dynamic>? ??
              const [])
          .map((item) =>
              MissingDimension.fromJson(Map<String, dynamic>.from(item as Map)))
          .toList(),
      duration: DurationRecommendation.fromJson(
        Map<String, dynamic>.from(
            (json['recommended_duration'] as Map?) ?? const {}),
      ),
      datasetProfile: DatasetProfile.fromJson(
        Map<String, dynamic>.from(
            (json['dataset_profile'] as Map?) ?? const {}),
      ),
      evidence: RecommendationEvidence.fromJson(
        Map<String, dynamic>.from((json['evidence'] as Map?) ?? const {}),
      ),
      currentTrendIdeas: CurrentTrendIdeas.fromJson(Map<String, dynamic>.from(
          (json['current_trend_ideas'] as Map?) ?? const {})),
      evidenceBundle: Map<String, dynamic>.from(
          (json['evidence_bundle'] as Map?) ?? const {}),
      actionableRecommendations: json['actionable_recommendations'] is Map &&
              (json['actionable_recommendations'] as Map).isNotEmpty
          ? ActionableRecommendations.fromJson(Map<String, dynamic>.from(
              json['actionable_recommendations'] as Map))
          : null,
      classification: json['classification'] is Map
          ? ClassificationResult.fromJson(
              Map<String, dynamic>.from(json['classification'] as Map),
            )
          : null,
    );
  }
}

class AnalysisResultViewData {
  const AnalysisResultViewData({
    this.contentId,
    required this.title,
    required this.transcript,
    required this.recommendation,
    required this.fallbackDomain,
    required this.saved,
    required this.raw,
    required this.outcomeAssessment,
    required this.outcomeAssessmentFingerprint,
    this.rawTranscript = '',
    this.cleanedTranscript = '',
  });

  final int? contentId;
  final String title;
  final String transcript;
  final RecommendationResult recommendation;
  final String fallbackDomain;
  final bool saved;
  final Map<String, dynamic> raw;
  final OutcomeAssessment outcomeAssessment;
  final String outcomeAssessmentFingerprint;
  final String rawTranscript;
  final String cleanedTranscript;

  Map<String, dynamic> get analysisSettings {
    final root = raw['analysis'] as Map? ?? const {};
    return Map<String, dynamic>.from(raw['analysis_settings'] as Map? ??
        root['analysis_settings'] as Map? ??
        const {});
  }

  factory AnalysisResultViewData.fromJson(Map<String, dynamic> json) {
    final analysisRoot =
        Map<String, dynamic>.from((json['analysis'] as Map?) ?? const {});
    final analysis = Map<String, dynamic>.from(
        (analysisRoot['analysis'] as Map?) ?? const {});
    final legacyTranscript = json['transcript']?.toString() ??
        analysisRoot['transcript']?.toString() ??
        '';
    final rawTranscript = json['raw_transcript']?.toString() ??
        analysisRoot['raw_transcript']?.toString() ??
        legacyTranscript;
    final cleanedTranscript = json['cleaned_transcript']?.toString() ??
        analysisRoot['cleaned_transcript']?.toString() ??
        legacyTranscript;
    final recommendationJson =
        Map<String, dynamic>.from((json['recommendation'] as Map?) ?? const {});
    final outcomeJson = json['outcome_assessment'] is Map
        ? json['outcome_assessment']
        : recommendationJson['outcome_assessment'];
    return AnalysisResultViewData(
      contentId: (json['content_id'] as num?)?.toInt(),
      title: json['title']?.toString() ??
          analysis['title']?.toString() ??
          'Result',
      transcript:
          cleanedTranscript.isNotEmpty ? cleanedTranscript : rawTranscript,
      rawTranscript: rawTranscript,
      cleanedTranscript: cleanedTranscript,
      recommendation: RecommendationResult.fromJson(
        recommendationJson,
      ),
      fallbackDomain: analysis['domain']?.toString() ?? '-',
      saved: json['saved'] == true || json['content_id'] != null,
      raw: json,
      outcomeAssessment: OutcomeAssessment.fromJson(outcomeJson),
      outcomeAssessmentFingerprint:
          json['outcome_assessment_fingerprint']?.toString() ?? '',
    );
  }
}

class DatasetProfile {
  const DatasetProfile({
    required this.domain,
    required this.sampleSize,
    required this.source,
    required this.sourcePlatformCounts,
    required this.exemplarTitles,
  });

  final String domain;
  final int sampleSize;
  final String source;
  final Map<String, int> sourcePlatformCounts;
  final List<String> exemplarTitles;

  factory DatasetProfile.fromJson(Map<String, dynamic> json) {
    final rawCounts = json['source_platform_counts'];
    return DatasetProfile(
      domain: json['domain']?.toString() ?? '-',
      sampleSize: (json['sample_size'] as num?)?.toInt() ?? 0,
      source: json['source']?.toString() ?? '-',
      sourcePlatformCounts: rawCounts is Map
          ? rawCounts.map(
              (key, value) =>
                  MapEntry(key.toString(), (value as num?)?.toInt() ?? 0),
            )
          : const {},
      exemplarTitles: (json['exemplar_titles'] as List<dynamic>? ?? const [])
          .map((item) => item.toString())
          .toList(),
    );
  }
}

class RecommendationEvidence {
  const RecommendationEvidence({
    required this.source,
    required this.datasetSources,
    required this.datasetVersions,
    required this.sourceRecordIds,
    required this.dataSourceLabel,
    required this.datasetSampleSize,
    required this.eligiblePoolSize,
    required this.viewMetricVersion,
    required this.viewMetricCohortSize,
    required this.excludedIncompatibleViewMetricRows,
    required this.sourcePlatformCounts,
    required this.transcriptSourceCounts,
    required this.languageCounts,
    required this.selectionRule,
    required this.licenseName,
    required this.verificationStatus,
    required this.durationSource,
    required this.durationEvidenceStatus,
    required this.durationSampleSize,
    required this.durationMinimumSampleSize,
    required this.durationTargetSampleSize,
    required this.durationCohort,
    required this.durationSamples,
    required this.durationDatasetRowIds,
    required this.durationSourceRecordIds,
    required this.durationExemplarTitles,
    required this.durationSelectionRule,
    required this.exemplarTitles,
    required this.keywordScoreExplanation,
    required this.durationExplanation,
    required this.transcriptSource,
    required this.transcriptScope,
    this.warning,
    this.hookSecondsAnalyzed,
    this.sttFallbackReason,
  });

  final String source;
  final List<String> datasetSources;
  final List<String> datasetVersions;
  final List<String> sourceRecordIds;
  final String dataSourceLabel;
  final int datasetSampleSize;
  final int eligiblePoolSize;
  final String viewMetricVersion;
  final int viewMetricCohortSize;
  final int excludedIncompatibleViewMetricRows;
  final Map<String, int> sourcePlatformCounts;
  final Map<String, int> transcriptSourceCounts;
  final Map<String, int> languageCounts;
  final String selectionRule;
  final String licenseName;
  final String verificationStatus;
  final String durationSource;
  final String durationEvidenceStatus;
  final int durationSampleSize;
  final int durationMinimumSampleSize;
  final int durationTargetSampleSize;
  final String durationCohort;
  final List<int> durationSamples;
  final List<int> durationDatasetRowIds;
  final List<String> durationSourceRecordIds;
  final List<String> durationExemplarTitles;
  final String durationSelectionRule;
  final List<String> exemplarTitles;
  final String keywordScoreExplanation;
  final String durationExplanation;
  final String transcriptSource;
  final String transcriptScope;
  final String? warning;
  final int? hookSecondsAnalyzed;
  final String? sttFallbackReason;

  factory RecommendationEvidence.fromJson(Map<String, dynamic> json) {
    final rawCounts = json['source_platform_counts'];
    final rawTranscriptCounts = json['transcript_source_counts'];
    final rawLanguageCounts = json['language_counts'];
    return RecommendationEvidence(
      source: json['source']?.toString() ?? '-',
      datasetSources: (json['dataset_sources'] as List<dynamic>? ?? const [])
          .map((item) => item.toString())
          .toList(),
      datasetVersions: (json['dataset_versions'] as List<dynamic>? ?? const [])
          .map((item) => item.toString())
          .toList(),
      sourceRecordIds: (json['source_record_ids'] as List<dynamic>? ?? const [])
          .map((item) => item.toString())
          .toList(),
      dataSourceLabel: json['data_source_label']?.toString() ?? '-',
      datasetSampleSize: (json['dataset_sample_size'] as num?)?.toInt() ?? 0,
      eligiblePoolSize: (json['eligible_pool_size'] as num?)?.toInt() ??
          (json['dataset_sample_size'] as num?)?.toInt() ??
          0,
      viewMetricVersion: json['view_metric_version']?.toString() ?? '',
      viewMetricCohortSize:
          (json['view_metric_cohort_size'] as num?)?.toInt() ?? 0,
      excludedIncompatibleViewMetricRows:
          (json['excluded_incompatible_view_metric_rows'] as num?)?.toInt() ??
              0,
      sourcePlatformCounts: rawCounts is Map
          ? rawCounts.map(
              (key, value) =>
                  MapEntry(key.toString(), (value as num?)?.toInt() ?? 0),
            )
          : const {},
      transcriptSourceCounts: rawTranscriptCounts is Map
          ? rawTranscriptCounts.map(
              (key, value) =>
                  MapEntry(key.toString(), (value as num?)?.toInt() ?? 0),
            )
          : const {},
      languageCounts: rawLanguageCounts is Map
          ? rawLanguageCounts.map(
              (key, value) =>
                  MapEntry(key.toString(), (value as num?)?.toInt() ?? 0),
            )
          : const {},
      selectionRule: json['selection_rule']?.toString() ?? 'none',
      licenseName: json['license_name']?.toString() ?? '',
      verificationStatus: json['verification_status']?.toString() ?? '',
      durationSource: json['duration_source']?.toString() ?? '-',
      durationEvidenceStatus: json['duration_evidence_status']?.toString() ??
          'insufficient_evidence',
      durationSampleSize: (json['duration_sample_size'] as num?)?.toInt() ?? 0,
      durationMinimumSampleSize:
          (json['duration_minimum_sample_size'] as num?)?.toInt() ?? 10,
      durationTargetSampleSize:
          (json['duration_target_sample_size'] as num?)?.toInt() ?? 15,
      durationCohort:
          json['duration_cohort']?.toString() ?? 'upload_compatible_under_5m',
      durationSamples: (json['duration_samples'] as List<dynamic>? ?? const [])
          .whereType<num>()
          .map((item) => item.toInt())
          .toList(),
      durationDatasetRowIds:
          (json['duration_dataset_row_ids'] as List<dynamic>? ?? const [])
              .whereType<num>()
              .map((item) => item.toInt())
              .toList(),
      durationSourceRecordIds:
          (json['duration_source_record_ids'] as List<dynamic>? ?? const [])
              .map((item) => item.toString())
              .toList(),
      durationExemplarTitles:
          (json['duration_exemplar_titles'] as List<dynamic>? ?? const [])
              .map((item) => item.toString())
              .toList(),
      durationSelectionRule:
          json['duration_selection_rule']?.toString() ?? 'none',
      exemplarTitles: (json['exemplar_titles'] as List<dynamic>? ?? const [])
          .map((item) => item.toString())
          .toList(),
      keywordScoreExplanation:
          json['keyword_score_explanation']?.toString() ?? '',
      durationExplanation: json['duration_explanation']?.toString() ?? '',
      transcriptSource: json['transcript_source']?.toString() ?? 'unknown',
      transcriptScope: json['transcript_scope']?.toString() ?? 'unknown',
      warning: json['warning']?.toString(),
      hookSecondsAnalyzed: (json['hook_seconds_analyzed'] as num?)?.toInt(),
      sttFallbackReason: json['stt_fallback_reason']?.toString(),
    );
  }
}

class AnalysisJobStatus {
  const AnalysisJobStatus({
    required this.jobId,
    required this.status,
    required this.stage,
    required this.progress,
    required this.message,
    this.result,
    this.error,
  });

  final String status;
  final String jobId;
  final String stage;
  final int progress;
  final String message;
  final AnalysisResultViewData? result;
  final String? error;

  bool get isComplete => status == 'completed';
  bool get isInterrupted => status == 'interrupted';
  bool get isFailed =>
      status == 'failed' || status == 'error' || status == 'not_found';

  factory AnalysisJobStatus.fromJson(Map<String, dynamic> json) {
    final status = json['status']?.toString() ?? 'unknown';
    final rawResult = json['result'];
    return AnalysisJobStatus(
      jobId: json['job_id']?.toString() ?? '',
      status: status,
      stage: json['stage']?.toString() ?? status,
      progress: (json['progress'] as num?)?.toInt() ?? 0,
      message: json['message']?.toString() ?? '',
      result: rawResult is Map
          ? AnalysisResultViewData.fromJson(
              Map<String, dynamic>.from(rawResult),
            )
          : null,
      error: json['error']?.toString(),
    );
  }
}
