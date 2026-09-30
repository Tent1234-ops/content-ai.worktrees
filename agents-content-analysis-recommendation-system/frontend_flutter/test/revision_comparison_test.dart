import 'package:content_ai_web/widgets/revision_comparison_panel.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> comparisonFixture({String status = 'ready'}) => {
      'status': status,
      'method_status': 'derived_same_matcher',
      'parent': {
        'content_id': 41,
        'title': 'รีวิวโทรศัพท์ฉบับต้นฉบับ',
        'created_at': '2026-09-29T10:00:00Z',
      },
      'child': {
        'content_id': 42,
        'title': 'รีวิวโทรศัพท์ฉบับแก้ไข',
        'created_at': '2026-09-30T10:00:00Z',
      },
      'plan': {
        'revision': 2,
        'saved_at': '2026-09-29T12:00:00Z',
      },
      'topics': [
        {
          'title': 'แบตเตอรี่',
          'message': 'ตรวจพบการกล่าวถึงในฉบับใหม่',
          'automatic_completion': false,
          'before': {
            'status': 'not_detected',
            'occurrences': [],
            'context': {'status': 'unclear'},
          },
          'after': {
            'status': 'detected',
            'occurrences': [
              {
                'quote': 'ทดสอบแบตเตอรี่ด้วยการเล่นเกมต่อเนื่อง',
                'timestamp': {'start_seconds': 74.5, 'end_seconds': 81.0},
              }
            ],
            'context': {'status': 'context_present'},
          },
        },
        {
          'title': 'การระบายความร้อน',
          'message': 'ข้อมูลยังไม่พอเปรียบเทียบ',
          'before': {
            'status': 'detected',
            'occurrences': [],
            'context': {'status': 'keyword_only'},
          },
          'after': {
            'status': 'unassessable',
            'occurrences': [],
            'context': {'status': 'unclear'},
          },
        }
      ],
      'limitations': [
        'ผลนี้ตรวจเฉพาะการเปลี่ยนแปลงของข้อความ ไม่ใช่คะแนนคุณภาพ',
      ],
    };

Future<void> mount(WidgetTester tester, double width,
    {String status = 'ready'}) async {
  await tester.binding.setSurfaceSize(Size(width, 900));
  await tester.pumpWidget(MaterialApp(
      home: Scaffold(
          body: SingleChildScrollView(
              child: RevisionComparisonPanel(
                  data: comparisonFixture(status: status))))));
  await tester.pumpAndSettle();
}

void main() {
  for (final width in [1000.0, 1440.0]) {
    testWidgets('shows before after evidence without a success score at $width',
        (tester) async {
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await mount(tester, width);
      expect(find.text('การเปลี่ยนแปลงเนื้อหา'), findsOneWidget);
      expect(find.text('ตรวจพบการกล่าวถึงในฉบับใหม่'), findsOneWidget);
      expect(find.text('พบคำพร้อมบริบทใกล้เคียง'), findsOneWidget);
      expect(find.textContaining('74.5 วินาที'), findsOneWidget);
      expect(find.textContaining('100%'), findsNothing);
      expect(find.textContaining('ปรับสำเร็จ'), findsNothing);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('withheld category is explicit and does not show topic claims',
      (tester) async {
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await mount(tester, 1000, status: 'withheld_category');
    expect(find.textContaining('งดสรุปการเปลี่ยนแปลง'), findsOneWidget);
    expect(find.text('ตรวจพบการกล่าวถึงในฉบับใหม่'), findsNothing);
  });

  testWidgets('notes-only result explains why no automatic comparison exists',
      (tester) async {
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await mount(tester, 1000, status: 'no_topics_selected');
    expect(find.textContaining('แผนนี้มีเฉพาะบันทึก'), findsOneWidget);
  });
}
