class KeywordScore {
  const KeywordScore({
    required this.keyword,
    required this.score,
    this.supportCount = 0,
    this.sampleSize = 0,
    this.supportRatio = 0,
    this.totalFrequency = 0,
    this.supportingDatasetRowIds = const [],
    this.supportingExamples = const [],
  });

  final String keyword;
  final double score;
  final int supportCount;
  final int sampleSize;
  final double supportRatio;
  final int totalFrequency;
  final List<int> supportingDatasetRowIds;
  final List<KeywordEvidenceExample> supportingExamples;

  bool get hasDatasetEvidence =>
      supportCount > 0 && sampleSize > 0 && supportingDatasetRowIds.isNotEmpty;

  factory KeywordScore.fromJson(Map<String, dynamic> json) {
    return KeywordScore(
      keyword: json['keyword']?.toString() ?? '-',
      score: (json['score'] as num?)?.toDouble() ?? 0,
      supportCount: (json['support_count'] as num?)?.toInt() ?? 0,
      sampleSize: (json['sample_size'] as num?)?.toInt() ?? 0,
      supportRatio: (json['support_ratio'] as num?)?.toDouble() ?? 0,
      totalFrequency: (json['total_frequency'] as num?)?.toInt() ?? 0,
      supportingDatasetRowIds:
          (json['supporting_dataset_row_ids'] as List<dynamic>? ?? const [])
              .whereType<num>()
              .map((item) => item.toInt())
              .toList(),
      supportingExamples:
          (json['supporting_examples'] as List<dynamic>? ?? const [])
              .whereType<Map>()
              .map(
                (item) => KeywordEvidenceExample.fromJson(
                  Map<String, dynamic>.from(item),
                ),
              )
              .toList(),
    );
  }
}

class KeywordEvidenceExample {
  const KeywordEvidenceExample({
    required this.datasetId,
    required this.title,
    required this.frequency,
    this.sourceRecordId = '',
    this.videoUrl = '',
    this.platform = 'youtube',
    this.publishedAt,
    this.statisticsCapturedAt,
  });

  final int datasetId;
  final String sourceRecordId;
  final String title;
  final String videoUrl;
  final String platform;
  final int frequency;
  final DateTime? publishedAt;
  final DateTime? statisticsCapturedAt;

  factory KeywordEvidenceExample.fromJson(Map<String, dynamic> json) {
    return KeywordEvidenceExample(
      datasetId: (json['dataset_id'] as num?)?.toInt() ?? 0,
      sourceRecordId: json['source_record_id']?.toString() ?? '',
      title: json['title']?.toString() ?? 'Untitled',
      videoUrl: json['video_url']?.toString() ?? '',
      platform: json['platform']?.toString() ?? 'youtube',
      frequency: (json['frequency'] as num?)?.toInt() ?? 0,
      publishedAt: DateTime.tryParse(json['published_at']?.toString() ?? ''),
      statisticsCapturedAt:
          DateTime.tryParse(json['statistics_captured_at']?.toString() ?? ''),
    );
  }
}

class ChartItem {
  const ChartItem({required this.label, required this.count});

  final String label;
  final num count;

  factory ChartItem.fromJson(
    Map<String, dynamic> json, {
    required String labelKey,
    String valueKey = 'count',
  }) {
    return ChartItem(
      label: json[labelKey]?.toString() ?? '-',
      count: json[valueKey] as num? ?? 0,
    );
  }

  Map<String, dynamic> toChartJson(String labelKey, String valueKey) {
    return {labelKey: label, valueKey: count};
  }
}

class PaginatedResult<T> {
  const PaginatedResult({
    required this.total,
    required this.items,
  });

  final int total;
  final List<T> items;
}
