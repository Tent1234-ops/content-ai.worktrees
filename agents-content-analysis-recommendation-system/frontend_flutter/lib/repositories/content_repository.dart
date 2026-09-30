import '../models/common_models.dart';
import '../models/content_history.dart';
import '../models/clip_revision_plan.dart';
import '../models/recommendation_result.dart';
import '../services/api_client.dart';

class ContentRepository {
  ContentRepository({ApiClient? client}) : _client = client ?? ApiClient();

  final ApiClient _client;

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
