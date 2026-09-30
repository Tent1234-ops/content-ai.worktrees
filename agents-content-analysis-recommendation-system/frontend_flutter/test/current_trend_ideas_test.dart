import 'package:content_ai_web/models/current_trend_ideas.dart';
import 'package:content_ai_web/models/recommendation_result.dart';
import 'package:content_ai_web/widgets/current_trend_ideas_panel.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> sample() => {
      'status': 'ready',
      'generated_at': '2026-09-25T10:00:00Z',
      'items': [
        {
          'topic': 'iPhone 27 Pro',
          'suggestion': 'ลองเปรียบเทียบประเด็นแบตเตอรี่',
          'support_count': 1,
          'expires_at': '2026-09-26T10:00:00Z',
          'user_evidence': [
            {'field': 'transcript', 'text': 'แบตเตอรี่'}
          ],
          'sources': [
            {
              'platform': 'youtube',
              'title': 'iPhone 27 Pro ทดสอบแบตเตอรี่',
              'url': 'https://www.youtube.com/watch?v=abcde123456',
              'evidence_field': 'title',
              'evidence_text': 'iPhone 27 Pro ทดสอบแบตเตอรี่',
              'observed_at': '2026-09-25T10:00:00Z',
              'published_at': '2026-09-24T10:00:00Z',
              'snapshot_run_id': 12,
              'snapshot_item_id': 30,
            }
          ],
        }
      ],
    };

void main() {
  test('legacy responses remain distinguishable from no related ideas', () {
    final result = RecommendationResult.fromJson({});
    expect(result.currentTrendIdeas.status, 'not_evaluated');
  });
  test('stored stale recommendations are not current and missing time abstains',
      () {
    final data = CurrentTrendIdeas.fromJson(sample());
    expect(data.validAt(DateTime.utc(2026, 9, 25, 12)), hasLength(1));
    expect(data.validAt(DateTime.utc(2026, 9, 27)), isEmpty);
    final missing = sample()..remove('generated_at');
    expect(
        CurrentTrendIdeas.fromJson(missing)
            .validAt(DateTime.utc(2026, 9, 25, 12)),
        isEmpty);
  });
  testWidgets(
      'ideas expose source fields times links and transcript separation',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(900, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: SingleChildScrollView(
                child: CurrentTrendIdeasPanel(
                    data: CurrentTrendIdeas.fromJson(sample()),
                    now: () => DateTime.utc(2026, 9, 25, 12))))));
    expect(find.text('ไอเดียจากกระแสล่าสุด'), findsOneWidget);
    expect(find.text('ชื่อคลิป YouTube'), findsOneWidget);
    expect(
        find.textContaining('ไม่ใช่หลักฐานคำพูดใน Transcript'), findsOneWidget);
    expect(find.byTooltip('เปิดต้นทาง'), findsOneWidget);
    expect(find.textContaining('รอบ #12 / รายการ #30'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });
  testWidgets('old result never displays a latest badge or stale suggestions',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: CurrentTrendIdeasPanel(
                data: CurrentTrendIdeas.fromJson(sample()),
                now: () => DateTime.utc(2026, 9, 27)))));
    expect(find.text('ไอเดียจากกระแสล่าสุด'), findsNothing);
    expect(find.text('iPhone 27 Pro'), findsNothing);
    expect(find.textContaining('หมดอายุแล้ว'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
