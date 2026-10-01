Map<String, dynamic> trainingMap(dynamic value) =>
    Map<String, dynamic>.from(value as Map? ?? {});
List<Map<String, dynamic>> trainingRows(dynamic value) =>
    (value as List? ?? []).map(trainingMap).toList();

class TrainingRun {
  TrainingRun.fromJson(Map<String, dynamic> json)
      : id = json['run_id'] as String,
        status = json['status'] as String,
        stage = json['stage'] as String,
        modelKey = json['current_model_key'] as String?,
        error = json['error'] as String?,
        createdAt = json['created_at']?.toString() ?? '',
        result = trainingMap(json['result']);
  final String id, status, stage, createdAt;
  final String? modelKey, error;
  final Map<String, dynamic> result;
  bool get isRunning => status == 'queued' || status == 'running';
}

class TrainedModel {
  TrainedModel.fromJson(Map<String, dynamic> json)
      : id = (json['model_id'] as num).toInt(),
        key = json['model_key'] as String,
        version = json['model_version'] as String,
        status = json['status'] as String,
        isActive = json['is_active'] == true,
        canActivate = json['can_activate'] == true,
        artifactAvailable = json['artifact_available'] == true,
        sampleCount = (json['training_sample_count'] as num?)?.toInt() ?? 0,
        unknownThreshold = (json['unknown_threshold'] as num?)?.toDouble(),
        metrics = trainingRows(json['metrics']),
        qualification = trainingMap(json['qualification']),
        readiness = trainingMap(json['readiness']),
        perCategory = trainingRows(json['per_category']),
        confusionMatrices = trainingRows(json['confusion_matrices']);
  final int id, sampleCount;
  final String key, version, status;
  final bool isActive, canActivate, artifactAvailable;
  final double? unknownThreshold;
  final List<Map<String, dynamic>> metrics, perCategory, confusionMatrices;
  final Map<String, dynamic> qualification, readiness;
  Map<String, dynamic>? metric(String split, String name) {
    for (final row in metrics) {
      if (row['split'] == split && row['metric'] == name) return row;
    }
    return null;
  }
}

class TrainingOverview {
  TrainingOverview.fromJson(Map<String, dynamic> json)
      : dataset = trainingMap(json['dataset']),
        policy = trainingMap(json['policy']),
        runs = trainingRows(json['runs']).map(TrainingRun.fromJson).toList(),
        models = trainingRows(trainingMap(json['models'])['items'])
            .map(TrainedModel.fromJson)
            .toList(),
        totalModels =
            (trainingMap(json['models'])['total'] as num?)?.toInt() ?? 0,
        activeModel = json['active_model'] == null
            ? null
            : TrainedModel.fromJson(trainingMap(json['active_model']));
  final Map<String, dynamic> dataset, policy;
  final List<TrainingRun> runs;
  final List<TrainedModel> models;
  final int totalModels;
  final TrainedModel? activeModel;
}

String trainingModelName(String key) {
  if (key.contains('complement')) return 'Complement Naive Bayes';
  if (key.contains('embedding')) return 'Multilingual Embeddings';
  if (key.contains('svm')) return 'Calibrated Linear SVM';
  if (key.contains('logistic') || key.contains('logreg')) {
    return 'Tuned Logistic Regression';
  }
  return key;
}

String trainingStatus(String value) => switch (value) {
      'queued' => 'รอเริ่มเทรน',
      'running' => 'กำลังเทรน',
      'preparing' => 'ตรวจสอบและเตรียมข้อมูล',
      'cross_validation' => 'ประเมินข้ามชุดข้อมูลตามช่อง',
      'fitting' => 'ฝึกโมเดล',
      'evaluating' => 'ทดสอบโมเดลกับข้อมูลที่แยกไว้',
      'persisting' => 'บันทึกโมเดลและผลประเมิน',
      'completed' => 'เทรนและประเมินเสร็จแล้ว',
      'not_ready' => 'ข้อมูลยังไม่พร้อมเทรน',
      'failed' => 'เทรนไม่สำเร็จ',
      'interrupted' => 'งานเทรนหยุดกลางทาง',
      'qualified' => 'ผ่านเกณฑ์ที่บันทึกไว้',
      'evaluated_below_threshold' => 'ยังไม่ผ่านเกณฑ์',
      'smoke_test_only' => 'ทดลองเท่านั้น',
      _ => value,
    };

String trainingGateReason(String value) => switch (value) {
      'classification_metrics_below_threshold' =>
        'คะแนนจำแนกหมวดยังต่ำกว่าเกณฑ์',
      'phase22_collection_not_ready' =>
        'จำนวนข้อมูลหรือความหลากหลายของช่องยังไม่ครบ',
      'insufficient_out_of_scope_evaluation_samples' =>
        'ตัวอย่างทดสอบนอกขอบเขตยังไม่เพียงพอ',
      'unknown_recall_below_threshold' =>
        'การตรวจจับคลิปนอกขอบเขตยังต่ำกว่าเกณฑ์',
      'scope_validation_not_passed' =>
        'เกณฑ์รับผลจำแนกยังไม่ผ่านชุด Validation',
      'insufficient_unknown_test' =>
        'จำนวนคลิปหรือช่องในชุดทดสอบ Unknown ยังไม่ครบ',
      'unknown_test_not_passed' => 'ผลทดสอบการปฏิเสธ Unknown ยังไม่ผ่าน',
      'smoke_test_incomplete_dataset' =>
        'โมเดลทดลองจากข้อมูลไม่ครบ เปิดใช้งานไม่ได้',
      _ => value,
    };

String trainingPercent(dynamic value) =>
    value is num ? '${(value * 100).toStringAsFixed(1)}%' : '-';
String trainingDate(String value) {
  final date =
      DateTime.tryParse(value.endsWith('Z') ? value : '${value}Z')?.toLocal();
  return date == null
      ? '-'
      : '${date.day}/${date.month}/${date.year} ${date.hour.toString().padLeft(2, '0')}:${date.minute.toString().padLeft(2, '0')}';
}
