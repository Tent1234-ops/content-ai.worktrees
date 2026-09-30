class DatasetItem {
  const DatasetItem({
    required this.datasetId,
    required this.title,
    required this.videoUrl,
    required this.transcript,
    required this.sourcePlatform,
    required this.category,
    required this.views,
    required this.likes,
    required this.comments,
    required this.trendScore,
    required this.durationSeconds,
    required this.publishedAt,
    this.taxonomyVersion = '',
    this.taxonomyLeafKey = '',
    this.categoryLevel1 = '',
    this.categoryLevel2 = '',
    this.categoryLevel3 = '',
    this.transcriptSha256 = '',
    this.dataSplit = '',
    this.isTrainingEligible = false,
    this.reviewedBy = '',
    this.reviewedAt = '',
    this.deletedAt,
    this.quality = const {},
  });

  final int datasetId;
  final String title;
  final String videoUrl;
  final String transcript;
  final String sourcePlatform;
  final String category;
  final int views;
  final int likes;
  final int comments;
  final num trendScore;
  final int? durationSeconds;
  final String publishedAt;
  final String taxonomyVersion;
  final String taxonomyLeafKey;
  final String categoryLevel1;
  final String categoryLevel2;
  final String categoryLevel3;
  final String transcriptSha256;
  final String dataSplit;
  final bool isTrainingEligible;
  final String reviewedBy;
  final String reviewedAt;
  final DateTime? deletedAt;
  final Map<String, dynamic> quality;

  String get taxonomyPath => [categoryLevel1, categoryLevel2, categoryLevel3]
      .where((value) => value.trim().isNotEmpty)
      .join(' > ');

  factory DatasetItem.fromJson(Map<String, dynamic> json) {
    return DatasetItem(
      datasetId: (json['dataset_id'] as num?)?.toInt() ?? 0,
      title: json['title']?.toString() ?? '-',
      videoUrl: json['video_url']?.toString() ?? '',
      transcript: json['transcript']?.toString() ?? '',
      sourcePlatform: json['source_platform']?.toString() ?? '-',
      category: json['category']?.toString() ?? 'uncategorized',
      views: (json['views'] as num?)?.toInt() ?? 0,
      likes: (json['likes'] as num?)?.toInt() ?? 0,
      comments: (json['comments'] as num?)?.toInt() ?? 0,
      trendScore: json['trend_score'] as num? ?? 0,
      durationSeconds: (json['duration_seconds'] as num?)?.toInt(),
      publishedAt: json['published_at']?.toString() ?? '',
      taxonomyVersion: json['taxonomy_version']?.toString() ?? '',
      taxonomyLeafKey: json['taxonomy_leaf_key']?.toString() ?? '',
      categoryLevel1: json['category_level_1']?.toString() ?? '',
      categoryLevel2: json['category_level_2']?.toString() ?? '',
      categoryLevel3: json['category_level_3']?.toString() ?? '',
      transcriptSha256: json['transcript_sha256']?.toString() ?? '',
      dataSplit: json['data_split']?.toString() ?? '',
      isTrainingEligible: json['is_training_eligible'] as bool? ?? false,
      reviewedBy: json['reviewed_by']?.toString() ?? '',
      reviewedAt: json['reviewed_at']?.toString() ?? '',
      deletedAt: DateTime.tryParse(json['deleted_at']?.toString() ?? ''),
      quality: Map<String, dynamic>.from(json['quality'] as Map? ?? const {}),
    );
  }

  Map<String, dynamic> toEditableJson() {
    return {
      'title': title,
      'video_url': videoUrl,
      'transcript': transcript,
      'taxonomy_leaf_key': taxonomyLeafKey,
      'views': views,
      'likes': likes,
      'comments': comments,
      'trend_score': trendScore,
      'duration_seconds': durationSeconds,
    };
  }
}
