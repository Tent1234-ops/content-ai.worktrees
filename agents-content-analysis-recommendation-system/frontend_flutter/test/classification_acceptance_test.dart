import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:content_ai_web/models/recommendation_result.dart';
import 'package:content_ai_web/screens/result_screen.dart';
import 'package:content_ai_web/ui/app_theme.dart';

void main() {
  testWidgets('unvalidated high confidence is not described as low confidence',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1100, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final data = AnalysisResultViewData.fromJson({
      'transcript': 'ข้อความถอดเสียงเดิม',
      'recommendation': {
        'domain': 'unknown',
        'classification': {
          'domain': 'unknown',
          'taxonomy_leaf_key': 'unknown',
          'is_unknown': true,
          'raw_taxonomy_leaf_key': 'phone',
          'confidence': 0.99,
          'acceptance': {'reason': 'scope_validation_unavailable'},
          'warning': 'โมเดลยังไม่มีผลประเมินการปฏิเสธคลิปนอกขอบเขต',
        },
        'missing_keywords': [],
        'hook_keywords': [],
        'dataset_profile': {'sample_size': 0},
      }
    });
    await tester.pumpWidget(MaterialApp(
        theme: buildAppTheme(Brightness.light),
        home: Scaffold(
            body: SingleChildScrollView(child: AnalysisReport(data: data)))));
    await tester.pumpAndSettle();
    expect(find.textContaining('งดคำแนะนำเฉพาะหมวด'), findsOneWidget);
    expect(find.textContaining('ยังไม่มั่นใจพอ'), findsNothing);
    expect(find.text('ยังไม่ยืนยันหมวดหมู่สำหรับสร้างคำแนะนำ'), findsOneWidget);
    expect(find.textContaining('ยังไม่มีข้อมูลคลิปอ้างอิงในหมวดนี้เพียงพอ'),
        findsNothing);
    await tester.tap(find.text('ผลทายก่อนตรวจรับ'));
    await tester.pumpAndSettle();
    expect(find.textContaining('99.0%'), findsOneWidget);
    expect(find.textContaining('ไม่ใช้เลือกคลิปอ้างอิง'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  test('historical classification payloads remain readable', () {
    final value =
        ClassificationResult.fromJson({'domain': 'phone', 'confidence': 0.98});
    expect(value.rawTaxonomyLeafKey, isEmpty);
    expect(value.acceptanceReason, isEmpty);
  });
}
