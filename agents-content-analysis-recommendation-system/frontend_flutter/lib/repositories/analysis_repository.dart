import 'dart:async';
import 'dart:typed_data';

import '../models/recommendation_result.dart';
import '../models/analysis_settings.dart';
import '../services/api_client.dart';

class AnalysisRepository {
  AnalysisRepository({ApiClient? client}) : _client = client ?? ApiClient();

  final ApiClient _client;

  Future<AnalysisSettings> getSettings() async => AnalysisSettings.fromJson(
      Map<String, dynamic>.from(await _client.get('/analyze/settings') as Map));

  Future<String> startAnalyzeAndSaveVideo({
    String? filePath,
    Uint8List? fileBytes,
    Stream<List<int>>? fileStream,
    int? fileSize,
    required String fileName,
  }) async {
    final response = await _client.postMultipart(
      '/analyze/save',
      fileName: fileName,
      filePath: filePath,
      fileBytes: fileBytes,
      fileStream: fileStream,
      fileSize: fileSize,
    );
    final payload = Map<String, dynamic>.from(response as Map);
    final jobId = payload['job_id']?.toString();
    if (jobId == null || jobId.isEmpty) {
      throw Exception('Backend did not return a job id.');
    }
    return jobId;
  }

  Future<String> startRevisionVideo({
    String? filePath,
    Uint8List? fileBytes,
    Stream<List<int>>? fileStream,
    int? fileSize,
    required String fileName,
    required Map<String, dynamic> context,
    required String clientRequestId,
  }) async {
    final response = await _client.postMultipart(
      '/analyze/revision',
      fileName: fileName,
      filePath: filePath,
      fileBytes: fileBytes,
      fileStream: fileStream,
      fileSize: fileSize,
      fields: {
        'parent_content_id': context['parent_content_id'].toString(),
        'parent_analysis_id': context['parent_analysis_id'].toString(),
        'parent_recommendation_fingerprint':
            context['parent_recommendation_fingerprint'].toString(),
        'expected_plan_revision': context['expected_plan_revision'].toString(),
        'client_request_id': clientRequestId,
      },
    );
    final jobId = (response as Map)['job_id']?.toString();
    if (jobId == null || jobId.isEmpty) {
      throw Exception('Backend did not return a revision job id.');
    }
    return jobId;
  }

  Future<AnalysisJobStatus> getAnalysisJob(String jobId) async {
    final response = await _client.get('/jobs/$jobId');
    return AnalysisJobStatus.fromJson(
      Map<String, dynamic>.from(response as Map),
    );
  }

  Future<AnalysisJobStatus> getRevisionJob(String jobId) async {
    final response = await _client.get('/revision-jobs/$jobId');
    return AnalysisJobStatus.fromJson(
        Map<String, dynamic>.from(response as Map));
  }

  Future<AnalysisJobStatus> retryRevisionJob(String jobId) async {
    final response = await _client.post('/revision-jobs/$jobId/retry', {});
    return AnalysisJobStatus.fromJson(
        Map<String, dynamic>.from(response as Map));
  }
}
