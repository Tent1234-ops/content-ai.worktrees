import 'package:content_ai_web/models/recommendation_result.dart';
import 'package:content_ai_web/screens/result_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  for (final includeRange in [true, false]) {
    testWidgets('duration uses measured seconds, range present=$includeRange',
        (tester) async {
      final data = AnalysisResultViewData.fromJson({
        'recommendation': {
          'domain': 'phone',
          'recommended_duration': {
            'evidence_status': 'sufficient',
            'sample_size': 12,
            'median_seconds': 112,
            'percentile_low': 25,
            'percentile_high': 75,
            if (includeRange) 'percentile_low_seconds': 77,
            if (includeRange) 'percentile_high_seconds': 136,
          },
        },
      });
      await tester.pumpWidget(MaterialApp(
          home: Scaffold(
              body: SingleChildScrollView(child: AnalysisReport(data: data)))));
      expect(
          find.text(includeRange
              ? 'ค่ากลาง 112 วินาที · ช่วง 77–136 วินาที'
              : 'ค่ากลาง 112 วินาที · ไม่ได้บันทึกช่วงความยาว'),
          findsOneWidget);
      expect(find.textContaining('ช่วง 25–75 วินาที'), findsNothing);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('missing duration is not displayed as null seconds',
      (tester) async {
    final data = AnalysisResultViewData.fromJson({
      'recommendation': {
        'recommended_duration': {'evidence_status': 'sufficient'},
      },
    });
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: SingleChildScrollView(child: AnalysisReport(data: data)))));
    expect(find.text('ข้อมูลอ้างอิงยังไม่เพียงพอ'), findsOneWidget);
    expect(find.textContaining('null วินาที'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
