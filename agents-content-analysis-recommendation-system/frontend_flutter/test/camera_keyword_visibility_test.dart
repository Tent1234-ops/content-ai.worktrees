import 'package:content_ai_web/models/recommendation_result.dart';
import 'package:content_ai_web/screens/result_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('supported keywords remain visible with actionable advice',
      (tester) async {
    final data = AnalysisResultViewData.fromJson({
      'recommendation': {
        'domain': 'camera',
        'missing_keywords': [
          {'keyword': 'ผม', 'score': 1}
        ],
        'hook_keywords': [
          {
            'keyword': 'low light',
            'score': 1,
            'support_count': 5,
            'sample_size': 25,
            'supporting_dataset_row_ids': [1, 2, 3, 4, 5]
          }
        ],
        'actionable_recommendations': {
          'status': 'ready',
          'items': [
            {
              'id': 'advice1',
              'evidence_topic_id': 'topic1',
              'title': 'ภาพในสภาพแสงน้อย',
              'proposal': 'ลองถ่ายแสงน้อย'
            }
          ],
        },
        'evidence_bundle': {
          'action_topics': [
            {
              'topic_id': 'topic1',
              'canonical_topic': 'low light',
              'title_th': 'ภาพในสภาพแสงน้อย',
              'support_count': 5,
              'sample_size': 25,
              'supporting_dataset_row_ids': [1, 2, 3, 4, 5]
            }
          ],
        },
      },
    });
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: SingleChildScrollView(child: AnalysisReport(data: data)))));
    await tester.pumpAndSettle();
    expect(find.text('คำสำคัญที่แนะนำให้เพิ่ม'), findsOneWidget);
    expect(find.text('คำสำคัญที่เสนอสำหรับช่วงเปิดคลิป'), findsOneWidget);
    expect(find.text('ภาพในสภาพแสงน้อย'), findsNWidgets(2));
    expect(find.text('พบใน 5 จาก 25 คลิปอ้างอิง'), findsNWidgets(2));
    expect(find.text('ผม'), findsNothing);
    expect(find.text('low light'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
