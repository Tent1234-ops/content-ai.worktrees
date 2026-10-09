import 'outcome_prediction.dart';

class OutcomeTrainingRun {
  OutcomeTrainingRun.fromJson(dynamic value)
      : raw = outcomeMap(value),
        id = outcomeMap(value)['run_id']?.toString() ?? '',
        status = outcomeMap(value)['status']?.toString() ?? 'unknown',
        stage = outcomeMap(value)['stage']?.toString() ?? 'unknown',
        progress = (outcomeMap(value)['progress'] as num?)?.toDouble() ?? 0,
        manifestSha256 = outcomeMap(value)['manifest_sha256']?.toString() ?? '',
        error = outcomeMap(value)['error']?.toString(),
        createdAt = DateTime.tryParse(
            outcomeMap(value)['created_at']?.toString() ?? ''),
        result = outcomeMap(outcomeMap(value)['result']);

  final String id;
  final String status;
  final String stage;
  final double progress;
  final String manifestSha256;
  final String? error;
  final DateTime? createdAt;
  final Map<String, dynamic> result;
  final Map<String, dynamic> raw;

  bool get isRunning => status == 'queued' || status == 'running';
}

class OutcomeModelSummary {
  OutcomeModelSummary.fromJson(dynamic value)
      : raw = outcomeMap(value),
        id = (outcomeMap(value)['model_id'] as num?)?.toInt() ?? 0,
        version = outcomeMap(value)['model_version']?.toString() ?? '-',
        targetVersion = outcomeMap(value)['target_version']?.toString() ?? '-',
        status = outcomeMap(value)['status']?.toString() ?? 'unknown',
        sourceKind = outcomeMap(value)['source_kind']?.toString() ?? 'unknown',
        manifestSha256 = outcomeMap(value)['manifest_sha256']?.toString() ?? '',
        protocolSha256 = outcomeMap(value)['protocol_sha256']?.toString() ?? '',
        featureSchemaSha256 =
            outcomeMap(value)['feature_schema_sha256']?.toString() ?? '',
        isActive = outcomeMap(value)['is_active'] == true,
        canActivate = outcomeMap(value)['can_activate'] == true,
        independentTestPassed =
            outcomeMap(value)['independent_test_passed'] == true,
        productionEligible = outcomeMap(value)['production_eligible'] == true,
        trainingSampleCount =
            (outcomeMap(value)['training_sample_count'] as num?)?.toInt() ?? 0,
        activationReasonCodes =
            outcomeStrings(outcomeMap(value)['activation_reason_codes']),
        metrics = outcomeMap(outcomeMap(value)['metrics']),
        metricRows = (outcomeMap(value)['metric_rows'] as List? ?? const [])
            .map(outcomeMap)
            .toList(),
        evaluatedScopes = outcomeStrings(outcomeMap(value)['evaluated_scopes']),
        artifactAvailable = outcomeMap(value)['artifact_available'] == true;

  final int id;
  final String version;
  final String targetVersion;
  final String status;
  final String sourceKind;
  final String manifestSha256;
  final String protocolSha256;
  final String featureSchemaSha256;
  final bool isActive;
  final bool canActivate;
  final bool independentTestPassed;
  final bool productionEligible;
  final int trainingSampleCount;
  final List<String> activationReasonCodes;
  final Map<String, dynamic> metrics;
  final List<Map<String, dynamic>> metricRows;
  final List<String> evaluatedScopes;
  final bool artifactAvailable;
  final Map<String, dynamic> raw;
}

class OutcomeTrainingOverview {
  OutcomeTrainingOverview.fromJson(dynamic value)
      : raw = outcomeMap(value),
        preflight = outcomeMap(outcomeMap(value)['preflight']),
        runs = (outcomeMap(value)['runs'] as List? ?? const [])
            .map(OutcomeTrainingRun.fromJson)
            .toList(),
        models = (outcomeMap(outcomeMap(value)['models'])['items'] as List? ??
                const [])
            .map(OutcomeModelSummary.fromJson)
            .toList(),
        totalModels = (outcomeMap(outcomeMap(value)['models'])['total'] as num?)
                ?.toInt() ??
            0,
        activeModel = outcomeMap(value)['active_model'] == null
            ? null
            : OutcomeModelSummary.fromJson(outcomeMap(value)['active_model']);

  final Map<String, dynamic> preflight;
  final List<OutcomeTrainingRun> runs;
  final List<OutcomeModelSummary> models;
  final int totalModels;
  final OutcomeModelSummary? activeModel;
  final Map<String, dynamic> raw;
}

String outcomeTrainingStatus(String value) => switch (value) {
      'queued' => 'รอเริ่มเทรน',
      'running' => 'กำลังเทรน',
      'preflight' => 'ตรวจความพร้อมข้อมูล',
      'training' => 'กำลังฝึกและตรวจสอบโมเดล',
      'completed' => 'เทรนและบันทึกผลแล้ว',
      'failed' => 'เทรนไม่สำเร็จ',
      'interrupted' => 'งานเทรนหยุดกลางทาง',
      'validation_passed' => 'ผ่าน Validation แต่ยังไม่ผ่าน Test อิสระ',
      'experimental' => 'หลักฐานยังไม่พอสำหรับเปิดใช้',
      'qualified' => 'ผ่านการตรวจรับสำหรับขอบเขตที่ระบุ',
      'active' => 'กำลังใช้งาน',
      _ => value,
    };

String outcomeAdminReason(String reason) => switch (reason) {
      'phase2_frozen_manifest_missing' =>
        'ยังไม่มี Frozen manifest จากชุดข้อมูล Outcome ที่ผ่านเกณฑ์',
      'manifest_hash_not_found' => 'ไม่พบ Manifest hash ที่ร้องขอ',
      'data_use_not_confirmed' =>
        'เจ้าของโครงการยังไม่ยืนยันสิทธิ์ใช้ข้อมูลสำหรับฝึกและให้บริการ',
      'data_use_unverified' =>
        'สถานะสิทธิ์ใช้ข้อมูลสำหรับฝึกและให้บริการยังไม่ยืนยัน',
      'confirmation_evidence_missing' =>
        'ยังไม่มีหลักฐานการยืนยันสิทธิ์ใช้ข้อมูลจากเจ้าของโครงการ',
      'model_not_independent_test_qualified' =>
        'โมเดลยังไม่ผ่าน Independent Test',
      'independent_test_not_passed' => 'Independent Test ยังไม่ผ่าน',
      'production_eligibility_false' => 'ยังไม่ผ่านเกณฑ์ใช้งานจริง',
      'synthetic_fixture_not_activatable' =>
        'โมเดลจากข้อมูลทดสอบเปิดใช้จริงไม่ได้',
      'model_already_active' => 'โมเดลนี้กำลังใช้งานอยู่',
      'outcome_artifact_missing' =>
        'ไม่พบไฟล์โมเดลในพื้นที่จัดเก็บที่เชื่อถือได้',
      'outcome_version_hash_invalid' => 'Hash ของรุ่นข้อมูลหรือโมเดลไม่ครบ',
      'outcome_split_hashes_incomplete' =>
        'Hash ของชุดข้อมูลแต่ละ Split ไม่ครบ',
      'outcome_evaluated_scopes_incomplete' =>
        'ผลประเมินยังไม่ครอบคลุม Scope ที่กำหนด',
      _ when reason.endsWith('_minimum_videos_not_met') =>
        'จำนวนวิดีโออิสระในชุดข้อมูลยังไม่ครบขั้นต่ำ',
      _ when reason.endsWith('_minimum_channels_not_met') =>
        'จำนวนช่องอิสระในชุดข้อมูลยังไม่ครบขั้นต่ำ',
      _ when reason.contains('format') => 'ยังขาดรูปแบบคลิปที่ยืนยันแล้ว',
      _ when reason.contains('transcript') =>
        'Transcript ยังไม่ผ่านเงื่อนไขที่กำหนด',
      _ => 'ยังไม่ผ่านเงื่อนไข: $reason',
    };

String outcomeSplitLabel(String value) => switch (value) {
      'fit' => 'Fit (ฝึกค่าของโมเดล)',
      'tuning' => 'Tuning (เลือกโมเดล)',
      'calibration' => 'Calibration (ปรับความน่าจะเป็น)',
      'independent_test' => 'Independent Test (ยังปิดอยู่)',
      _ => value,
    };
