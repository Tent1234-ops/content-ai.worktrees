import 'package:content_ai_web/widgets/classification_readiness_panel.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('presentation remains visibly unqualified with an expiry',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(
        home: Scaffold(
            body: ClassificationReadinessPanel(readiness: {
      'status': 'presentation',
      'artifact_loadable': true,
      'scope_policy_valid': false,
      'presentation_expires_at': '2026-10-06T14:00:00.915985+00:00',
      'reason_codes': [
        'model_not_qualified',
        'scope_policy_not_validated',
        'presentation_unqualified'
      ],
    }))));
    expect(find.text('เปิดใช้ชั่วคราวสำหรับสาธิต ยังไม่ผ่านเกณฑ์ 80%'),
        findsOneWidget);
    expect(find.textContaining('ใช้สาธิตได้ถึง:'), findsOneWidget);
    expect(find.textContaining('06/10/2026'), findsOneWidget);
    expect(find.textContaining('.915985'), findsNothing);
    expect(find.textContaining('หรือใช้กับระบบรุ่นนี้ไม่ได้'), findsNothing);
    expect(find.textContaining('อนุญาตเฉพาะการสาธิตชั่วคราว'), findsOneWidget);
    expect(find.text('เกณฑ์รับผลจำแนกพร้อมใช้งาน'), findsNothing);
    expect(find.textContaining('ยังไม่ได้ตรวจรับกับชุด Test'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
  for (final width in [1000.0, 1440.0]) {
    testWidgets('readiness wraps at desktop width $width', (tester) async {
      tester.view.physicalSize = Size(width, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      for (final code in [
        'scope_policy_missing',
        'scope_policy_not_validated',
        'artifact_unavailable'
      ]) {
        await tester.pumpWidget(MaterialApp(
            home: Scaffold(
                body: SizedBox(
          width: width / 2,
          child: ClassificationReadinessPanel(readiness: {
            'status': 'blocked',
            'artifact_loadable': code != 'artifact_unavailable',
            'scope_policy_valid': false,
            'reason_codes': [code],
          }),
        ))));
        expect(find.text('ยังไม่พร้อมให้คำแนะนำเฉพาะหมวด'), findsOneWidget);
        expect(tester.takeException(), isNull);
      }
    });
  }
  testWidgets('ready is conditional and old responses stay unconfirmed',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(
        home: Scaffold(
            body:
                ClassificationReadinessPanel(readiness: {'status': 'ready'}))));
    expect(find.text('เกณฑ์รับผลจำแนกพร้อมใช้งาน'), findsOneWidget);
    expect(find.textContaining('ไม่ใช่การรับรอง'), findsOneWidget);
    await tester.pumpWidget(const MaterialApp(
        home: Scaffold(body: ClassificationReadinessPanel(readiness: {}))));
    expect(find.text('ยังไม่มีข้อมูลตรวจความพร้อมของโมเดล'), findsOneWidget);
    expect(find.text('เกณฑ์รับผลจำแนกพร้อมใช้งาน'), findsNothing);
  });
}
