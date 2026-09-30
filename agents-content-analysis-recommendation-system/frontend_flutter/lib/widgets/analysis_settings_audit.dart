import 'package:flutter/material.dart';

class AnalysisSettingsAudit extends StatelessWidget {
  const AnalysisSettingsAudit({super.key, required this.snapshot});
  final Map<String, dynamic> snapshot;

  @override
  Widget build(BuildContext context) {
    final model = snapshot['classification_model'] as Map? ?? const {};
    final threshold = model['unknown_threshold'] as num?;
    final captured =
        DateTime.tryParse(snapshot['captured_at']?.toString() ?? '')?.toLocal();
    final rows = <String, String>{
      'ความยาวอัปโหลดสูงสุด':
          '${snapshot['upload_max_duration_seconds']} วินาที',
      'โมเดลถอดเสียง': 'Whisper ${snapshot['asr_model']}',
      'ช่วงเปิดคลิป (Hook)': '${snapshot['hook_duration_seconds']} วินาที',
      'โมเดลจำแนกหมวด': model['model_id'] == null
          ? 'ไม่มีโมเดลที่เปิดใช้งานตอนรับงาน'
          : '#${model['model_id']} · ${model['model_key']} · ${model['model_version']}',
      if (threshold != null)
        'เกณฑ์ Unknown ของโมเดล': '${(threshold * 100).toStringAsFixed(1)}%',
      if (captured != null) 'รับงานเมื่อ': captured.toString().split('.').first,
      if (model['artifact_sha256'] != null)
        'รหัสตรวจไฟล์โมเดล (SHA-256)': model['artifact_sha256'].toString(),
    };
    return ExpansionTile(
      tilePadding: EdgeInsets.zero,
      leading: const Icon(Icons.tune),
      title: const Text('การตั้งค่าที่ใช้วิเคราะห์ครั้งนี้'),
      children: [
        if (snapshot.isEmpty)
          const ListTile(title: Text('ผลเก่านี้ยังไม่ได้บันทึกการตั้งค่า'))
        else
          ...rows.entries.map((row) => Padding(
                padding: const EdgeInsets.symmetric(vertical: 8),
                child: Align(
                    alignment: Alignment.centerLeft,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(row.key,
                            style: Theme.of(context).textTheme.labelLarge),
                        SelectableText(row.value)
                      ],
                    )),
              )),
      ],
    );
  }
}
