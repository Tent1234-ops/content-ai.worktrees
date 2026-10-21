import '../models/common_models.dart';
import '../models/content_history.dart';
import '../models/clip_revision_plan.dart';
import '../models/recommendation_result.dart';
import '../models/outcome_prediction.dart';
import '../models/performance_clustering.dart';
import '../models/performance_overview.dart';
import '../services/api_client.dart';

class ContentRepository {
  ContentRepository({ApiClient? client}) : _client = client ?? ApiClient();

  final ApiClient _client;

  // Legacy automatic overview has no corresponding backend endpoint yet.
  // Keep the contract for its existing widget/tests without inventing an API.
  Future<PerformanceOverview> getAutomaticPerformanceOverview(int contentId) {
    throw UnsupportedError(
      'Automatic performance overview is not available in this backend. '
      'Use the topic-specific performance comparison instead.',
    );
  }

  Future<PerformanceComparison> getPerformanceComparison(int contentId,
      {int? minimumViews,
      String? topicId,
      int? groupIndex,
      String comparisonMethod = 'embedding_centroid'}) async {
    final params = <String, String>{};
    if (minimumViews != null) params['minimum_views'] = '$minimumViews';
    if (topicId != null) params['topic_id'] = topicId;
    if (groupIndex != null) params['group_index'] = '$groupIndex';
    params['comparison_method'] = comparisonMethod;
    final query =
        params.isEmpty ? '' : '?${Uri(queryParameters: params).query}';
    final response = await _client
        .get('/contents/$contentId/performance-clustering$query')
        .timeout(Duration(
            seconds: comparisonMethod == 'embedding_centroid' ? 180 : 30));
    return PerformanceComparison.fromJson(
        Map<String, dynamic>.from(response as Map));
  }

  Future<ClipRevisionPlan> getRevisionPlan(int contentId) async =>
      ClipRevisionPlan.fromJson(Map<String, dynamic>.from(
          await _client.get('/contents/$contentId/revision-plan') as Map));

  Future<ClipRevisionPlan> saveRevisionPlan(
          int contentId, Map<String, dynamic> body) async =>
      ClipRevisionPlan.fromJson(Map<String, dynamic>.from(await _client.put(
          '/contents/$contentId/revision-plan', body) as Map));

  Future<AnalysisResultViewData> getContentResult(int contentId) async {
    final response = await _client.get('/contents/$contentId');
    return AnalysisResultViewData.fromJson(
      Map<String, dynamic>.from(response as Map),
    );
  }

  Future<OutcomeScenario> simulateOutcomeScenario({
    required int contentId,
    required int analysisId,
    required String assessmentFingerprint,
    required List<String> selectedTopicIds,
  }) async =>
      OutcomeScenario.fromJson(await _client.post(
        '/contents/$contentId/outcome-scenario',
        {
          'analysis_id': analysisId,
          'assessment_fingerprint': assessmentFingerprint,
          'selected_topic_ids': selectedTopicIds,
        },
      ));

  Future<PaginatedResult<ContentHistoryItem>> listMyContents({
    int limit = 20,
    int offset = 0,
  }) async {
    final response = Map<String, dynamic>.from(
      await _client.get('/contents/my?limit=$limit&offset=$offset') as Map,
    );
    return PaginatedResult<ContentHistoryItem>(
      total: (response['total'] as num?)?.toInt() ?? 0,
      items: (response['items'] as List<dynamic>? ?? const [])
          .map((item) => ContentHistoryItem.fromJson(
              Map<String, dynamic>.from(item as Map)))
          .toList(),
    );
  }
}
