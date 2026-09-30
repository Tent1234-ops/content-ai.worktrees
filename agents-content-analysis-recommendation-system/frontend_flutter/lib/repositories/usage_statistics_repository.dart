import '../services/api_client.dart';

class UsageStatisticsRepository {
  UsageStatisticsRepository({ApiClient? client})
      : _client = client ?? ApiClient();
  final ApiClient _client;

  Future<Map<String, dynamic>> load(
      {required int year, int? month, bool admin = false}) async {
    final path = admin ? '/admin/usage-statistics' : '/contents/statistics';
    final query = Uri(queryParameters: {
      'year': '$year',
      if (month != null) 'month': '$month'
    }).query;
    return Map<String, dynamic>.from(await _client.get('$path?$query') as Map);
  }
}
