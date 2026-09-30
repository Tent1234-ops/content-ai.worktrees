import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:content_ai_web/models/recommendation_result.dart';
import 'package:content_ai_web/screens/result_screen.dart';
import 'package:content_ai_web/widgets/recommendation_evidence_panel.dart';

Map<String, dynamic> _bundle() => {
      'schema_version': 'recommendation-evidence-v1',
      'method_version': 'transcript-gap-source-spans-v1',
      'synonym_version': 'a' * 64,
      'data_fingerprint': 'b' * 64,
      'canonicalization': 'curated_synonyms',
      'generated_at': '2026-09-28T10:00:00Z',
      'input': {
        'availability': 'available',
        'segments': [],
        'hook_seconds': 60
      },
      'topics': [
        {
          'topic_id': 'battery',
          'canonical_topic': 'battery life',
          'synonyms': ['battery', 'แบตเตอรี่'],
          'support_count': 1,
          'channel_count': 1,
          'user': {'status': 'not_detected', 'occurrences': []},
          'user_hook': {'status': 'unassessable', 'occurrences': []},
          'references': [
            {
              'dataset_id': 99,
              'frequency': 1,
              'occurrences': [
                {
                  'quote': 'แบตเตอรี่ใช้งานได้นานตลอดวัน',
                  'matched_text': 'แบตเตอรี่',
                  'timestamp': null
                },
              ]
            }
          ],
        }
      ],
      'reference_documents': [
        {
          'dataset_id': 99,
          'title': 'คลิปต้นแบบทดสอบ',
          'channel_title': 'ช่องทดสอบ',
          'statistics': {'views': 2000, 'likes': 0, 'comments': null},
          'statistics_captured_at': '2026-09-27T08:00:00Z',
          'published_at': '2026-09-01T08:00:00Z',
          'dataset_version': 'fixture-v1',
          'video_id': 'fixture01',
        }
      ],
    };

void main() {
  testWidgets(
      'legacy recomputation is visibly distinguished from saved evidence',
      (tester) async {
    final bundle = _bundle()..['origin'] = 'recomputed_legacy_not_original';
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: SingleChildScrollView(
      child: RecommendationEvidencePanel(bundle: bundle),
    ))));
    expect(find.textContaining('ไม่ใช่หลักฐานที่เก็บในวันวิเคราะห์เดิม'),
        findsOneWidget);
  });
  testWidgets(
      'evidence exposes actual quote, unknown time, missing counter and provenance',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1000, 950));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: SingleChildScrollView(
      child: RecommendationEvidencePanel(bundle: _bundle()),
    ))));
    await tester.tap(find.text('battery life'));
    await tester.pumpAndSettle();
    expect(find.text('ช่วงเปิดคลิป: ตรวจไม่ได้จากข้อมูลที่มี'), findsOneWidget);
    await tester.tap(find.text('คลิปต้นแบบทดสอบ'));
    await tester.pumpAndSettle();
    expect(find.textContaining('แบตเตอรี่ใช้งานได้นานตลอดวัน'), findsOneWidget);
    expect(find.text('ไม่มี Timestamp จากต้นทาง'), findsOneWidget);
    expect(find.text('ยอดวิว 2000 · ไลก์ 0 · ความคิดเห็น ไม่มีข้อมูล'),
        findsOneWidget);
    expect(find.text('เวอร์ชัน Dataset: fixture-v1'), findsOneWidget);
    await tester.ensureVisible(find.text('เวอร์ชันและเวลาของหลักฐาน'));
    await tester.tap(find.text('เวอร์ชันและเวลาของหลักฐาน'));
    await tester.pumpAndSettle();
    expect(find.textContaining('รหัสข้อมูล:'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
      'failed ASR is unassessable, never presented as user omitted a topic',
      (tester) async {
    final bundle = _bundle();
    bundle['input'] = {'availability': 'unavailable', 'segments': []};
    final data = AnalysisResultViewData.fromJson({
      'title': 'Failed audio',
      'recommendation': {
        'domain': 'phone',
        'evidence_bundle': bundle,
      }
    });
    expect(data.recommendation.evidenceBundle, bundle);
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: SingleChildScrollView(
      child: AnalysisReport(data: data),
    ))));
    expect(
        find.text('ข้อความถอดเสียงยังไม่สมบูรณ์ จึงยังสรุปประเด็นในคลิปไม่ได้'),
        findsOneWidget);
    await tester.tap(find.text('คำสำคัญและข้อความถอดเสียง'));
    await tester.pumpAndSettle();
    expect(find.text('ตรวจคำสำคัญไม่ได้ เพราะข้อความถอดเสียงไม่สมบูรณ์'),
        findsOneWidget);
    expect(
        find.text(
            'ตรวจช่วงเปิดไม่ได้ เพราะไม่มีข้อความถอดเสียงพร้อมเวลาที่เพียงพอ'),
        findsOneWidget);
    expect(
        find.text(
            'งดข้อเสนอให้เพิ่มหัวข้อ เพราะข้อความถอดเสียงไม่สมบูรณ์ จึงยังสรุปไม่ได้ว่าผู้ใช้ไม่ได้พูดเรื่องนั้น'),
        findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
