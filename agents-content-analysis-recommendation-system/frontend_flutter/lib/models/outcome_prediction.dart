Map<String, dynamic> outcomeMap(dynamic value) =>
    value is Map ? Map<String, dynamic>.from(value) : <String, dynamic>{};

List<String> outcomeStrings(dynamic value) =>
    (value as List? ?? const []).map((item) => item.toString()).toList();

double? _probability(dynamic value) {
  final parsed = value is num ? value.toDouble() : double.tryParse('$value');
  if (parsed == null || !parsed.isFinite || parsed < 0 || parsed > 1) {
    return null;
  }
  return parsed;
}

class OutcomeAssessment {
  const OutcomeAssessment({
    required this.status,
    required this.reasonCodes,
    required this.probability,
    required this.context,
    required this.evaluatedScope,
    required this.supportSummary,
    required this.evidenceTopicIds,
    required this.limitations,
    required this.targetVersion,
    required this.protocolVersion,
    required this.featureVersion,
    required this.modelVersion,
    required this.modelId,
    required this.referenceCutoff,
    required this.assessedAt,
    required this.fixtureOnly,
    required this.raw,
  });

  final String status;
  final List<String> reasonCodes;
  final double? probability;
  final Map<String, dynamic> context;
  final Map<String, dynamic> evaluatedScope;
  final Map<String, dynamic> supportSummary;
  final List<String> evidenceTopicIds;
  final List<String> limitations;
  final String targetVersion;
  final String protocolVersion;
  final String featureVersion;
  final String modelVersion;
  final int? modelId;
  final DateTime? referenceCutoff;
  final DateTime? assessedAt;
  final bool fixtureOnly;
  final Map<String, dynamic> raw;

  bool get isAvailable => status == 'available' && probability != null;
  bool get isLegacy => status == 'legacy_not_assessed';

  factory OutcomeAssessment.fromJson(dynamic value) {
    final json = outcomeMap(value);
    if (json.isEmpty) return OutcomeAssessment.legacy();
    final status = json['status']?.toString().trim();
    return OutcomeAssessment(
      status: status == null || status.isEmpty ? 'legacy_not_assessed' : status,
      reasonCodes: outcomeStrings(json['reason_codes']),
      probability: _probability(json['probability']),
      context: outcomeMap(json['context']),
      evaluatedScope: outcomeMap(json['evaluated_scope']),
      supportSummary: outcomeMap(json['support_summary']),
      evidenceTopicIds: outcomeStrings(json['evidence_topic_ids']),
      limitations: outcomeStrings(json['limitations']),
      targetVersion: json['target_version']?.toString() ?? '',
      protocolVersion: json['protocol_version']?.toString() ?? '',
      featureVersion: json['feature_version']?.toString() ?? '',
      modelVersion: json['model_version']?.toString() ?? '',
      modelId: (json['model_id'] as num?)?.toInt(),
      referenceCutoff:
          DateTime.tryParse(json['reference_cutoff']?.toString() ?? ''),
      assessedAt: DateTime.tryParse(json['assessed_at']?.toString() ?? ''),
      fixtureOnly: json['fixture_only'] == true,
      raw: json,
    );
  }

  factory OutcomeAssessment.legacy() => const OutcomeAssessment(
        status: 'legacy_not_assessed',
        reasonCodes: ['saved_before_outcome_assessment_v1'],
        probability: null,
        context: {},
        evaluatedScope: {},
        supportSummary: {},
        evidenceTopicIds: [],
        limitations: [],
        targetVersion: '',
        protocolVersion: '',
        featureVersion: '',
        modelVersion: '',
        modelId: null,
        referenceCutoff: null,
        assessedAt: null,
        fixtureOnly: false,
        raw: {},
      );
}

class OutcomeScenario {
  const OutcomeScenario({
    required this.status,
    required this.reasonCodes,
    required this.hypothetical,
    required this.probabilityBefore,
    required this.probabilityAfter,
    required this.deltaPercentagePoints,
    required this.limitation,
    required this.raw,
  });

  final String status;
  final List<String> reasonCodes;
  final bool hypothetical;
  final double? probabilityBefore;
  final double? probabilityAfter;
  final double? deltaPercentagePoints;
  final String limitation;
  final Map<String, dynamic> raw;

  bool get isAvailable =>
      status == 'available' &&
      hypothetical &&
      probabilityBefore != null &&
      probabilityAfter != null &&
      deltaPercentagePoints != null;

  factory OutcomeScenario.fromJson(dynamic value) {
    final json = outcomeMap(value);
    final delta = json['delta_percentage_points'] is num
        ? (json['delta_percentage_points'] as num).toDouble()
        : double.tryParse('${json['delta_percentage_points']}');
    return OutcomeScenario(
      status: json['status']?.toString() ?? 'error',
      reasonCodes: outcomeStrings(json['reason_codes']),
      hypothetical: json['hypothetical'] == true,
      probabilityBefore: _probability(json['probability_before']),
      probabilityAfter: _probability(json['probability_after']),
      deltaPercentagePoints: delta != null && delta.isFinite ? delta : null,
      limitation: json['limitation']?.toString() ?? '',
      raw: json,
    );
  }
}

String outcomeStatusMessage(String status) => switch (status) {
      'available' => 'มีค่าประเมินจากโมเดลที่ผ่านเกณฑ์',
      'insufficient_data' =>
        'หลักฐานในกลุ่มอ้างอิงยังไม่เพียงพอสำหรับประเมินผลตอบรับ',
      'unsupported_context' => 'ยังไม่มีกลุ่มอ้างอิงที่รองรับบริบทของคลิปนี้',
      'unassessable_transcript' =>
        'ข้อความถอดเสียงยังไม่พร้อมสำหรับประเมินผลตอบรับ',
      'classification_withheld' =>
        'ยังไม่ประเมินผลตอบรับ เพราะหมวดของคลิปไม่ผ่านเกณฑ์ตรวจรับ',
      'model_unavailable' => 'ยังไม่มีโมเดลประเมินผลตอบรับที่เปิดใช้งาน',
      'model_unqualified' => 'โมเดลประเมินผลตอบรับยังไม่ผ่านการทดสอบอิสระ',
      'data_use_unverified' =>
        'ยังไม่ประเมินผลตอบรับ เพราะสิทธิ์ใช้ข้อมูลสำหรับโมเดลยังไม่ยืนยัน',
      'legacy_not_assessed' => 'ผลนี้ยังไม่มีการประเมินผลตอบรับ',
      'withdrawn' => 'หลักฐานของผลประเมินนี้ถูกถอนออกแล้ว',
      'inaccessible' => 'ไม่สามารถเข้าถึงหลักฐานของผลประเมินนี้ได้',
      'error' => 'ระบบประเมินผลตอบรับไม่สำเร็จ แต่ผลวิเคราะห์ส่วนอื่นยังใช้ได้',
      _ => 'ยังไม่สามารถประเมินผลตอบรับสำหรับผลนี้ได้',
    };

String outcomeReasonMessage(String reason) {
  if (reason.startsWith('parent:') || reason.startsWith('child:')) {
    return 'ผลต้นฉบับหรือฉบับใหม่ยังไม่มีค่าประเมินที่พร้อมเปรียบเทียบ';
  }
  if (reason.startsWith('outcome_') && reason.endsWith('_mismatch')) {
    return 'รุ่นโมเดล วิธีวิเคราะห์ หรือบริบทอ้างอิงของสองผลไม่ตรงกัน';
  }
  if (reason.startsWith('paired_evidence_not_supported:')) {
    return 'หัวข้อนี้ยังไม่มีกลุ่มคลิปที่พูดถึงและไม่พูดถึงมากพอสำหรับจำลอง';
  }
  return switch (reason) {
    'saved_before_outcome_assessment_v1' =>
      'บันทึกผลก่อนระบบประเมินผลตอบรับรุ่นนี้',
    'data_use_not_confirmed' => 'สิทธิ์ใช้ข้อมูลสำหรับโมเดลยังไม่ยืนยัน',
    'confirmation_evidence_missing' =>
      'ยังไม่มีหลักฐานยืนยันสิทธิ์ใช้ข้อมูลสำหรับสร้างโมเดล',
    'data_use_unverified' =>
      'สถานะสิทธิ์ใช้ข้อมูลสำหรับสร้างโมเดลยังไม่ได้รับการยืนยัน',
    'phase2_frozen_manifest_missing' =>
      'ยังไม่มีชุดข้อมูล Outcome ที่ผ่านการตรึงและตรวจสอบ',
    'active_outcome_model_missing' =>
      'ยังไม่มีโมเดลประเมินผลตอบรับที่เปิดใช้งาน',
    'model_not_independent_test_qualified' => 'โมเดลยังไม่ผ่านชุดทดสอบอิสระ',
    'independent_test_not_passed' => 'ผลชุดทดสอบอิสระยังไม่ผ่าน',
    'production_eligibility_false' => 'โมเดลยังไม่พร้อมใช้งานจริง',
    'confirmed_format_required' => 'ยังไม่ได้ยืนยันรูปแบบคลิปสั้นหรือคลิปยาว',
    'reference_age_context_required' => 'ยังไม่ได้ระบุช่วงอายุของคลิปอ้างอิง',
    'asr_or_transcript_unassessable' =>
      'ข้อความถอดเสียงของฉบับใดฉบับหนึ่งตรวจสอบไม่ได้',
    'outcome_probability_missing' => 'ผลใดผลหนึ่งไม่มีค่าประเมินที่ตรวจรับแล้ว',
    _ => 'ยังไม่ผ่านเงื่อนไขตรวจรับของระบบ',
  };
}

String outcomeFormatLabel(String value) => switch (value) {
      'short_form' => 'คลิปสั้น',
      'long_form' => 'คลิปยาว',
      _ => value.isEmpty ? 'ไม่ได้ระบุรูปแบบ' : value,
    };

String outcomeAgeLabel(String value) {
  final normalized = value.toLowerCase().replaceAll('to', '-');
  if (RegExp(r'(^|\D)0[_ -]+7(\D|$)').hasMatch(normalized)) {
    return 'อายุคลิป 0–7 วัน';
  }
  if (RegExp(r'(^|\D)7[_ -]+30(\D|$)').hasMatch(normalized)) {
    return 'อายุคลิป 7–30 วัน';
  }
  if (RegExp(r'(^|\D)30[_ -]+90(\D|$)').hasMatch(normalized)) {
    return 'อายุคลิป 30–90 วัน';
  }
  if (RegExp(r'(^|\D)90[_ -]+365(\D|$)').hasMatch(normalized)) {
    return 'อายุคลิป 90–365 วัน';
  }
  if (normalized.contains('365')) return 'อายุคลิป 365 วันขึ้นไป';
  return value.isEmpty ? 'ไม่ได้ระบุช่วงอายุ' : value;
}
