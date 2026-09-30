class ClipRevisionPlan {
  const ClipRevisionPlan(
      {required this.contentId,
      required this.analysisId,
      required this.fingerprint,
      required this.revision,
      required this.selectedIds,
      required this.notes,
      this.savedAt});
  final int contentId, analysisId, revision;
  final String fingerprint, notes;
  final List<String> selectedIds;
  final DateTime? savedAt;

  factory ClipRevisionPlan.fromJson(Map<String, dynamic> json) {
    if (json['content_id'] is! int ||
        json['analysis_id'] is! int ||
        json['revision'] is! int ||
        (json['revision'] as int) < 0 ||
        json['status'] != 'planning' ||
        json['notes'] is! String ||
        json['selected_advice_ids'] is! List ||
        !RegExp(r'^[0-9a-f]{64}$')
            .hasMatch(json['recommendation_fingerprint']?.toString() ?? '')) {
      throw const FormatException('ไม่พบข้อมูลแผนที่ยืนยันการบันทึก');
    }
    final savedAt = DateTime.tryParse(json['saved_at']?.toString() ?? '');
    if ((json['revision'] as int) > 0 && savedAt == null) {
      throw const FormatException('ไม่พบเวลายืนยันการบันทึก');
    }
    return ClipRevisionPlan(
        contentId: json['content_id'],
        analysisId: json['analysis_id'],
        fingerprint: json['recommendation_fingerprint'],
        revision: json['revision'],
        selectedIds: List<String>.from(json['selected_advice_ids']),
        notes: json['notes'],
        savedAt: savedAt);
  }

  Map<String, dynamic> request(Set<String> selected, String draftNotes) => {
        'analysis_id': analysisId,
        'recommendation_fingerprint': fingerprint,
        'expected_revision': revision,
        'selected_advice_ids': selected.toList(),
        'notes': draftNotes,
      };
}
