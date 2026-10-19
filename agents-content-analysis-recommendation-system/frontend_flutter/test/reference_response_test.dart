import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:content_ai_web/models/reference_response.dart';
import 'package:content_ai_web/models/recommendation_result.dart';
import 'package:content_ai_web/screens/result_screen.dart';
import 'package:content_ai_web/widgets/reference_response_panel.dart';

Map<String, dynamic> document(int id, String videoId) => {
      'dataset_id': id,
      'source_type': 'dataset_transcript',
      'video_id': videoId,
      'source_record_id': videoId,
      'title': 'รีวิวกล้องพร้อมทดสอบภาพแสงน้อย $id',
      'url': 'https://www.youtube.com/watch?v=$videoId',
      'channel_id': 'channel-$id',
      'channel_title': 'ช่องรีวิว $id',
      'taxonomy_leaf_key': 'camera',
      'data_split': 'train',
      'transcript': 'วันนี้จะทดสอบภาพแสงน้อยในห้องเดิม',
      'published_at': '2026-09-01T12:00:00Z',
      'statistics_captured_at': '2026-10-16T09:00:00Z',
      'statistics_source': 'dataset_contents_at_analysis_time',
      'statistics': {'views': 12000, 'likes': 0, 'comments': null},
    };

Map<String, dynamic> support(int id) => {
      'dataset_id': id,
      'occurrences': [
        {'quote': 'ทดสอบภาพแสงน้อย'}
      ],
    };

Map<String, dynamic> topic(String id, List<int> ids) => {
      'topic_id': id,
      'source_type': 'transcript',
      'user': {'status': 'not_detected'},
      'support_count': 999,
      'channel_count': 999,
      'references': ids.map(support).toList(),
    };

Map<String, dynamic> fixture() => {
      'generated_at': '2026-10-16T10:00:00Z',
      'taxonomy_leaf_key': 'camera',
      'input': {'availability': 'available'},
      'reference_documents': [document(1, '12345678901')],
      'action_topics': [
        topic('low-light', [1])
      ],
    };

List<ReferenceResponseTopic> read(Map<String, dynamic> bundle) =>
    referenceResponses(bundle,
        recommendedTopics: {'low-light': 'ภาพในสภาพแสงน้อย'});

void main() {
  for (final category in ['phone', 'camera', 'laptop']) {
    test('saved evidence supports $category without cross-category fallback',
        () {
      final bundle = fixture()..['taxonomy_leaf_key'] = category;
      bundle['reference_documents'][0]['taxonomy_leaf_key'] = category;
      expect(read(bundle).single.clips.length, 1);
    });
  }
  test('uses frozen counters and real source IDs without changing the snapshot',
      () {
    final bundle = fixture();
    final before = jsonEncode(bundle);
    final result = read(bundle).single;
    expect(result.clips.length, 1);
    expect(result.knownChannelCount, 1);
    final clip = result.clips.single;
    expect(clip.views, 12000);
    expect(clip.likes, 0);
    expect(clip.comments, isNull);
    expect(clip.quote, 'ทดสอบภาพแสงน้อย');
    expect(clip.sourceUrl.toString(),
        'https://www.youtube.com/watch?v=12345678901');
    expect(clip.capturedAt, DateTime.utc(2026, 10, 16, 9));
    expect(jsonEncode(bundle), before);
  });

  test('same video cannot increase support or known channel counts', () {
    final bundle = fixture();
    (bundle['reference_documents'] as List).add(document(2, '12345678901'));
    bundle['action_topics'] = [
      topic('low-light', [1, 1, 2])
    ];
    expect(read(bundle).single.clips.length, 1);
    expect(read(bundle).single.knownChannelCount, 1);
  });

  test('renders only recommended transcript topics, in recommendation order',
      () {
    final bundle = fixture();
    bundle['action_topics'] = [
      topic('already-mentioned', [1])..['user'] = {'status': 'detected'},
      topic('metadata-only', [1])..['source_type'] = 'video_title',
      topic('unrelated', [1]),
      topic('low-light', [1]),
      topic('handling', [1]),
    ];
    final result = referenceResponses(bundle, recommendedTopics: {
      'handling': 'การจับถือ',
      'low-light': 'ภาพแสงน้อย',
      'already-mentioned': 'ซ้ำ',
      'metadata-only': 'ชื่อคลิป',
    });
    expect(result.map((row) => row.id), ['handling', 'low-light']);
  });

  for (final badDocument in <String, Map<String, dynamic>>{
    'category': {'taxonomy_leaf_key': 'phone'},
    'validation': {'data_split': 'validation'},
    'test': {'data_split': 'test'},
    'title source': {'source_type': 'video_title'},
    'identity': {'source_record_id': '98765432109'},
    'bad identity': {'video_id': 'bad'},
    'unsupported quote': {'transcript': 'Different content'},
  }.entries) {
    test('does not show unsupported evidence: ${badDocument.key}', () {
      final bundle = fixture();
      (bundle['reference_documents'][0] as Map).addAll(badDocument.value);
      expect(read(bundle).single.clips, isEmpty);
    });
  }

  test('missing and ambiguous dataset rows do not become evidence', () {
    final bundle = fixture();
    (bundle['reference_documents'] as List).add(document(1, '98765432109'));
    bundle['action_topics'] = [
      topic('low-light', [1, 99])
    ];
    expect(read(bundle).single.clips, isEmpty);
  });

  for (final timestamp in [
    null,
    'invalid',
    '2026-10-17T09:00:00Z',
    '2026-08-01T00:00:00Z'
  ]) {
    test('unverified observation time hides counters: $timestamp', () {
      final bundle = fixture();
      bundle['reference_documents'][0]['statistics_captured_at'] = timestamp;
      final clip = read(bundle).single.clips.single;
      expect(clip.capturedAt, isNull);
      expect(clip.views, isNull);
      expect(clip.likes, isNull);
      expect(clip.comments, isNull);
    });
  }

  test('missing cutoff or counter source cannot verify observations', () {
    final bundle = fixture()..remove('generated_at');
    expect(read(bundle).single.clips.single.hasStatistics, false);
    bundle['generated_at'] = '2026-10-16T10:00:00Z';
    bundle['reference_documents'][0]['statistics_source'] = null;
    expect(read(bundle).single.clips.single.hasStatistics, false);
  });

  test('invalid counters are missing, not fake zeros or rounded values', () {
    final bundle = fixture();
    bundle['reference_documents'][0]['statistics'] = {
      'views': -1,
      'likes': 1.5,
      'comments': double.nan,
    };
    expect(read(bundle).single.clips.single.hasStatistics, false);
  });

  test('legacy absent action topics can use saved legacy evidence', () {
    final bundle = fixture();
    bundle['topics'] = bundle.remove('action_topics');
    expect(read(bundle).length, 1);
    bundle['action_topics'] = [];
    expect(read(bundle), isEmpty);
  });

  test('unassessable input or missing evidence does not invent references', () {
    expect(read({}), isEmpty);
    final bundle = fixture();
    bundle['input'] = {'availability': 'partial'};
    expect(read(bundle), isEmpty);
    bundle['input'] = {'availability': 'available'};
    bundle['taxonomy_leaf_key'] = 'unknown';
    expect(read(bundle), isEmpty);
  });

  for (final width in [390.0, 1440.0]) {
    testWidgets('actual counters and all sources are accessible at $width px',
        (tester) async {
      await tester.binding.setSurfaceSize(Size(width, 1000));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final bundle = fixture();
      (bundle['reference_documents'] as List).addAll(<Map<String, dynamic>>[
        document(2, '12345678902'),
        document(3, '12345678903'),
      ]);
      bundle['action_topics'] = [
        topic('low-light', [1, 2, 3])
      ];
      await tester.pumpWidget(MaterialApp(
          home: Scaffold(
        body: SingleChildScrollView(
            child: Padding(
          padding: const EdgeInsets.all(24),
          child: ReferenceResponsePanel(
              bundle: bundle,
              recommendedTopics: const {'low-light': 'ภาพในสภาพแสงน้อย'}),
        )),
      )));
      await tester.pumpAndSettle();
      expect(find.text('12,000'), findsNWidgets(2));
      expect(find.text('0'), findsNWidgets(2));
      expect(find.text('ไม่มีข้อมูล'), findsNWidgets(2));
      expect(find.text('หลักฐานที่เปิดดูได้ 3 คลิป · ยืนยันช่องได้ 3 ช่อง'),
          findsOneWidget);
      expect(find.textContaining('ไม่ใช่เปอร์เซ็นต์ทำนาย'), findsNothing);
      final more = find.text('ดูคลิปอ้างอิงอีก 1 คลิป');
      await tester.ensureVisible(more);
      await tester.tap(more);
      await tester.pumpAndSettle();
      expect(find.text('12,000'), findsNWidgets(3));
      expect(find.byTooltip('เปิดคลิปต้นทาง รีวิวกล้องพร้อมทดสอบภาพแสงน้อย 3'),
          findsOneWidget);
      final quote = find.text('ข้อความที่พบในคลิปอ้างอิง').first;
      await tester.ensureVisible(quote);
      await tester.tap(quote);
      await tester.pumpAndSettle();
      expect(find.text('ทดสอบภาพแสงน้อย'), findsOneWidget);
      expect(find.text('Dataset #1 · Video ID 12345678901'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('withheld category cannot show reference statistics',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: ReferenceResponsePanel(
      bundle: fixture(),
      recommendedTopics: const {'low-light': 'ภาพแสงน้อย'},
      withheld: true,
    ))));
    expect(find.textContaining('หมวดหรือข้อความถอดเสียงยังไม่พร้อม'),
        findsOneWidget);
    expect(find.text('12,000'), findsNothing);
  });

  testWidgets(
      'failed source navigation reports failure and uses the stored Video ID',
      (tester) async {
    String? attemptedUrl;
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/url_launcher'), (call) async {
      if (call.method == 'launch') {
        attemptedUrl = call.arguments['url'];
        return false;
      }
      return null;
    });
    addTearDown(() => tester.binding.defaultBinaryMessenger
        .setMockMethodCallHandler(
            const MethodChannel('plugins.flutter.io/url_launcher'), null));
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
      body: SingleChildScrollView(
          child: ReferenceResponsePanel(
        bundle: fixture(),
        recommendedTopics: const {'low-light': 'ภาพแสงน้อย'},
      )),
    )));
    await tester
        .tap(find.byTooltip('เปิดคลิปต้นทาง รีวิวกล้องพร้อมทดสอบภาพแสงน้อย 1'));
    await tester.pumpAndSettle();
    expect(attemptedUrl, 'https://www.youtube.com/watch?v=12345678901');
    expect(find.text('เปิดคลิปต้นทางไม่สำเร็จ'), findsOneWidget);
  });

  testWidgets(
      'saved unavailable Outcome uses real references without a fake probability',
      (tester) async {
    final data = AnalysisResultViewData.fromJson({
      'title': 'Saved result',
      'recommendation': {
        'domain': 'camera',
        'evidence_bundle': fixture(),
        'actionable_recommendations': {
          'status': 'ready',
          'items': [
            {
              'id': 'advice',
              'evidence_topic_id': 'low-light',
              'title': 'ภาพแสงน้อย'
            }
          ],
        },
      },
      'outcome_assessment': {
        'status': 'model_unavailable',
        'probability': null
      },
    });
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: SingleChildScrollView(
      child: AnalysisReport(data: data),
    ))));
    await tester.pumpAndSettle();
    final tab = find.byKey(const ValueKey('result-tab-evidence'));
    await tester.ensureVisible(tab);
    await tester.tap(tab);
    await tester.pumpAndSettle();
    expect(find.text('ผลตอบรับจากคลิปอ้างอิง'), findsOneWidget);
    expect(find.text('12,000'), findsOneWidget);
    expect(find.byKey(const ValueKey('outcome-probability')), findsNothing);
    expect(find.text('แผนปรับคลิปของฉัน'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
