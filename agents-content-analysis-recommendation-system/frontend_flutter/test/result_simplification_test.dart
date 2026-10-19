import 'dart:convert';
import 'package:content_ai_web/models/recommendation_result.dart';
import 'package:content_ai_web/screens/result_screen.dart';
import 'package:content_ai_web/widgets/current_trend_ideas_panel.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'current_trend_ideas_test.dart' as trends;
import 'group_response_summary_test.dart' as groups;

void main() {
  for (final width in [390.0, 1440.0]) {
    testWidgets(
        'result restores reasons and confidence context without discarding data at $width',
        (tester) async {
      await tester.binding.setSurfaceSize(Size(width, 1000));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final bundle = groups.fixture();
      bundle['action_topics'][0].addAll({
        'canonical_topic': 'low light',
        'support_count': 5,
        'sample_size': 25,
        'supporting_dataset_row_ids': [1, 2, 3, 4, 5],
      });
      final payload = {
        'recommendation': {
          'domain': 'camera',
          'classification': {
            'domain': 'camera',
            'taxonomy_leaf_key': 'camera',
            'category_level_3': 'Camera',
            'confidence': 0.97,
            'is_unknown': false,
          },
          'evidence_bundle': bundle,
          'recommended_duration': {
            'evidence_status': 'sufficient',
            'sample_size': 33,
            'minimum_sample_size': 10,
            'median_seconds': 79,
            'percentile_low_seconds': 59,
            'percentile_high_seconds': 91,
          },
          'current_trend_ideas': trends.sample(),
          'hook_keywords': [
            {
              'keyword': 'low light',
              'score': 1,
              'support_count': 5,
              'sample_size': 25,
              'supporting_dataset_row_ids': [1, 2, 3, 4, 5],
            }
          ],
          'actionable_recommendations': {
            'status': 'ready',
            'items': [
              {
                'id': 'low-light-advice',
                'evidence_topic_id': 'low-light',
                'title': 'ภาพในสภาพแสงน้อย',
                'proposal': 'เพิ่มฉากทดสอบแสงน้อย',
                'reason': 'พบใน 5 จาก 25 คลิปอ้างอิง',
                'relevance_reason': 'เหตุผลที่บันทึกไว้สำหรับตรวจย้อนหลัง',
              }
            ],
          },
        },
      };
      final before = jsonEncode(payload);
      final data = AnalysisResultViewData.fromJson(payload);
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(child: AnalysisReport(data: data)),
        ),
      ));
      await tester.pumpAndSettle();
      expect(find.text('ความมั่นใจของโมเดล'), findsOneWidget);
      expect(find.text('97%'), findsOneWidget);
      expect(find.textContaining('ไม่ใช่คะแนนคุณภาพคลิป'), findsOneWidget);
      expect(find.text('1 ข้อ'), findsOneWidget);
      await tester.ensureVisible(
          find.byKey(const ValueKey('result-tab-recommendations')));
      await tester
          .tap(find.byKey(const ValueKey('result-tab-recommendations')));
      await tester.pumpAndSettle();
      expect(find.text('คำสำคัญที่แนะนำให้เพิ่ม'), findsOneWidget);
      expect(find.text('คำสำคัญที่เสนอสำหรับช่วงเปิดคลิป'), findsOneWidget);
      expect(
          find.text('ค่ากลาง 79 วินาที · ช่วง 59–91 วินาที'), findsOneWidget);
      expect(find.text('เหตุผล'), findsOneWidget);
      expect(find.textContaining('พบใน 5 จาก 25 คลิปอ้างอิง'), findsOneWidget);
      expect(find.textContaining('เหตุผลที่บันทึกไว้สำหรับตรวจย้อนหลัง'),
          findsOneWidget);
      for (final hidden in [
        'มีข้อมูลความยาว',
        'ไอเดียจากกระแสล่าสุด',
        'คลิปอ้างอิงในหมวดเดียวกันที่กล่าวถึงประเด็นที่แนะนำ',
        'เป็นตัวอย่างที่ระบบคัดไว้',
        'เปรียบเทียบภายในหมวด',
        'ค่าอ้างอิงยอดวิวสะสม:',
        'เนื้อหาใกล้เคียงหมายถึงตรวจพบประเด็นนี้ใน Transcript',
        'เป็นสัดส่วนในข้อมูลที่คัดเก็บ',
        'คลิปที่ใช้คำนวณ',
      ]) {
        expect(find.textContaining(hidden), findsNothing, reason: hidden);
      }
      expect(find.byType(CurrentTrendIdeasPanel), findsNothing);
      expect(find.text('ดูข้อความและคลิปอ้างอิง'), findsOneWidget);
      await tester
          .ensureVisible(find.byKey(const ValueKey('result-tab-evidence')));
      await tester.tap(find.byKey(const ValueKey('result-tab-evidence')));
      await tester.pumpAndSettle();
      expect(find.textContaining('จำนวน 1 จาก 2 คลิป คิดเป็น 50%'),
          findsOneWidget);
      expect(find.byTooltip('เปิดคลิปต้นทาง รีวิวกล้องพร้อมทดสอบภาพแสงน้อย 1'),
          findsOneWidget);
      expect(data.recommendation.actionableRecommendations!.items.single.reason,
          'พบใน 5 จาก 25 คลิปอ้างอิง');
      expect(data.recommendation.duration.sampleSize, 33);
      expect(data.recommendation.currentTrendIdeas.items, isNotEmpty);
      expect(groups.read(data.recommendation.evidenceBundle).single.members,
          hasLength(2));
      expect(jsonEncode(payload), before);
      expect(tester.takeException(), isNull);
    });
  }
}
