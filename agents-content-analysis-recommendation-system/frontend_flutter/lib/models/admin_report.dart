import 'recommendation_result.dart' hide DatasetProfile;

class DatasetHealth {
  const DatasetHealth({
    required this.totalDatasetContents,
    required this.youtubeDatasetContents,
    required this.googleDatasetContents,
    required this.tiktokDatasetContents,
    required this.durationCoverageCount,
    required this.durationCoverageRatio,
  });

  final int totalDatasetContents;
  final int youtubeDatasetContents;
  final int googleDatasetContents;
  final int tiktokDatasetContents;
  final int durationCoverageCount;
  final double durationCoverageRatio;

  factory DatasetHealth.fromJson(Map<String, dynamic> json) {
    return DatasetHealth(
      totalDatasetContents:
          (json['total_dataset_contents'] as num?)?.toInt() ?? 0,
      youtubeDatasetContents:
          (json['youtube_dataset_contents'] as num?)?.toInt() ?? 0,
      googleDatasetContents:
          (json['google_dataset_contents'] as num?)?.toInt() ?? 0,
      tiktokDatasetContents:
          (json['tiktok_dataset_contents'] as num?)?.toInt() ?? 0,
      durationCoverageCount:
          (json['duration_coverage_count'] as num?)?.toInt() ?? 0,
      durationCoverageRatio:
          (json['duration_coverage_ratio'] as num?)?.toDouble() ?? 0,
    );
  }
}

class ProfileHealth {
  const ProfileHealth({
    required this.youtubeProfiles,
    required this.googleProfiles,
    required this.tiktokProfiles,
    required this.youtubeDomains,
    required this.googleDomains,
    required this.tiktokDomains,
  });

  final int youtubeProfiles;
  final int googleProfiles;
  final int tiktokProfiles;
  final List<String> youtubeDomains;
  final List<String> googleDomains;
  final List<String> tiktokDomains;

  factory ProfileHealth.fromJson(Map<String, dynamic> json) {
    return ProfileHealth(
      youtubeProfiles: (json['youtube_profiles'] as num?)?.toInt() ?? 0,
      googleProfiles: (json['google_profiles'] as num?)?.toInt() ?? 0,
      tiktokProfiles: (json['tiktok_profiles'] as num?)?.toInt() ?? 0,
      youtubeDomains: (json['youtube_domains'] as List<dynamic>? ?? const [])
          .map((item) => item.toString())
          .toList(),
      googleDomains: (json['google_domains'] as List<dynamic>? ?? const [])
          .map((item) => item.toString())
          .toList(),
      tiktokDomains: (json['tiktok_domains'] as List<dynamic>? ?? const [])
          .map((item) => item.toString())
          .toList(),
    );
  }
}

class DatasetProfile {
  const DatasetProfile({
    required this.domain,
    required this.sampleSize,
    required this.duration,
  });

  final String domain;
  final int sampleSize;
  final DurationRecommendation duration;

  factory DatasetProfile.fromJson(Map<String, dynamic> json) {
    return DatasetProfile(
      domain: json['domain']?.toString() ?? '-',
      sampleSize: (json['sample_size'] as num?)?.toInt() ?? 0,
      duration: DurationRecommendation.fromJson(
        Map<String, dynamic>.from(
            (json['recommended_duration'] as Map?) ?? const {}),
      ),
    );
  }
}

class RecommendationAdminReport {
  const RecommendationAdminReport({
    required this.datasetHealth,
    required this.profileHealth,
    required this.youtubeProfiles,
    required this.googleProfiles,
    required this.tiktokProfiles,
  });

  final DatasetHealth datasetHealth;
  final ProfileHealth profileHealth;
  final List<DatasetProfile> youtubeProfiles;
  final List<DatasetProfile> googleProfiles;
  final List<DatasetProfile> tiktokProfiles;

  factory RecommendationAdminReport.fromJson(Map<String, dynamic> json) {
    return RecommendationAdminReport(
      datasetHealth: DatasetHealth.fromJson(
        Map<String, dynamic>.from((json['dataset_health'] as Map?) ?? const {}),
      ),
      profileHealth: ProfileHealth.fromJson(
        Map<String, dynamic>.from((json['profile_health'] as Map?) ?? const {}),
      ),
      youtubeProfiles: (json['youtube_profiles'] as List<dynamic>? ?? const [])
          .map((item) =>
              DatasetProfile.fromJson(Map<String, dynamic>.from(item as Map)))
          .toList(),
      googleProfiles: (json['google_profiles'] as List<dynamic>? ?? const [])
          .map((item) =>
              DatasetProfile.fromJson(Map<String, dynamic>.from(item as Map)))
          .toList(),
      tiktokProfiles: (json['tiktok_profiles'] as List<dynamic>? ?? const [])
          .map((item) =>
              DatasetProfile.fromJson(Map<String, dynamic>.from(item as Map)))
          .toList(),
    );
  }
}

class AdminSettings {
  const AdminSettings({
    required this.maxKeywordsDisplay,
    required this.hookAnalysisDuration,
    required this.autoScanIntervalHours,
    required this.youtubeRegion,
    required this.googleRegion,
    required this.tiktokRegion,
    required this.enableYoutubeTrending,
    required this.enableGoogleTrends,
    required this.enableTiktokTrending,
  });

  final int maxKeywordsDisplay;
  final int hookAnalysisDuration;
  final int autoScanIntervalHours;
  final String youtubeRegion;
  final String googleRegion;
  final String tiktokRegion;
  final bool enableYoutubeTrending;
  final bool enableGoogleTrends;
  final bool enableTiktokTrending;

  factory AdminSettings.fromJson(Map<String, dynamic> json) {
    return AdminSettings(
      maxKeywordsDisplay: (json['max_keywords_display'] as num?)?.toInt() ?? 10,
      hookAnalysisDuration:
          (json['hook_analysis_duration'] as num?)?.toInt() ?? 60,
      autoScanIntervalHours:
          (json['auto_scan_interval_hours'] as num?)?.toInt() ?? 6,
      youtubeRegion: json['youtube_region']?.toString() ?? 'TH',
      googleRegion: json['google_region']?.toString() ?? 'TH',
      tiktokRegion: json['tiktok_region']?.toString() ?? 'TH',
      enableYoutubeTrending: json['enable_youtube_trending'] != false,
      enableGoogleTrends: json['enable_google_trends'] != false,
      enableTiktokTrending: json['enable_tiktok_trending'] != false,
    );
  }
}
