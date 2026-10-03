import '../models/dashboard_overview.dart';
import '../models/trend_history.dart';
import '../services/api_client.dart';

class DashboardRepository {
  DashboardRepository({ApiClient? client}) : _client = client ?? ApiClient();

  final ApiClient _client;

  Future<TrendHistory> getTrendHistory(
      {required String platform,
      int days = 7,
      String? categoryId,
      String? itemKey}) async {
    final query = Uri(queryParameters: {
      'platform': platform,
      'days': '$days',
      if (categoryId != null) 'video_category_id': categoryId,
      if (itemKey != null) 'item_key': itemKey,
    }).query;
    final response = await _client.get('/dashboard/public/history?$query');
    return TrendHistory.fromJson(Map<String, dynamic>.from(response as Map));
  }

  Future<LiveTrendSnapshot> getPublicTrendSnapshot({int limit = 50}) async {
    final response =
        await _client.get('/dashboard/public/trends?trend_limit=$limit');
    return LiveTrendSnapshot.fromJson(
      Map<String, dynamic>.from(response as Map),
    );
  }

  Future<DashboardOverview> getOverview() async {
    final response =
        await _client.get('/dashboard/summary?trend_mode=live&trend_limit=50');
    return DashboardOverview.fromJson(
      Map<String, dynamic>.from(response as Map),
    );
  }

  Future<LiveTrendSnapshot> getLiveTrendSnapshot({int limit = 50}) async {
    final response =
        await _client.get('/dashboard/live-trends/snapshot?trend_limit=$limit');
    return LiveTrendSnapshot.fromJson(
      Map<String, dynamic>.from(response as Map),
    );
  }

  Future<YouTubeCategoryTrendSnapshot> getYouTubeCategoryTrendSnapshot({
    String? categoryId,
    int limit = 50,
  }) async {
    final categoryQuery = categoryId == null || categoryId.isEmpty
        ? ''
        : '&video_category_id=${Uri.encodeQueryComponent(categoryId)}';
    final response = await _client.get(
      '/dashboard/public/youtube/categories?trend_limit=$limit$categoryQuery',
    );
    return YouTubeCategoryTrendSnapshot.fromJson(
      Map<String, dynamic>.from(response as Map),
    );
  }

  Future<List<FollowedTopicItem>> getFollowedTopics() async {
    final response = await _client.get('/follows/topics?limit=100');
    final items = (response['items'] as List<dynamic>? ?? const [])
        .map((item) => FollowedTopicItem.fromJson(
              Map<String, dynamic>.from(item as Map),
            ))
        .toList();
    return items;
  }

  Future<FollowedTopicItem> followTopic(
    String value, {
    String matchType = 'keyword',
    String platform = 'all',
  }) async {
    final response = await _client.post('/follows/topic', {
      'match_type': matchType,
      'value': value,
      'platform': platform,
    });
    return FollowedTopicItem.fromJson(
      Map<String, dynamic>.from(response as Map),
    );
  }

  Future<void> unfollowTopic(int id) async {
    await _client.delete('/follows/topic/$id');
  }

  Future<Map<String, dynamic>> followPreferences() async =>
      Map<String, dynamic>.from(
          await _client.get('/follows/preferences') as Map);

  Future<void> saveNotificationMode(String mode) async {
    await _client.put('/follows/preferences', {'notification_mode': mode});
  }

  Future<List<NotificationItem>> getNotifications({
    bool unreadOnly = false,
    int limit = 20,
  }) async {
    final response = await _client.get(
      '/notifications/?unread_only=$unreadOnly&limit=$limit',
    );
    return (response['items'] as List<dynamic>? ?? const [])
        .map((item) => NotificationItem.fromJson(
              Map<String, dynamic>.from(item as Map),
            ))
        .toList();
  }

  Future<void> markNotificationsRead(List<int> ids) async {
    await _client.post('/notifications/mark_read', {'ids': ids});
  }

  Future<List<TrendSyncResult>> syncAllTrendsLive({int limit = 50}) async {
    final platforms = ['youtube', 'google'];
    final results = <TrendSyncResult>[];
    for (final platform in platforms) {
      try {
        final response = await _client.post(
          '/trends/$platform/sync?mode=live&limit=$limit',
          <String, dynamic>{},
        );
        results.add(
          TrendSyncResult.fromJson(
            platform,
            Map<String, dynamic>.from(response as Map),
          ),
        );
      } catch (error) {
        results.add(TrendSyncResult.failed(platform, error));
      }
    }
    return results;
  }
}
