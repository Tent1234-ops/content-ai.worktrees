class DatasetReviewSummary {
  const DatasetReviewSummary({
    required this.total,
    required this.pending,
    required this.approved,
    required this.rejected,
  });

  final int total;
  final int pending;
  final int approved;
  final int rejected;

  factory DatasetReviewSummary.fromJson(Map<String, dynamic> json) {
    return DatasetReviewSummary(
      total: (json['total'] as num?)?.toInt() ?? 0,
      pending: (json['pending'] as num?)?.toInt() ?? 0,
      approved: (json['approved'] as num?)?.toInt() ?? 0,
      rejected: (json['rejected'] as num?)?.toInt() ?? 0,
    );
  }
}

class DatasetReviewRun {
  const DatasetReviewRun({
    required this.collectionRunId,
    required this.datasetVersion,
    required this.status,
    required this.startedAt,
    required this.total,
    required this.pending,
    required this.approved,
    required this.rejected,
    required this.progress,
    this.lastResumedAt,
    this.failureMessage,
  });

  final int collectionRunId;
  final String datasetVersion;
  final String status;
  final DateTime? startedAt;
  final int total;
  final int pending;
  final int approved;
  final int rejected;
  final DatasetCollectionProgress progress;
  final DateTime? lastResumedAt;
  final String? failureMessage;

  factory DatasetReviewRun.fromJson(Map<String, dynamic> json) {
    return DatasetReviewRun(
      collectionRunId: (json['collection_run_id'] as num?)?.toInt() ?? 0,
      datasetVersion: json['dataset_version']?.toString() ?? '',
      status: json['status']?.toString() ?? '',
      startedAt: DateTime.tryParse(json['started_at']?.toString() ?? ''),
      total: (json['total'] as num?)?.toInt() ?? 0,
      pending: (json['pending'] as num?)?.toInt() ?? 0,
      approved: (json['approved'] as num?)?.toInt() ?? 0,
      rejected: (json['rejected'] as num?)?.toInt() ?? 0,
      progress: DatasetCollectionProgress.fromJson(
        Map<String, dynamic>.from((json['progress'] as Map?) ?? const {}),
      ),
      lastResumedAt:
          DateTime.tryParse(json['last_resumed_at']?.toString() ?? ''),
      failureMessage: json['failure_message']?.toString(),
    );
  }
}

class DatasetCollectionLeafProgress {
  const DatasetCollectionLeafProgress({
    required this.leafKey,
    required this.target,
    required this.accepted,
    required this.percent,
    required this.languageCounts,
    required this.thaiMinimum,
    required this.thaiRemaining,
    required this.uniqueChannels,
    required this.minimumUniqueChannelsExpected,
    required this.complete,
  });

  final String leafKey;
  final int target;
  final int accepted;
  final double percent;
  final Map<String, int> languageCounts;
  final int thaiMinimum;
  final int thaiRemaining;
  final int uniqueChannels;
  final int minimumUniqueChannelsExpected;
  final bool complete;

  factory DatasetCollectionLeafProgress.fromJson(Map<String, dynamic> json) {
    return DatasetCollectionLeafProgress(
      leafKey: json['leaf_key']?.toString() ?? '',
      target: (json['target'] as num?)?.toInt() ?? 0,
      accepted: (json['accepted'] as num?)?.toInt() ?? 0,
      percent: (json['percent'] as num?)?.toDouble() ?? 0,
      languageCounts: (json['language_counts'] as Map? ?? const {}).map(
        (key, value) => MapEntry(key.toString(), (value as num?)?.toInt() ?? 0),
      ),
      thaiMinimum: (json['thai_minimum'] as num?)?.toInt() ?? 0,
      thaiRemaining: (json['thai_remaining'] as num?)?.toInt() ?? 0,
      uniqueChannels: (json['unique_channels'] as num?)?.toInt() ?? 0,
      minimumUniqueChannelsExpected:
          (json['minimum_unique_channels_expected'] as num?)?.toInt() ?? 0,
      complete: json['complete'] as bool? ?? false,
    );
  }
}

class DatasetCollectionProgress {
  const DatasetCollectionProgress({
    required this.targetTotal,
    required this.acceptedTotal,
    required this.percent,
    required this.languageCounts,
    required this.uniqueChannels,
    required this.completeLeaves,
    required this.leafCount,
    required this.byLeaf,
  });

  final int targetTotal;
  final int acceptedTotal;
  final double percent;
  final Map<String, int> languageCounts;
  final int uniqueChannels;
  final int completeLeaves;
  final int leafCount;
  final List<DatasetCollectionLeafProgress> byLeaf;

  factory DatasetCollectionProgress.fromJson(Map<String, dynamic> json) {
    return DatasetCollectionProgress(
      targetTotal: (json['target_total'] as num?)?.toInt() ?? 0,
      acceptedTotal: (json['accepted_total'] as num?)?.toInt() ?? 0,
      percent: (json['percent'] as num?)?.toDouble() ?? 0,
      languageCounts: (json['language_counts'] as Map? ?? const {}).map(
        (key, value) => MapEntry(key.toString(), (value as num?)?.toInt() ?? 0),
      ),
      uniqueChannels: (json['unique_channels'] as num?)?.toInt() ?? 0,
      completeLeaves: (json['complete_leaves'] as num?)?.toInt() ?? 0,
      leafCount: (json['leaf_count'] as num?)?.toInt() ?? 0,
      byLeaf: (json['by_leaf'] as List<dynamic>? ?? const [])
          .map(
            (item) => DatasetCollectionLeafProgress.fromJson(
              Map<String, dynamic>.from(item as Map),
            ),
          )
          .toList(),
    );
  }
}

class DatasetReviewTaxonomyLeaf {
  const DatasetReviewTaxonomyLeaf({
    required this.leafKey,
    required this.level1,
    required this.level2,
    required this.level3,
    required this.minimumSampleCount,
    required this.verifiedSampleCount,
    required this.ready,
    this.splitCounts = const {},
    this.minimumSplitCounts = const {},
  });

  final String leafKey;
  final String level1;
  final String level2;
  final String level3;
  final int minimumSampleCount;
  final int verifiedSampleCount;
  final bool ready;
  final Map<String, int> splitCounts;
  final Map<String, int> minimumSplitCounts;

  String get displayName => leafKey == 'unknown'
      ? 'นอกขอบเขต'
      : [level3, level2, level1, leafKey].firstWhere((v) => v.trim().isNotEmpty);

  List<String> get coverageLabels => leafKey == 'unknown'
      ? [
          '$displayName $verifiedSampleCount คลิป',
          'ปรับเกณฑ์ ${splitCounts['validation'] ?? 0}/${minimumSplitCounts['validation'] ?? 10}',
          'ทดสอบ ${splitCounts['test'] ?? 0}/${minimumSplitCounts['test'] ?? 30}',
          if ((splitCounts['train'] ?? 0) > 0) 'สำรอง ${splitCounts['train']} คลิป',
        ]
      : ['$displayName $verifiedSampleCount/$minimumSampleCount'];

  String get path => [level1, level2, level3]
      .where((value) => value.trim().isNotEmpty)
      .join(' > ');

  factory DatasetReviewTaxonomyLeaf.fromJson(Map<String, dynamic> json) {
    return DatasetReviewTaxonomyLeaf(
      leafKey: json['leaf_key']?.toString() ?? '',
      level1: json['category_level_1']?.toString() ?? '',
      level2: json['category_level_2']?.toString() ?? '',
      level3: json['category_level_3']?.toString() ?? '',
      minimumSampleCount: (json['minimum_sample_count'] as num?)?.toInt() ?? 0,
      verifiedSampleCount:
          (json['verified_sample_count'] as num?)?.toInt() ?? 0,
      ready: json['ready'] as bool? ?? false,
      splitCounts: (json['split_counts'] as Map? ?? const {}).map(
        (k, v) => MapEntry(k.toString(), (v as num).toInt()),
      ),
      minimumSplitCounts: (json['minimum_split_counts'] as Map? ?? const {}).map(
        (k, v) => MapEntry(k.toString(), (v as num).toInt()),
      ),
    );
  }
}

class DatasetReviewCandidate {
  const DatasetReviewCandidate({
    required this.collectionRunId,
    required this.datasetVersion,
    required this.youtubeId,
    required this.title,
    required this.videoUrl,
    required this.channelTitle,
    required this.youtubeLicenseCode,
    required this.licenseName,
    required this.publicCaptionsAvailable,
    required this.proposedLeafKey,
    required this.transcriptLanguage,
    required this.captionType,
    required this.transcriptAcquisitionMethod,
    required this.transcriptScope,
    required this.transcriptTimestampsAvailable,
    required this.durationSeconds,
    required this.transcript,
    required this.transcriptPreview,
    required this.evidenceTerms,
    required this.automatedChecks,
    required this.datasetUsage,
    required this.views,
    required this.likes,
    required this.comments,
    required this.reviewStatus,
    this.reviewedLeafKey,
    this.transcriptQuality,
    this.reviewer,
    this.reviewedAt,
    this.reviewNotes,
    this.datasetId,
    this.candidateSha256 = '',
  });

  final int collectionRunId;
  final String datasetVersion;
  final String youtubeId;
  final String title;
  final String videoUrl;
  final String channelTitle;
  final String youtubeLicenseCode;
  final String licenseName;
  final bool publicCaptionsAvailable;
  final String proposedLeafKey;
  final String transcriptLanguage;
  final String captionType;
  final String transcriptAcquisitionMethod;
  final String transcriptScope;
  final bool transcriptTimestampsAvailable;
  final int durationSeconds;
  final String transcript;
  final String transcriptPreview;
  final List<String> evidenceTerms;
  final Map<String, bool> automatedChecks;
  final Map<String, bool> datasetUsage;
  final int views;
  final int likes;
  final int comments;
  final String reviewStatus;
  final String? reviewedLeafKey;
  final String? transcriptQuality;
  final String? reviewer;
  final DateTime? reviewedAt;
  final String? reviewNotes;
  final int? datasetId;
  final String candidateSha256;

  bool get allAutomatedChecksPass =>
      automatedChecks.isNotEmpty &&
      automatedChecks.values.every((value) => value);

  factory DatasetReviewCandidate.fromJson(Map<String, dynamic> json) {
    return DatasetReviewCandidate(
      collectionRunId: (json['collection_run_id'] as num?)?.toInt() ?? 0,
      datasetVersion: json['dataset_version']?.toString() ?? '',
      youtubeId: json['source_youtube_id']?.toString() ?? '',
      title: json['title']?.toString() ?? '',
      videoUrl: json['video_url']?.toString() ?? '',
      channelTitle: json['channel_title']?.toString() ?? '',
      youtubeLicenseCode: json['youtube_license_code']?.toString() ?? '',
      licenseName: json['license_name']?.toString() ?? '',
      publicCaptionsAvailable:
          json['public_captions_available'] as bool? ?? false,
      proposedLeafKey: json['proposed_leaf_key']?.toString() ?? '',
      transcriptLanguage: json['transcript_language']?.toString() ?? 'und',
      captionType: json['caption_type']?.toString() ?? 'unknown',
      transcriptAcquisitionMethod:
          json['transcript_acquisition_method']?.toString() ?? '',
      transcriptScope: json['transcript_scope']?.toString() ?? '',
      transcriptTimestampsAvailable:
          json['transcript_timestamps_available'] as bool? ?? false,
      durationSeconds: (json['duration_seconds'] as num?)?.toInt() ?? 0,
      transcript: json['transcript']?.toString() ?? '',
      transcriptPreview: json['transcript_preview']?.toString() ?? '',
      evidenceTerms: (json['evidence_terms'] as List<dynamic>? ?? const [])
          .map((item) => item.toString())
          .toList(),
      automatedChecks: Map<String, bool>.from(
        (json['automated_checks'] as Map?)?.map(
              (key, value) => MapEntry(key.toString(), value == true),
            ) ??
            const {},
      ),
      datasetUsage: Map<String, bool>.from(
        (json['dataset_usage'] as Map?)?.map(
              (key, value) => MapEntry(key.toString(), value == true),
            ) ??
            const {},
      ),
      views: (json['views'] as num?)?.toInt() ?? 0,
      likes: (json['likes'] as num?)?.toInt() ?? 0,
      comments: (json['comments'] as num?)?.toInt() ?? 0,
      reviewStatus: json['review_status']?.toString() ?? 'pending',
      reviewedLeafKey: json['reviewed_leaf_key']?.toString(),
      transcriptQuality: json['transcript_quality']?.toString(),
      reviewer: json['reviewer']?.toString(),
      reviewedAt: DateTime.tryParse(json['reviewed_at']?.toString() ?? ''),
      reviewNotes: json['review_notes']?.toString(),
      datasetId: (json['dataset_id'] as num?)?.toInt(),
      candidateSha256: json['candidate_sha256']?.toString() ?? '',
    );
  }
}

class DatasetReviewDecisionResult {
  const DatasetReviewDecisionResult({
    required this.status,
    required this.decision,
    required this.youtubeId,
    required this.collectionRunId,
    required this.reviewEventId,
    this.datasetId,
  });

  final String status;
  final String decision;
  final String youtubeId;
  final int collectionRunId;
  final int? reviewEventId;
  final int? datasetId;

  factory DatasetReviewDecisionResult.fromJson(Map<String, dynamic> json) {
    return DatasetReviewDecisionResult(
      status: json['status']?.toString() ?? '',
      decision: json['decision']?.toString() ?? '',
      youtubeId: json['source_youtube_id']?.toString() ?? '',
      collectionRunId: (json['collection_run_id'] as num?)?.toInt() ?? 0,
      reviewEventId: (json['review_event_id'] as num?)?.toInt(),
      datasetId: (json['dataset_id'] as num?)?.toInt(),
    );
  }
}

class NotebookLMImportResult {
  const NotebookLMImportResult({
    required this.collectionRunId,
    required this.candidateCount,
    required this.candidateArtifactSha256,
    required this.candidate,
  });

  final int collectionRunId;
  final int candidateCount;
  final String candidateArtifactSha256;
  final DatasetReviewCandidate candidate;

  factory NotebookLMImportResult.fromJson(Map<String, dynamic> json) {
    return NotebookLMImportResult(
      collectionRunId: (json['collection_run_id'] as num?)?.toInt() ?? 0,
      candidateCount: (json['candidate_count'] as num?)?.toInt() ?? 0,
      candidateArtifactSha256:
          json['candidate_artifact_sha256']?.toString() ?? '',
      candidate: DatasetReviewCandidate.fromJson(
        Map<String, dynamic>.from((json['candidate'] as Map?) ?? const {}),
      ),
    );
  }
}

class DatasetReviewQueueResult {
  const DatasetReviewQueueResult({
    required this.total,
    required this.limit,
    required this.offset,
    required this.summary,
    required this.runs,
    required this.taxonomy,
    required this.items,
  });

  final int total;
  final int limit;
  final int offset;
  final DatasetReviewSummary summary;
  final List<DatasetReviewRun> runs;
  final List<DatasetReviewTaxonomyLeaf> taxonomy;
  final List<DatasetReviewCandidate> items;

  factory DatasetReviewQueueResult.fromJson(Map<String, dynamic> json) {
    return DatasetReviewQueueResult(
      total: (json['total'] as num?)?.toInt() ?? 0,
      limit: (json['limit'] as num?)?.toInt() ?? 0,
      offset: (json['offset'] as num?)?.toInt() ?? 0,
      summary: DatasetReviewSummary.fromJson(
        Map<String, dynamic>.from((json['summary'] as Map?) ?? const {}),
      ),
      runs: (json['runs'] as List<dynamic>? ?? const [])
          .map((item) => DatasetReviewRun.fromJson(
                Map<String, dynamic>.from(item as Map),
              ))
          .toList(),
      taxonomy: (json['taxonomy'] as List<dynamic>? ?? const [])
          .map((item) => DatasetReviewTaxonomyLeaf.fromJson(
                Map<String, dynamic>.from(item as Map),
              ))
          .toList(),
      items: (json['items'] as List<dynamic>? ?? const [])
          .map((item) => DatasetReviewCandidate.fromJson(
                Map<String, dynamic>.from(item as Map),
              ))
          .toList(),
    );
  }
}
