import '../models/admin_report.dart';
import '../models/analysis_settings.dart';
import '../models/model_training.dart';
import '../models/managed_user.dart';
import '../models/common_models.dart';
import '../models/dataset_item.dart';
import '../models/dataset_review.dart';
import '../models/system_log.dart';
import '../services/api_client.dart';

class AdminRepository {
  AdminRepository({ApiClient? client}) : _client = client ?? ApiClient();

  final ApiClient _client;

  Future<Map<String, dynamic>> referenceStatistics({int offset = 0}) async =>
      Map<String, dynamic>.from(await _client
          .get('/admin/reference-statistics?offset=$offset&limit=20') as Map);

  Future<Map<String, dynamic>> referenceStatisticsHistory(int id) async =>
      Map<String, dynamic>.from(
          await _client.get('/admin/datasets/$id/statistics') as Map);

  Future<String> refreshReferenceStatistics() async {
    final result =
        await _client.post('/admin/reference-statistics/refresh', {}) as Map;
    return result['job_id'] as String;
  }

  Future<Map<String, dynamic>> referenceStatisticsJob(String id) async =>
      Map<String, dynamic>.from(await _client.get('/jobs/$id') as Map);

  Future<void> saveReferenceStatisticsSettings(
      Map<String, dynamic> values) async {
    await _client.put('/admin/reference-statistics/settings', values);
  }

  Future<Map<String, dynamic>> datasetReadiness(
      {String category = 'all', String role = 'all', int offset = 0}) async {
    final query = Uri(queryParameters: {
      if (category != 'all') 'category': category,
      'role': role,
      'offset': '$offset',
      'limit': '20',
    }).query;
    return Map<String, dynamic>.from(
        await _client.get('/admin/datasets/readiness?$query') as Map);
  }

  Future<Map<String, dynamic>> trendSettings() async =>
      Map<String, dynamic>.from(
          await _client.get('/admin/trend-settings') as Map);

  Future<Map<String, dynamic>> saveTrendSettings(
          Map<String, dynamic> values) async =>
      Map<String, dynamic>.from(
          await _client.put('/admin/trend-settings', values) as Map);

  Future<void> deleteDataset(int id) async {
    final result =
        await _client.delete('/admin/datasets/$id?confirmation_id=$id') as Map;
    if (result['deleted'] != true || result['dataset_id'] != id) {
      throw StateError('ระบบยังไม่ยืนยันการย้ายข้อมูลเข้าถังขยะ');
    }
  }

  Future<DatasetItem> restoreDataset(int id) async {
    final result = DatasetItem.fromJson(Map<String, dynamic>.from(await _client
        .post('/admin/datasets/$id/restore?confirmation_id=$id', {}) as Map));
    if (result.datasetId != id || result.deletedAt != null) {
      throw StateError('ระบบยังไม่ยืนยันการกู้คืนข้อมูล');
    }
    return result;
  }

  Future<Map<String, dynamic>> sourceHealth() async =>
      Map<String, dynamic>.from(
          await _client.get('/admin/sources/health') as Map);

  Future<ManagedUsersPage> listUsers(
      {String query = '',
      String role = 'all',
      String state = 'all',
      int offset = 0}) async {
    final params = Uri(queryParameters: {
      'q': query,
      'role': role,
      'state': state,
      'offset': '$offset',
      'limit': '20'
    }).query;
    return ManagedUsersPage.fromJson(Map<String, dynamic>.from(
        await _client.get('/admin/users?$params') as Map));
  }

  Future<ManagedUser> userDetail(int id) async => ManagedUser.fromJson(
      Map<String, dynamic>.from(await _client.get('/admin/users/$id') as Map));
  Future<void> createUser(Map<String, dynamic> fields) async {
    await _client.post('/admin/users', fields);
  }

  Future<void> updateUser(int id, Map<String, dynamic> fields) async {
    await _client.put('/admin/users/$id', fields);
  }

  Future<void> revokeUserSessions(ManagedUser user) async {
    await _client.post('/admin/users/${user.id}/revoke-sessions',
        {'expected_revision': user.revision});
  }

  Future<int> deleteUser(ManagedUser user, String confirmation) async {
    final response = Map<String, dynamic>.from(await _client
        .delete('/admin/users/${user.id}', body: {
      'expected_revision': user.revision,
      'confirmation': confirmation
    }) as Map);
    return (response['files_remaining'] as num?)?.toInt() ?? 0;
  }

  Future<TrainingOverview> trainingOverview() async =>
      TrainingOverview.fromJson(
          trainingMap(await _client.get('/admin/training')));
  Future<TrainingRun> startTraining(String fingerprint) async =>
      TrainingRun.fromJson(trainingMap(await _client
          .post('/admin/training/runs', {'dataset_fingerprint': fingerprint})));
  Future<TrainingRun> trainingRun(String id) async => TrainingRun.fromJson(
      trainingMap(await _client.get('/admin/training/runs/$id')));
  Future<PaginatedResult<TrainedModel>> trainingModels(
      {required int offset}) async {
    final json = trainingMap(
        await _client.get('/admin/training/models?limit=20&offset=$offset'));
    return PaginatedResult(
        total: (json['total'] as num).toInt(),
        items: trainingRows(json['items']).map(TrainedModel.fromJson).toList());
  }

  Future<TrainedModel> trainingModel(int id) async => TrainedModel.fromJson(
      trainingMap(await _client.get('/admin/training/models/$id')));
  Future<void> activateTrainingModel(int id, int? activeId) async {
    await _client.post('/admin/training/models/$id/activate',
        {'expected_active_model_id': activeId});
  }

  Future<AnalysisSettings> getAnalysisSettings() async =>
      AnalysisSettings.fromJson(Map<String, dynamic>.from(
          await _client.get('/admin/analysis-settings') as Map));

  Future<AnalysisSettings> saveAnalysisSettings({
    required int uploadMaxDurationSeconds,
    required String asrModel,
    required int hookDurationSeconds,
  }) async =>
      AnalysisSettings.fromJson(Map<String, dynamic>.from(
          await _client.put('/admin/analysis-settings', {
        'upload_max_duration_seconds': uploadMaxDurationSeconds,
        'asr_model': asrModel,
        'hook_duration_seconds': hookDurationSeconds,
      }) as Map));

  Future<PaginatedResult<DatasetItem>> listDatasets({
    required int limit,
    required int offset,
    String source = 'all',
    String category = 'all',
    String search = '',
    bool trashed = false,
  }) async {
    final buffer = StringBuffer('/admin/datasets?limit=$limit&offset=$offset');
    buffer.write('&trashed=$trashed');
    if (source != 'all') {
      buffer.write('&source=$source');
    }
    if (category != 'all') {
      buffer.write('&category=${Uri.encodeComponent(category)}');
    }
    if (search.trim().isNotEmpty) {
      buffer.write('&search=${Uri.encodeComponent(search.trim())}');
    }
    final response =
        Map<String, dynamic>.from(await _client.get(buffer.toString()) as Map);
    return PaginatedResult<DatasetItem>(
      total: (response['total'] as num?)?.toInt() ?? 0,
      items: (response['items'] as List<dynamic>? ?? const [])
          .map((item) =>
              DatasetItem.fromJson(Map<String, dynamic>.from(item as Map)))
          .toList(),
    );
  }

  Future<DatasetItem> createDataset(Map<String, dynamic> payload) async {
    final response = await _client.post('/admin/datasets', payload);
    return DatasetItem.fromJson(Map<String, dynamic>.from(response as Map));
  }

  Future<DatasetItem> updateDataset(
    int datasetId,
    Map<String, dynamic> payload,
  ) async {
    final response = await _client.put('/admin/datasets/$datasetId', payload);
    final result =
        DatasetItem.fromJson(Map<String, dynamic>.from(response as Map));
    if (result.datasetId != datasetId || result.deletedAt != null) {
      throw StateError('ระบบยังไม่ยืนยันการบันทึกข้อมูล');
    }
    return result;
  }

  Future<List<DatasetReviewTaxonomyLeaf>> listTaxonomyLeaves() async {
    final response = Map<String, dynamic>.from(
      await _client.get('/classification/taxonomy') as Map,
    );
    return (response['leaves'] as List<dynamic>? ?? const [])
        .map(
          (item) => DatasetReviewTaxonomyLeaf.fromJson(
            Map<String, dynamic>.from(item as Map),
          ),
        )
        .where((item) => item.leafKey.trim().isNotEmpty)
        .toList();
  }

  Future<DatasetReviewQueueResult> listDatasetReviewQueue({
    required int limit,
    required int offset,
    String status = 'pending',
    String leafKey = 'all',
    int? collectionRunId,
    String search = '',
  }) async {
    final buffer = StringBuffer(
      '/admin/dataset-review/queue?limit=$limit&offset=$offset&status=$status',
    );
    if (leafKey != 'all') {
      buffer.write('&leaf_key=${Uri.encodeComponent(leafKey)}');
    }
    if (collectionRunId != null) {
      buffer.write('&collection_run_id=$collectionRunId');
    }
    if (search.trim().isNotEmpty) {
      buffer.write('&search=${Uri.encodeComponent(search.trim())}');
    }
    final response = Map<String, dynamic>.from(
      await _client.get(buffer.toString()) as Map,
    );
    return DatasetReviewQueueResult.fromJson(response);
  }

  Future<DatasetReviewDecisionResult> reviewDatasetCandidate({
    required DatasetReviewCandidate candidate,
    required String decision,
    String? reviewedLeafKey,
    String? transcriptQuality,
    String notes = '',
    bool requirePending = false,
  }) async {
    final response = Map<String, dynamic>.from(
      await _client.post(
        '/admin/dataset-review/runs/${candidate.collectionRunId}'
        '/candidates/${Uri.encodeComponent(candidate.youtubeId)}',
        {
          'decision': decision,
          'reviewed_leaf_key': reviewedLeafKey,
          'transcript_quality': transcriptQuality,
          'notes': notes.trim().isEmpty ? null : notes.trim(),
          if (candidate.candidateSha256.isNotEmpty)
            'expected_candidate_sha256': candidate.candidateSha256,
          'require_pending': requirePending,
        },
      ) as Map,
    );
    return DatasetReviewDecisionResult.fromJson(response);
  }

  Future<NotebookLMImportResult> createNotebookLMCandidate({
    required String videoUrl,
    required String transcript,
    required String proposedLeafKey,
    required String transcriptLanguage,
    required String captionType,
    required String collectionStrategy,
    int? collectionRunId,
  }) async {
    final response = await _client.post(
      '/admin/dataset-review/notebooklm/candidates',
      {
        'video_url': videoUrl.trim(),
        'transcript': transcript.trim(),
        'proposed_leaf_key': proposedLeafKey,
        'transcript_language': transcriptLanguage,
        'caption_type': captionType,
        'collection_strategy': collectionStrategy,
        'collection_run_id': collectionRunId,
        'dataset_version': 'youtube-public-research-th-v1',
      },
    );
    return NotebookLMImportResult.fromJson(
      Map<String, dynamic>.from(response as Map),
    );
  }

  Future<List<Map<String, dynamic>>> previewTrainingChannels(
      List<String> ids) async {
    final response = trainingMap(await _client
        .post('/admin/training/channel-preview', {'channel_ids': ids}));
    return trainingRows(response['items']);
  }

  Future<RecommendationAdminReport> getRecommendationReport() async {
    final response = await _client.get('/recommendations/admin/report');
    return RecommendationAdminReport.fromJson(
      Map<String, dynamic>.from(response as Map),
    );
  }

  Future<AdminSettings> getSettings() async {
    final response = await _client.get('/admin/settings');
    return AdminSettings.fromJson(Map<String, dynamic>.from(response as Map));
  }

  Future<AdminSettings> updateSettings(Map<String, dynamic> payload) async {
    final response = await _client.put('/admin/settings', payload);
    return AdminSettings.fromJson(Map<String, dynamic>.from(response as Map));
  }

  Future<PaginatedResult<SystemLogItem>> listLogs({
    required int limit,
    required int offset,
    String status = 'all',
    String action = '',
  }) async {
    final buffer = StringBuffer('/admin/logs?limit=$limit&offset=$offset');
    if (status != 'all') {
      buffer.write('&status=$status');
    }
    if (action.trim().isNotEmpty) {
      buffer.write('&action=${Uri.encodeComponent(action.trim())}');
    }
    final response =
        Map<String, dynamic>.from(await _client.get(buffer.toString()) as Map);
    return PaginatedResult<SystemLogItem>(
      total: (response['total'] as num?)?.toInt() ?? 0,
      items: (response['items'] as List<dynamic>? ?? const [])
          .map((item) =>
              SystemLogItem.fromJson(Map<String, dynamic>.from(item as Map)))
          .toList(),
    );
  }
}
