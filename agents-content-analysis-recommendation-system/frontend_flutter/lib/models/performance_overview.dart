/// Summary of automatic comparisons for all saved evidence topic/context cells.
/// These similarity scores are descriptive, not calibrated probabilities.
class PerformanceOverviewGroup {
  PerformanceOverviewGroup.fromJson(Map<String, dynamic> json)
      : topicId = json['topic_id'] as String,
        topicTitle = json['topic_title'] as String,
        groupIndex = json['group_index'] as int,
        format = json['format'] as String,
        ageGroup = json['age_group'] as String,
        thresholdViews = json['threshold_views'] as int,
        topicSampleSize = json['topic_sample_size'] as int,
        passingCount = json['passing_count'] as int,
        eligibleCount = json['eligible_count'] as int,
        clusteringStatus = json['clustering_status'] as String,
        similarityStatus = json['similarity_status'] as String,
        lowScore = _score(json['low_score']),
        highScore = _score(json['high_score']),
        closestGroup = json['closest_group'] as String?,
        reason = json['reason'] as String? {
    if (groupIndex < 0 || thresholdViews < 0 || topicSampleSize < 0 ||
        passingCount < 0 || eligibleCount < 0 ||
        passingCount > topicSampleSize || eligibleCount > passingCount ||
        (closestGroup != null && !{'high', 'low'}.contains(closestGroup)) ||
        (similarityStatus != 'ready' && closestGroup != null)) {
      throw const FormatException('Invalid automatic topic performance group');
    }
  }

  final String topicId, topicTitle, format, ageGroup;
  final int groupIndex, thresholdViews, topicSampleSize;
  final int passingCount, eligibleCount;
  final String clusteringStatus, similarityStatus;
  final double? lowScore, highScore;
  final String? closestGroup, reason;

  bool get conclusive =>
      similarityStatus == 'ready' && closestGroup != null;
}

double? _score(dynamic value) =>
    value is num && value.isFinite && value >= 0 && value <= 1
        ? value.toDouble()
        : null;

class PerformanceOverview {
  PerformanceOverview.fromJson(Map<String, dynamic> json)
      : status = json['status'] as String,
        category = json['category'] as String,
        limitation = json['limitation'] as String,
        groups = (json['groups'] as List<dynamic>)
            .map((item) => PerformanceOverviewGroup.fromJson(
                Map<String, dynamic>.from(item as Map)))
            .toList(growable: false),
        topicCount = json['topic_count'] as int,
        groupCount = json['group_count'] as int,
        readyCount = json['ready_count'] as int,
        highCount = json['high_count'] as int,
        lowCount = json['low_count'] as int,
        inconclusiveCount = json['inconclusive_count'] as int {
    if (json['schema_version'] != 'performance-clustering-overview-v1' ||
        groupCount != groups.length ||
        readyCount + inconclusiveCount != groupCount ||
        highCount + lowCount != readyCount ||
        topicCount != groups.map((g) => g.topicId).toSet().length) {
      throw const FormatException('Invalid automatic performance overview');
    }
  }

  final String status, category, limitation;
  final List<PerformanceOverviewGroup> groups;
  final int topicCount, groupCount, readyCount;
  final int highCount, lowCount, inconclusiveCount;
}
