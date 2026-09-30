import 'common_models.dart';

class DashboardMetrics {
  const DashboardMetrics({
    required this.totalDatasetContents,
    required this.totalUsers,
    required this.myAnalysisResults,
  });

  final int totalDatasetContents;
  final int totalUsers;
  final int myAnalysisResults;

  factory DashboardMetrics.fromJson(Map<String, dynamic> json) {
    return DashboardMetrics(
      totalDatasetContents:
          (json['total_dataset_contents'] as num?)?.toInt() ?? 0,
      totalUsers: (json['total_users'] as num?)?.toInt() ?? 0,
      myAnalysisResults: (json['my_analysis_results'] as num?)?.toInt() ?? 0,
    );
  }
}

class PlatformSummary {
  const PlatformSummary({
    required this.source,
    required this.datasetCount,
    required this.profileCount,
    required this.domains,
  });

  final String source;
  final int datasetCount;
  final int profileCount;
  final List<String> domains;

  factory PlatformSummary.fromJson(Map<String, dynamic> json) {
    return PlatformSummary(
      source: json['source']?.toString() ?? '-',
      datasetCount: (json['dataset_count'] as num?)?.toInt() ?? 0,
      profileCount: (json['profile_count'] as num?)?.toInt() ?? 0,
      domains: (json['domains'] as List<dynamic>? ?? const [])
          .map((item) => item.toString())
          .toList(),
    );
  }
}

class PlatformComparisonItem {
  const PlatformComparisonItem({
    required this.domain,
    required this.youtubeSampleSize,
    required this.googleSampleSize,
    required this.youtubeDuration,
    required this.googleDuration,
  });

  final String domain;
  final int youtubeSampleSize;
  final int googleSampleSize;
  final String youtubeDuration;
  final String googleDuration;

  factory PlatformComparisonItem.fromJson(Map<String, dynamic> json) {
    return PlatformComparisonItem(
      domain: json['domain']?.toString() ?? '-',
      youtubeSampleSize: (json['youtube_sample_size'] as num?)?.toInt() ?? 0,
      googleSampleSize: (json['google_sample_size'] as num?)?.toInt() ?? 0,
      youtubeDuration: json['youtube_duration']?.toString() ?? '-',
      googleDuration: json['google_duration']?.toString() ?? '-',
    );
  }
}

class DashboardTrendItem {
  const DashboardTrendItem({
    required this.key,
    required this.platform,
    required this.title,
    required this.sourcePlatform,
    required this.channelTitle,
    required this.thumbnailUrl,
    required this.description,
    required this.durationSeconds,
    required this.searchVolume,
    required this.trendScore,
    required this.category,
    required this.categoryId,
    required this.rankingScope,
    required this.videoUrl,
    required this.views,
    required this.likes,
    required this.comments,
    required this.viewsAvailable,
    required this.likesAvailable,
    required this.commentsAvailable,
    required this.publishedAt,
    required this.engagementSignal,
    required this.viewMetricVersion,
    required this.metricVersionChanged,
    required this.engagementChangePercent,
    required this.engagementDelta,
    required this.engagementRatePerMinute,
    required this.rank,
    required this.rankChange,
    required this.momentumScore,
    required this.changeKind,
    required this.changeLabel,
    required this.hasPreviousSnapshot,
    required this.comparisonWindowSeconds,
    required this.isMeaningfulRising,
    required this.status,
    required this.isNew,
  });

  final String key;
  final String platform;
  final String title;
  final String sourcePlatform;
  final String channelTitle;
  final String thumbnailUrl;
  final String description;
  final int? durationSeconds;
  final int? searchVolume;
  final num trendScore;
  final String category;
  final String categoryId;
  final String rankingScope;
  final String videoUrl;
  final int views;
  final int likes;
  final int comments;
  final bool viewsAvailable;
  final bool likesAvailable;
  final bool commentsAvailable;
  final String publishedAt;
  final num engagementSignal;
  final String viewMetricVersion;
  final bool metricVersionChanged;
  final num engagementChangePercent;
  final num engagementDelta;
  final num engagementRatePerMinute;
  final int rank;
  final int rankChange;
  final num momentumScore;
  final String changeKind;
  final String changeLabel;
  final bool hasPreviousSnapshot;
  final int comparisonWindowSeconds;
  final bool isMeaningfulRising;
  final String status;
  final bool isNew;

  factory DashboardTrendItem.fromJson(Map<String, dynamic> json) {
    final sourcePlatform = json['source_platform']?.toString() ??
        json['source']?.toString() ??
        '-';
    final platform =
        json['platform']?.toString() ?? _platformFromSource(sourcePlatform);
    final trendScore = json['trend_score'] as num? ?? 0;
    final explicitSearchVolume = (json['search_volume'] as num?)?.toInt();
    final searchVolume =
        explicitSearchVolume != null && explicitSearchVolume > 0
            ? explicitSearchVolume
            : platform == 'google' && trendScore > 100
                ? trendScore.round()
                : null;
    return DashboardTrendItem(
      key: json['key']?.toString() ?? '',
      platform: platform,
      title: json['title']?.toString() ?? '-',
      sourcePlatform: sourcePlatform,
      channelTitle: json['channel_title']?.toString() ??
          json['creator']?.toString() ??
          '',
      thumbnailUrl: json['thumbnail_url']?.toString() ?? '',
      description: json['description']?.toString() ?? '',
      durationSeconds: (json['duration_seconds'] as num?)?.toInt(),
      searchVolume: searchVolume,
      trendScore: trendScore,
      category: json['category']?.toString() ?? '',
      categoryId: json['category_id']?.toString() ?? '',
      rankingScope: json['ranking_scope']?.toString() ?? 'global',
      videoUrl: json['video_url']?.toString() ?? '',
      views: (json['views'] as num?)?.toInt() ?? 0,
      likes: (json['likes'] as num?)?.toInt() ?? 0,
      comments: (json['comments'] as num?)?.toInt() ?? 0,
      viewsAvailable: _metricIsAvailable(json, 'views'),
      likesAvailable: _metricIsAvailable(json, 'likes'),
      commentsAvailable: _metricIsAvailable(json, 'comments'),
      publishedAt: json['published_at']?.toString() ?? '',
      engagementSignal: (json['engagement_signal'] as num?) ??
          (json['trend_score'] as num?) ??
          0,
      viewMetricVersion: json['view_metric_version']?.toString() ?? '',
      metricVersionChanged: json['metric_version_changed'] == true,
      engagementChangePercent: json['engagement_change_percent'] as num? ?? 0,
      engagementDelta: json['engagement_delta'] as num? ?? 0,
      engagementRatePerMinute: json['engagement_rate_per_minute'] as num? ?? 0,
      rank: (json['rank'] as num?)?.toInt() ?? 0,
      rankChange: (json['rank_change'] as num?)?.toInt() ?? 0,
      momentumScore: json['momentum_score'] as num? ?? 0,
      changeKind: json['change_kind']?.toString() ?? 'baseline',
      changeLabel: json['change_label']?.toString() ?? 'Baseline',
      hasPreviousSnapshot: json['has_previous_snapshot'] == true,
      comparisonWindowSeconds:
          (json['comparison_window_seconds'] as num?)?.toInt() ?? 0,
      isMeaningfulRising: json['is_meaningful_rising'] == true,
      status:
          json['status']?.toString() ?? _statusFromScore(json['trend_score']),
      isNew: json['is_new'] == true,
    );
  }
}

bool _metricIsAvailable(Map<String, dynamic> json, String metric) {
  final explicit = json['${metric}_available'];
  if (explicit is bool) return explicit;
  return (json[metric] as num? ?? 0) > 0;
}

String _platformFromSource(String source) {
  final normalized = source.toLowerCase();
  if (normalized.contains('youtube')) return 'youtube';
  if (normalized.contains('google')) return 'google';
  if (normalized.contains('tiktok')) return 'tiktok';
  return normalized;
}

String _statusFromScore(Object? rawScore) {
  final score = rawScore is num ? rawScore.toDouble() : 0.0;
  if (score >= 1000000) return 'Hot';
  if (score >= 250000) return 'Rising';
  return 'Stable';
}

class DashboardPlatformTrends {
  const DashboardPlatformTrends({
    required this.platform,
    required this.mode,
    required this.items,
  });

  final String platform;
  final String mode;
  final List<DashboardTrendItem> items;

  bool get isLive => mode == 'live';

  DashboardPlatformTrends retainPreviousItems(
    DashboardPlatformTrends previous,
  ) {
    if (items.isNotEmpty || mode == 'live' || previous.items.isEmpty) {
      return this;
    }
    return DashboardPlatformTrends(
      platform: platform,
      mode: mode,
      items: previous.items,
    );
  }

  factory DashboardPlatformTrends.fromJson(
    String platform,
    Map<String, dynamic>? json,
  ) {
    return DashboardPlatformTrends(
      platform: platform,
      mode: json?['mode']?.toString() ?? 'unknown',
      items: (json?['items'] as List<dynamic>? ?? const [])
          .map((item) => DashboardTrendItem.fromJson(
                Map<String, dynamic>.from(item as Map),
              ))
          .toList(),
    );
  }
}

class FollowedTopicItem {
  const FollowedTopicItem({
    required this.id,
    required this.matchType,
    required this.value,
    required this.createdAt,
    this.platform = 'all',
  });

  final int id;
  final String matchType;
  final String value;
  final String createdAt;
  final String platform;

  factory FollowedTopicItem.fromJson(Map<String, dynamic> json) {
    return FollowedTopicItem(
      id: (json['id'] as num?)?.toInt() ?? 0,
      matchType: json['match_type']?.toString() ?? 'keyword',
      platform: json['platform']?.toString() ?? 'all',
      value: json['value']?.toString() ?? '',
      createdAt: json['created_at']?.toString() ?? '',
    );
  }
}

class NotificationItem {
  const NotificationItem({
    required this.id,
    required this.watchSessionId,
    required this.trendKey,
    required this.platform,
    required this.title,
    required this.type,
    required this.category,
    required this.detectedAt,
    required this.isRead,
    required this.createdAt,
  });

  final int id;
  final int watchSessionId;
  final String trendKey;
  final String platform;
  final String title;
  final String type;
  final String category;
  final String detectedAt;
  final bool isRead;
  final String createdAt;

  factory NotificationItem.fromJson(Map<String, dynamic> json) {
    return NotificationItem(
      id: (json['notification_id'] as num?)?.toInt() ?? 0,
      watchSessionId: (json['watch_session_id'] as num?)?.toInt() ?? 0,
      trendKey: json['trend_key']?.toString() ?? '',
      platform: json['platform']?.toString() ?? 'unknown',
      title: json['title']?.toString() ?? 'New live trend',
      type: json['type']?.toString() ?? 'new_live_trend',
      category: json['category']?.toString() ?? 'general',
      detectedAt: json['detected_at']?.toString() ?? '',
      isRead: json['is_read'] == true,
      createdAt: json['created_at']?.toString() ?? '',
    );
  }
}

class LiveTrendSnapshot {
  const LiveTrendSnapshot({
    required this.generatedAt,
    required this.newCount,
    required this.newNotifications,
    required this.youtubeTrends,
    required this.googleTrends,
    required this.tiktokTrends,
  });

  final String generatedAt;
  final int newCount;
  final List<NotificationItem> newNotifications;
  final DashboardPlatformTrends youtubeTrends;
  final DashboardPlatformTrends googleTrends;
  final DashboardPlatformTrends tiktokTrends;

  List<DashboardPlatformTrends> get platformTrends => [
        youtubeTrends,
        googleTrends,
        tiktokTrends,
      ];

  LiveTrendSnapshot retainPreviousItems(LiveTrendSnapshot? previous) {
    if (previous == null) return this;
    return LiveTrendSnapshot(
      generatedAt: generatedAt,
      newCount: newCount,
      newNotifications: newNotifications,
      youtubeTrends: youtubeTrends.retainPreviousItems(previous.youtubeTrends),
      googleTrends: googleTrends.retainPreviousItems(previous.googleTrends),
      tiktokTrends: tiktokTrends.retainPreviousItems(previous.tiktokTrends),
    );
  }

  factory LiveTrendSnapshot.fromJson(Map<String, dynamic> json) {
    final platforms =
        Map<String, dynamic>.from((json['platforms'] as Map?) ?? const {});
    return LiveTrendSnapshot(
      generatedAt: json['generated_at']?.toString() ?? '',
      newCount: (json['new_count'] as num?)?.toInt() ?? 0,
      newNotifications:
          (json['new_notifications'] as List<dynamic>? ?? const [])
              .map((item) => NotificationItem.fromJson(
                    Map<String, dynamic>.from(item as Map),
                  ))
              .toList(),
      youtubeTrends: DashboardPlatformTrends.fromJson(
        'youtube',
        platforms['youtube'] is Map
            ? Map<String, dynamic>.from(platforms['youtube'] as Map)
            : null,
      ),
      googleTrends: DashboardPlatformTrends.fromJson(
        'google',
        platforms['google'] is Map
            ? Map<String, dynamic>.from(platforms['google'] as Map)
            : null,
      ),
      tiktokTrends: DashboardPlatformTrends.fromJson(
        'tiktok',
        platforms['tiktok'] is Map
            ? Map<String, dynamic>.from(platforms['tiktok'] as Map)
            : null,
      ),
    );
  }
}

class YouTubeTrendCategory {
  const YouTubeTrendCategory({
    required this.categoryId,
    required this.title,
    required this.total,
    required this.providerStatus,
    required this.rankingScope,
    required this.items,
    required this.hasPreviousSnapshot,
    this.error,
  });

  final String categoryId;
  final String title;
  final int total;
  final String providerStatus;
  final String rankingScope;
  final List<DashboardTrendItem> items;
  final bool hasPreviousSnapshot;
  final String? error;

  factory YouTubeTrendCategory.fromJson(Map<String, dynamic> json) {
    return YouTubeTrendCategory(
      categoryId: json['category_id']?.toString() ?? '',
      title: json['title']?.toString() ?? '',
      total: (json['total'] as num?)?.toInt() ?? 0,
      providerStatus: json['provider_status']?.toString() ?? 'pending',
      rankingScope: json['ranking_scope']?.toString() ?? '',
      items: (json['items'] as List<dynamic>? ?? const [])
          .map(
            (item) => DashboardTrendItem.fromJson(
              Map<String, dynamic>.from(item as Map),
            ),
          )
          .toList(),
      hasPreviousSnapshot: json['has_previous_snapshot'] == true,
      error: json['error']?.toString(),
    );
  }
}

class YouTubeCategoryTrendSnapshot {
  const YouTubeCategoryTrendSnapshot({
    required this.runId,
    required this.snapshotStatus,
    required this.generatedAt,
    required this.region,
    required this.refreshIntervalSeconds,
    required this.categories,
    required this.selectedCategory,
  });

  final int? runId;
  final String snapshotStatus;
  final String generatedAt;
  final String region;
  final int refreshIntervalSeconds;
  final List<YouTubeTrendCategory> categories;
  final YouTubeTrendCategory? selectedCategory;

  factory YouTubeCategoryTrendSnapshot.fromJson(Map<String, dynamic> json) {
    final rawSelected = json['selected_category'];
    return YouTubeCategoryTrendSnapshot(
      runId: (json['run_id'] as num?)?.toInt(),
      snapshotStatus: json['snapshot_status']?.toString() ?? 'pending',
      generatedAt: json['generated_at']?.toString() ?? '',
      region: json['region']?.toString() ?? 'TH',
      refreshIntervalSeconds:
          (json['refresh_interval_seconds'] as num?)?.toInt() ?? 60,
      categories: (json['categories'] as List<dynamic>? ?? const [])
          .map(
            (item) => YouTubeTrendCategory.fromJson(
              Map<String, dynamic>.from(item as Map),
            ),
          )
          .toList(),
      selectedCategory: rawSelected is Map
          ? YouTubeTrendCategory.fromJson(
              Map<String, dynamic>.from(rawSelected),
            )
          : null,
    );
  }
}

class TrendSyncResult {
  const TrendSyncResult({
    required this.platform,
    required this.created,
    required this.updated,
    required this.notifications,
    required this.mode,
    required this.totalFetched,
    this.error,
  });

  final String platform;
  final int created;
  final int updated;
  final int notifications;
  final String mode;
  final int totalFetched;
  final String? error;

  bool get failed => error != null;

  factory TrendSyncResult.fromJson(String platform, Map<String, dynamic> json) {
    return TrendSyncResult(
      platform: platform,
      created: (json['created'] as num?)?.toInt() ?? 0,
      updated: (json['updated'] as num?)?.toInt() ?? 0,
      notifications: (json['notifications'] as num?)?.toInt() ?? 0,
      mode: json['mode']?.toString() ?? 'unknown',
      totalFetched: (json['total_fetched'] as num?)?.toInt() ?? 0,
    );
  }

  factory TrendSyncResult.failed(String platform, Object error) {
    return TrendSyncResult(
      platform: platform,
      created: 0,
      updated: 0,
      notifications: 0,
      mode: 'failed',
      totalFetched: 0,
      error: error.toString(),
    );
  }
}

class DashboardOverview {
  const DashboardOverview({
    required this.userRole,
    required this.metrics,
    required this.platformComparison,
    required this.platformSummaries,
    required this.topTrends,
    required this.youtubeTrends,
    required this.googleTrends,
    required this.tiktokTrends,
    required this.sourceDistribution,
  });

  final String userRole;
  final DashboardMetrics metrics;
  final List<PlatformComparisonItem> platformComparison;
  final List<PlatformSummary> platformSummaries;
  final List<DashboardTrendItem> topTrends;
  final DashboardPlatformTrends youtubeTrends;
  final DashboardPlatformTrends googleTrends;
  final DashboardPlatformTrends tiktokTrends;
  final List<ChartItem> sourceDistribution;

  bool get isAdmin => userRole == 'admin';

  List<DashboardPlatformTrends> get platformTrends => [
        youtubeTrends,
        googleTrends,
        tiktokTrends,
      ];

  List<DashboardTrendItem> get liveYoutubeTrends => youtubeTrends.items;
  String get liveYoutubeTrendMode => youtubeTrends.mode;

  factory DashboardOverview.liveOnly(LiveTrendSnapshot snapshot) {
    return DashboardOverview(
      userRole: 'user',
      metrics: const DashboardMetrics(
        totalDatasetContents: 0,
        totalUsers: 0,
        myAnalysisResults: 0,
      ),
      platformComparison: const [],
      platformSummaries: const [],
      topTrends:
          snapshot.platformTrends.expand((platform) => platform.items).toList(),
      youtubeTrends: snapshot.youtubeTrends,
      googleTrends: snapshot.googleTrends,
      tiktokTrends: snapshot.tiktokTrends,
      sourceDistribution: const [],
    );
  }

  factory DashboardOverview.fromJson(Map<String, dynamic> json) {
    return DashboardOverview(
      userRole: json['user_role']?.toString() ?? 'user',
      metrics: DashboardMetrics.fromJson(
        Map<String, dynamic>.from((json['metrics'] as Map?) ?? const {}),
      ),
      platformComparison:
          (json['platform_comparison'] as List<dynamic>? ?? const [])
              .map((item) => PlatformComparisonItem.fromJson(
                    Map<String, dynamic>.from(item as Map),
                  ))
              .toList(),
      platformSummaries:
          (json['platform_summaries'] as List<dynamic>? ?? const [])
              .map((item) => PlatformSummary.fromJson(
                    Map<String, dynamic>.from(item as Map),
                  ))
              .toList(),
      topTrends: (json['top_trends'] as List<dynamic>? ?? const [])
          .map((item) => DashboardTrendItem.fromJson(
                Map<String, dynamic>.from(item as Map),
              ))
          .toList(),
      youtubeTrends: DashboardPlatformTrends.fromJson(
        'youtube',
        json['youtube_trends'] is Map
            ? Map<String, dynamic>.from(json['youtube_trends'] as Map)
            : null,
      ),
      googleTrends: DashboardPlatformTrends.fromJson(
        'google',
        json['google_trends'] is Map
            ? Map<String, dynamic>.from(json['google_trends'] as Map)
            : null,
      ),
      tiktokTrends: DashboardPlatformTrends.fromJson(
        'tiktok',
        json['tiktok_trends'] is Map
            ? Map<String, dynamic>.from(json['tiktok_trends'] as Map)
            : null,
      ),
      sourceDistribution:
          (json['source_distribution'] as List<dynamic>? ?? const [])
              .map((item) => ChartItem.fromJson(
                    Map<String, dynamic>.from(item as Map),
                    labelKey: 'source_platform',
                  ))
              .toList(),
    );
  }
}
