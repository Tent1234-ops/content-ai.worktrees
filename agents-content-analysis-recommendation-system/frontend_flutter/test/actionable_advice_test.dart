import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:content_ai_web/models/actionable_recommendations.dart';
import 'package:content_ai_web/models/recommendation_result.dart';
import 'package:content_ai_web/screens/result_screen.dart';
import 'package:content_ai_web/widgets/actionable_advice_panel.dart';

Map<String, dynamic> _advice({String status = 'ready', bool items = true}) => {
      'status': status,
      'method_version': 'thai-action-advice-v1',
      'template_version': 'fixture-v1',
      'catalog_sha256': 'a' * 64,
      'limitation': 'ไม่ยืนยันว่าเพิ่มหัวข้อแล้วจะทำให้ยอดวิวเพิ่มขึ้น',
      'items': items
          ? [
              {
                'id': 'charge-1',
                'evidence_topic_id': 'charge',
                'title': 'ความเร็วในการชาร์จ',
                'finding':
                    'ตรวจพบเรื่องแบตเตอรี่ แต่ยังไม่ตรวจพบเรื่องการชาร์จในข้อความที่วิเคราะห์',
                'proposal': 'เพิ่มการจับเวลาชาร์จพร้อมระบุอุปกรณ์ที่ใช้',
                'condition': 'ตรวจคู่มือก่อน ไม่สมมุติว่าทุกรุ่นมีชาร์จเร็ว',
                'steps': [
                  'จดระดับแบตเตอรี่เริ่มต้นและปลายทาง',
                  'จับเวลาจริงและบอกเงื่อนไข'
                ],
                'example': 'ผมจะจับเวลาชาร์จและรายงานค่าที่วัดได้จริง',
                'reason': 'พบใน 2 จาก 4 คลิปอ้างอิง จาก 2 ช่อง',
                'relevance_reason': 'เกี่ยวข้องกับเรื่องแบตเตอรี่ที่พูดถึง',
                'found_topics': [
                  {
                    'title': 'แบตเตอรี่',
                    'observation': {
                      'status': 'detected',
                      'source_field': 'raw_transcript',
                      'occurrences': [
                        {'quote': 'แบตเตอรี่ใช้งานได้นาน', 'timestamp': null}
                      ]
                    }
                  }
                ],
              }
            ]
          : [],
    };

Map<String, dynamic> _bundle() => {
      'input': {'availability': 'available', 'segments': []},
      'action_topics': [
        {
          'topic_id': 'charge',
          'canonical_topic': 'charging speed',
          'title_th': 'ความเร็วในการชาร์จ',
          'synonyms': ['ชาร์จไว'],
          'support_count': 2,
          'channel_count': 2,
          'user': {'status': 'not_detected'},
          'user_hook': {'status': 'unassessable'},
          'references': [
            {
              'dataset_id': 99,
              'frequency': 1,
              'occurrences': [
                {
                  'quote': 'จับเวลาการชาร์จด้วยอุปกรณ์ที่รองรับ',
                  'timestamp': null
                }
              ]
            }
          ],
        }
      ],
      'reference_documents': [
        {
          'dataset_id': 99,
          'title': 'คลิปอ้างอิงทดสอบ',
          'channel_title': 'ช่องทดสอบ',
          'statistics': {'views': 1000, 'likes': 20, 'comments': 2},
          'dataset_version': 'fixture-v1',
          'published_at': '2026-08-01T00:00:00Z',
          'statistics_captured_at': '2026-09-01T00:00:00Z'
        }
      ],
      'topic_comparisons': {
        'as_of': '2026-09-29T12:00:00Z',
        'items': [
          {
            'evidence_topic_id': 'charge',
            'cohort': {
              'detected_count': 12,
              'not_detected_count': 10,
              'support_cohort_video_count': 8,
              'comparison_pool_video_count': 14,
            },
            'metrics': {
              'views': {
                'status': 'comparison_supported',
                'detected': {
                  'count': 12,
                  'median': 2000,
                  'p25': 1500,
                  'p75': 2500
                },
                'not_detected': {
                  'count': 10,
                  'median': 1000,
                  'p25': 800,
                  'p75': 1200
                },
                'paired_channel_count': 10,
                'within_channel_median_difference': 700,
                'uncertainty': {'status': 'available', 'low': 200, 'high': 900},
              },
              'comments_per_1000_views': {
                'status': 'comparison_supported',
                'detected': {'count': 12, 'median': 3, 'p25': 2, 'p75': 4},
                'not_detected': {'count': 10, 'median': 5, 'p25': 4, 'p75': 6},
                'paired_channel_count': 10,
                'within_channel_median_difference': -2,
                'uncertainty': {'status': 'available', 'low': -3, 'high': -1},
              }
            },
            'limitation': 'เป็นความสัมพันธ์ในคลิปอ้างอิง ไม่ใช่เหตุและผล'
          }
        ]
      },
    };

void main() {
  for (final width in [1000.0, 1440.0]) {
    testWidgets(
        'Thai actions and linked transcript evidence fit web width $width',
        (tester) async {
      await tester.binding.setSurfaceSize(Size(width, 1000));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(MaterialApp(
          home: Scaffold(
              body: SingleChildScrollView(
                  child: ActionableAdvicePanel(
        data: ActionableRecommendations.fromJson(_advice()),
        bundle: _bundle(),
      )))));
      for (final label in [
        'สิ่งที่พบ',
        'สิ่งที่เสนอ',
        'เงื่อนไขก่อนทำ',
        'วิธีเพิ่มเนื้อหา',
        'ตัวอย่างประโยคก่อนทดสอบ',
        'เหตุผล'
      ]) {
        expect(find.text(label), findsOneWidget);
      }
      expect(find.text('ผมจะจับเวลาชาร์จและรายงานค่าที่วัดได้จริง'),
          findsOneWidget);
      await tester.ensureVisible(
          find.byKey(const ValueKey('advice-evidence-charge-1')));
      await tester.tap(find.byKey(const ValueKey('advice-evidence-charge-1')));
      await tester.pumpAndSettle();
      expect(find.textContaining('แบตเตอรี่ใช้งานได้นาน'), findsOneWidget);
      await tester.ensureVisible(find.text('คลิปอ้างอิงทดสอบ'));
      await tester.tap(find.text('คลิปอ้างอิงทดสอบ'));
      await tester.pumpAndSettle();
      expect(find.textContaining('จับเวลาการชาร์จด้วยอุปกรณ์ที่รองรับ'),
          findsOneWidget);
      expect(find.textContaining('ไม่มี Timestamp จากต้นทาง'), findsWidgets);
      await tester
          .ensureVisible(find.text('เปรียบเทียบผลตอบรับของคลิปอ้างอิง'));
      await tester.tap(find.text('เปรียบเทียบผลตอบรับของคลิปอ้างอิง'));
      await tester.pumpAndSettle();
      expect(find.text('ยอดวิวสะสม ณ เวลาเก็บข้อมูล'), findsOneWidget);
      expect(find.text('ความคิดเห็นต่อ 1,000 วิว'), findsOneWidget);
      await tester.tap(find.text('ความคิดเห็นต่อ 1,000 วิว'));
      await tester.pumpAndSettle();
      expect(find.textContaining('ผลต่างค่ากลางภายในช่อง -2'), findsOneWidget);
      expect(find.textContaining('ไม่ใช่ผลเชิงสาเหตุ'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.tap(find.text('ปิด'));
      await tester.pumpAndSettle();
      expect(find.byType(AlertDialog), findsNothing);
    });
  }

  testWidgets(
      'new result replaces raw keyword suggestions and empty advice never falls back',
      (tester) async {
    final result = AnalysisResultViewData.fromJson({
      'title': 'Fixture',
      'recommendation': {
        'domain': 'phone',
        'missing_keywords': [
          {'keyword': 'OLD RAW SUGGESTION', 'score': 1.0}
        ],
        'hook_keywords': [
          {'keyword': 'OLD HOOK', 'score': 1.0}
        ],
        'actionable_recommendations':
            _advice(status: 'all_topics_detected', items: false),
        'evidence_bundle': {
          ..._bundle(),
          'topics': [
            {'canonical_topic': 'OLD TOPIC EVIDENCE'}
          ],
        },
      }
    });
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: SingleChildScrollView(child: AnalysisReport(data: result)))));
    expect(find.text('OLD RAW SUGGESTION'), findsNothing);
    expect(find.text('OLD HOOK'), findsNothing);
    await tester.ensureVisible(find.text('เปิดดูหลักฐานและเวอร์ชัน'));
    await tester.tap(find.text('เปิดดูหลักฐานและเวอร์ชัน'));
    await tester.pumpAndSettle();
    expect(find.text('OLD TOPIC EVIDENCE'), findsNothing);
    expect(find.text('ความเร็วในการชาร์จ'), findsOneWidget);
    expect(find.textContaining('จึงไม่มีข้อเสนอให้เพิ่มซ้ำ'), findsOneWidget);
  });

  testWidgets('withheld input hides advice even if stale items are supplied',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: ActionableAdvicePanel(
      data: ActionableRecommendations.fromJson(_advice()),
      bundle: _bundle(),
      withheld: true,
    ))));
    expect(find.textContaining('ยังไม่แสดงข้อเสนอ'), findsOneWidget);
    expect(find.text('ความเร็วในการชาร์จ'), findsNothing);
  });

  test('legacy result keeps the old rendering contract', () {
    expect(
        RecommendationResult.fromJson({'domain': 'phone'})
            .actionableRecommendations,
        isNull);
  });
}
