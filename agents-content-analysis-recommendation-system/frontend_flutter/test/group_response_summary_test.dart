import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:content_ai_web/models/actionable_recommendations.dart';
import 'package:content_ai_web/models/reference_response.dart';
import 'package:content_ai_web/widgets/reference_response_panel.dart';
import 'reference_response_test.dart' as references;

Map<String, dynamic> fixture() {
  final bundle = references.fixture();
  final records = List.generate(4, (index) {
    final id = 'video00000${index + 1}';
    return {
      'video_id': id,
      'source_record_id': id,
      'taxonomy_leaf_key': 'camera',
      'data_split': 'train',
      'channel_id': index.isEven ? 'a' : 'b',
      'sampling_frame': 'general_protocol_v1',
      'collection_strategy': 'classification_diverse',
      'comparison_eligible': true,
      'format_group': 'long_form',
      'format_source': 'raw_metadata.content_format',
      'age_group': 'age_30_90d',
      'published_at': '2026-09-01T00:00:00Z',
      'view_metric_version': 'youtube_play_start_view_v2',
      'topic_status': index < 2 ? 'detected' : 'not_detected',
      'occurrences': index < 2
          ? [
              {'quote': 'ภาพแสงน้อย'}
            ]
          : [],
      'latest_observation': {
        'observation_id': index + 1,
        'video_id': id,
        'observed_at': '2026-10-16T09:00:00Z',
        'status': 'complete',
        'views': [100, 300, 200, 400][index],
        'view_metric_version': 'youtube_play_start_view_v2',
      },
    };
  });
  bundle['topic_comparisons'] = {
    'as_of': '2026-10-16T10:00:00Z',
    'items': [
      {
        'evidence_topic_id': 'low-light',
        'records': records,
        'group_response_summary': {
          'schema_version': 'historical-group-response-v1',
          'as_of': '2026-10-16T10:00:00Z',
          'status': 'available',
          'is_prediction': false,
          'causal_claim': false,
          'groups': [
            {
              'category': 'camera',
              'format': 'long_form',
              'age_group': 'age_30_90d',
              'view_metric_version': 'youtube_play_start_view_v2',
              'sample_size': 2,
              'passing_count': 1,
              'channel_count': 2,
              'percentage': 50,
              'threshold_views': 200,
              'benchmark_sample_size': 4,
              'benchmark_channel_count': 2,
              'video_ids': ['video000001', 'video000002'],
              'passing_video_ids': ['video000002'],
              'benchmark_video_ids': records.map((r) => r['video_id']).toList(),
              'observed_from': '2026-10-16T09:00:00Z',
              'observed_until': '2026-10-16T09:00:00Z',
            }
          ],
        },
      }
    ],
  };
  return jsonDecode(jsonEncode(bundle)) as Map<String, dynamic>;
}

Map<String, dynamic> item(Map<String, dynamic> data) =>
    data['topic_comparisons']['items'][0] as Map<String, dynamic>;
Map<String, dynamic> group(Map<String, dynamic> data) =>
    item(data)['group_response_summary']['groups'][0] as Map<String, dynamic>;
List<ReferenceResponseGroup> read(Map<String, dynamic> data) =>
    references.read(data).single.groups;

void main() {
  test('uses frozen observations and verifies X N Y Z against real member IDs',
      () {
    final data = fixture();
    final before = jsonEncode(data);
    final result = read(data).single;
    expect(result.passingCount, 1);
    expect(result.sampleSize, 2);
    expect(result.percentage, '50');
    expect(result.channelCount, 2);
    expect(result.benchmarkSize, 4);
    expect(result.thresholdViews, 200);
    expect(result.members.last.sourceUrl.toString(),
        'https://www.youtube.com/watch?v=video000002');
    expect(jsonEncode(data), before);
  });

  test('legacy evidence never becomes a guessed percentage', () {
    expect(references.read(references.fixture()).single.groups, isEmpty);
  });

  for (final change in <String, dynamic>{
    'passing_count': 2,
    'sample_size': 100,
    'channel_count': 3,
    'percentage': 70,
    'threshold_views': null,
    'benchmark_sample_size': 10,
    'benchmark_channel_count': 9,
    'format': 'unknown',
    'category': 'phone',
    'view_metric_version': 'unknown',
    'observed_until': '2027-01-01T00:00:00Z',
    'video_ids': ['video000001', 'video000001'],
    'passing_video_ids': ['video000001'],
  }.entries) {
    test('rejects inconsistent saved summary ${change.key}', () {
      final data = fixture();
      group(data)[change.key] = change.value;
      expect(read(data), isEmpty);
    });
  }

  for (final change in <String, dynamic>{
    'data_split': 'test',
    'sampling_frame': 'high_response_protocol_v1',
    'collection_strategy': 'recommendation_high_performance',
    'format_group': 'short_form',
    'taxonomy_leaf_key': 'phone',
    'channel_id': '',
    'comparison_eligible': false,
    'occurrences': [],
  }.entries) {
    test('rejects inconsistent group member ${change.key}', () {
      final data = fixture();
      item(data)['records'][0][change.key] = change.value;
      expect(read(data), isEmpty);
    });
  }

  test('duplicate observations cannot inflate the denominator', () {
    final data = fixture();
    final records = item(data)['records'] as List;
    records.add(Map<String, dynamic>.from(records.first as Map));
    expect(read(data), isEmpty);
  });

  for (final width in [390.0, 1440.0]) {
    for (final zero in [false, true]) {
      testWidgets('compact summary fits at $width, zero=$zero', (tester) async {
        await tester.binding.setSurfaceSize(Size(width, 1000));
        addTearDown(() => tester.binding.setSurfaceSize(null));
        final data = fixture();
        if (zero) {
          for (final row in item(data)['records'] as List) {
            row['latest_observation']['views'] = 0;
          }
          group(data).addAll({
            'threshold_views': 0,
            'passing_count': 0,
            'percentage': 0,
            'passing_video_ids': <String>[]
          });
        }
        await tester.pumpWidget(MaterialApp(
            home: Scaffold(
          body: SingleChildScrollView(
              child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: ReferenceResponsePanel(
                      bundle: data,
                      recommendedTopics: const {
                        'low-light': 'ภาพในสภาพแสงน้อย'
                      }))),
        )));
        await tester.pumpAndSettle();
        expect(
            find.text('ในกลุ่มคลิปอ้างอิงหมวด Camera '
                'ที่กล่าวถึง “ภาพในสภาพแสงน้อย” มีคลิปที่มียอดวิวสะสมมากกว่า '
                '${zero ? 0 : 200} ครั้ง ณ วันที่เก็บสถิติ '
                'จำนวน ${zero ? 0 : 1} จาก 2 คลิป คิดเป็น ${zero ? 0 : 50}% จากทั้งหมด 2 ช่อง '
                'สำหรับคลิปของคุณ หากเกี่ยวข้องกับสิ่งที่ทดสอบจริง '
                'ลองเพิ่มประเด็นนี้พร้อมตัวอย่างการใช้งาน แล้วติดตามผลตอบรับหลังเผยแพร่'),
            findsOneWidget);
        expect(
            find.textContaining('เปรียบเทียบภายในหมวด Camera'), findsNothing);
        expect(find.textContaining('คลิปปกติ · อายุ 30 ถึงน้อยกว่า 90 วัน'),
            findsNothing);
        expect(find.text('เป็นอีกชุดข้อมูล ไม่ใช่ตัวหารของสัดส่วนด้านบน'),
            findsOneWidget);
        expect(find.textContaining('คลิปที่ใช้คำนวณ'), findsNothing);
        expect(find.textContaining('ผ่านเกณฑ์'), findsNothing);
        expect(find.textContaining('ค่าอ้างอิงยอดวิวสะสม:'), findsNothing);
        expect(find.byTooltip('เปิดคลิปที่ใช้คำนวณ video000001'), findsNothing);
        expect(read(data).single.members, hasLength(2));
        expect(tester.takeException(), isNull);
      });
    }
  }

  testWidgets('narrative reuses the saved proposal and product condition',
      (tester) async {
    final data = fixture();
    final before = jsonEncode(data);
    final advice = ActionableAdvice.fromJson({
      'evidence_topic_id': 'low-light',
      'title': 'ภาพในสภาพแสงน้อย',
      'proposal': 'เพิ่มฉากแสงน้อยเพื่อแสดงข้อจำกัดของไฟล์',
      'condition': 'ใช้การตั้งค่าที่กล้องรองรับ ไม่สมมุติว่ามีโหมดกลางคืน',
    });
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: ReferenceResponsePanel(
            bundle: data,
            recommendedTopics: const {'low-light': 'ภาพในสภาพแสงน้อย'},
            adviceByTopic: {'low-light': advice},
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    expect(
        find.textContaining('ระบบเสนอให้ลอง${advice.proposal} '
            'ทั้งนี้ ${advice.condition} แล้วติดตามผลตอบรับหลังเผยแพร่'),
        findsOneWidget);
    expect(find.textContaining('เนื้อหานี้อยู่ในกลุ่ม'), findsNothing);
    expect(find.textContaining('10,000 ครั้งภายใน 7 วัน'), findsNothing);
    expect(
        find.textContaining('ไม่ใช่โอกาสที่คลิปของคุณจะดีขึ้น'), findsNothing);
    expect(jsonEncode(data), before);
    expect(tester.takeException(), isNull);
  });
}
