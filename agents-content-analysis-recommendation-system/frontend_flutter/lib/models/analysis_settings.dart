class AnalysisSettings {
  const AnalysisSettings({
    required this.uploadMaxDurationSeconds,
    required this.asrModel,
    required this.hookDurationSeconds,
    required this.asrReady,
    this.updatedAt = '',
    this.whisperModels = const [],
    this.classificationModel = const {},
    this.outcomeContexts = const [],
  });

  final int uploadMaxDurationSeconds;
  final String asrModel;
  final int hookDurationSeconds;
  final bool asrReady;
  final String updatedAt;
  final List<WhisperOption> whisperModels;
  final Map<String, dynamic> classificationModel;
  final List<Map<String, dynamic>> outcomeContexts;

  bool acceptsDuration(Duration duration) =>
      duration <= Duration(seconds: uploadMaxDurationSeconds, milliseconds: 50);

  factory AnalysisSettings.fromJson(Map<String, dynamic> json) =>
      AnalysisSettings(
        uploadMaxDurationSeconds:
            (json['upload_max_duration_seconds'] as num).toInt(),
        asrModel: json['asr_model'] as String,
        hookDurationSeconds: (json['hook_duration_seconds'] as num).toInt(),
        asrReady: json['asr_ready'] == true,
        updatedAt: json['updated_at']?.toString() ?? '',
        whisperModels: (json['whisper_models'] as List? ?? [])
            .map((item) => WhisperOption(
                name: item['name'] as String, ready: item['ready'] == true))
            .toList(),
        classificationModel: Map<String, dynamic>.from(
            json['classification_model'] as Map? ?? {}),
        outcomeContexts:
            ((json['outcome_upload'] as Map?)?['contexts'] as List? ?? [])
                .map((item) => Map<String, dynamic>.from(item as Map))
                .toList(),
      );
}

class WhisperOption {
  const WhisperOption({required this.name, required this.ready});
  final String name;
  final bool ready;
}
