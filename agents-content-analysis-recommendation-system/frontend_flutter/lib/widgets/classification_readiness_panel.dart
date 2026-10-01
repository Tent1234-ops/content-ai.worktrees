import 'package:flutter/material.dart';

class ClassificationReadinessPanel extends StatelessWidget {
  const ClassificationReadinessPanel({super.key, required this.readiness});
  final Map<String, dynamic> readiness;

  @override
  Widget build(BuildContext context) {
    final status = readiness['status'];
    final ready = status == 'ready';
    final reasons = (readiness['reason_codes'] as List? ?? [])
        .map((value) => _reason(value.toString()))
        .toList();
    final colors = Theme.of(context).colorScheme;
    return Semantics(
      container: true,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 12),
        child:
            Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Icon(
                ready
                    ? Icons.check_circle_outline
                    : Icons.warning_amber_rounded,
                color: ready ? colors.primary : colors.error,
                size: 22),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                ready
                    ? 'เกณฑ์รับผลจำแนกพร้อมใช้งาน'
                    : status == 'unvalidated'
                        ? 'ยังไม่ยืนยันความพร้อม: ปิดการบังคับตรวจคลิปนอกขอบเขต'
                        : status == 'blocked'
                            ? 'ยังไม่พร้อมให้คำแนะนำเฉพาะหมวด'
                            : 'ยังไม่มีข้อมูลตรวจความพร้อมของโมเดล',
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ),
          ]),
          if (ready)
            const Padding(
              padding: EdgeInsets.only(top: 8),
              child: Text(
                  'แต่ละคลิปยังต้องผ่านการตรวจรับผลและมีข้อมูลอ้างอิงเพียงพอ ไม่ใช่การรับรองคุณภาพคำแนะนำหรือยอดตอบรับ'),
            ),
          ...reasons.map((reason) => Padding(
              padding: const EdgeInsets.only(top: 8), child: Text(reason))),
          if (readiness.isNotEmpty) ...[
            const SizedBox(height: 8),
            Wrap(spacing: 24, runSpacing: 8, children: [
              Text(
                  'ไฟล์โมเดล: ${readiness['artifact_loadable'] == true ? 'โหลดได้' : 'ยังไม่พร้อม'}'),
              Text(
                  'เกณฑ์ปฏิเสธนอกขอบเขต: ${readiness['scope_policy_valid'] == true ? 'ผ่าน Validation' : 'ยังไม่ผ่านการตรวจรับ'}'),
            ]),
          ],
        ]),
      ),
    );
  }
}

String _reason(String code) => switch (code) {
      'no_active_model' => 'ยังไม่มีโมเดลที่ผ่านเกณฑ์และเปิดใช้งาน',
      'artifact_unavailable' =>
        'ไฟล์โมเดลหาย โหลดไม่ได้ หรือไม่ตรงกับทะเบียนโมเดล',
      'artifact_registry_mismatch' =>
        'ไฟล์โมเดลไม่ตรงกับรุ่นในทะเบียน จึงนำไปวิเคราะห์ไม่ได้',
      'smoke_test_only' =>
        'ไฟล์นี้เป็นโมเดลทดลองระบบเท่านั้น ไม่ใช่รุ่นสำหรับวิเคราะห์จริง',
      'model_not_qualified' => 'โมเดลนี้ยังไม่ผ่านเกณฑ์เปิดใช้งาน',
      'scope_policy_missing' =>
        'โมเดลนี้ยังไม่มีเกณฑ์ปฏิเสธคลิปนอกขอบเขต ระบบจึงงดคำแนะนำเฉพาะหมวดเมื่อบังคับตรวจรับผล',
      'scope_policy_not_validated' =>
        'เกณฑ์ปฏิเสธคลิปนอกขอบเขตยังไม่ผ่าน Validation หรือใช้กับระบบรุ่นนี้ไม่ได้',
      'scope_validation_disabled' =>
        'ระบบไม่ได้บังคับใช้เกณฑ์ปฏิเสธคลิปนอกขอบเขต จึงยังไม่ถือว่าพร้อมสำหรับใช้งานจริง',
      _ => 'ยังมีเงื่อนไขที่ต้องตรวจสอบ ($code)',
    };
