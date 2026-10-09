import 'package:content_ai_web/models/outcome_prediction.dart';
import 'package:content_ai_web/models/recommendation_result.dart';
import 'package:content_ai_web/repositories/content_repository.dart';
import 'package:content_ai_web/widgets/outcome_assessment_panel.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> assessmentJson({
  String status = 'available',
  dynamic probability = 0.62,
  bool fixtureOnly = false,
}) =>
    {
      'schema_version': 'outcome-assessment-v1',
      'status': status,
      'reason_codes': status == 'available' ? [] : ['data_use_not_confirmed'],
      'probability': probability,
      'context': {
        'accepted_category': 'camera',
        'confirmed_format': 'long_form',
        'frozen_age_context': 'age_7_30_days',
      },
      'support_summary': {
        'benchmark': {'video_count': 30, 'channel_count': 8}
      },
      'evidence_topic_ids': ['topic:low-light'],
      'limitations': [
        'เป็นความสัมพันธ์จากข้อมูลอ้างอิง ไม่ใช่หลักฐานเชิงเหตุและผล'
      ],
      'target_version': 'reference_relative_views_v1',
      'protocol_version': 'reference-relative-views-protocol-v1',
      'feature_version': 'outcome-features-v1',
      'model_id': 9,
      'model_version': 'outcome-qualified-v1',
      'fixture_only': fixtureOnly,
      'unexpected_future_field': {'is_safe_to_ignore': true},
    };

class ScenarioRepository extends ContentRepository {
  ScenarioRepository(this.response, {this.failure});
  final OutcomeScenario response;
  final Object? failure;
  int calls = 0;

  @override
  Future<OutcomeScenario> simulateOutcomeScenario({
    required int contentId,
    required int analysisId,
    required String assessmentFingerprint,
    required List<String> selectedTopicIds,
  }) async {
    calls++;
    if (failure != null) throw failure!;
    return response;
  }
}

OutcomeScenario scenario(double delta) => OutcomeScenario.fromJson({
      'status': 'available',
      'reason_codes': [],
      'hypothetical': true,
      'probability_before': 0.62,
      'probability_after': 0.62 + delta / 100,
      'delta_percentage_points': delta,
      'limitation': 'เป็นการจำลองค่าประเมิน ไม่ใช่เปอร์เซ็นต์ยอดวิวที่จะเพิ่ม',
    });

Future<void> mount(
  WidgetTester tester,
  OutcomeAssessment assessment,
  ContentRepository repository, {
  double width = 1000,
}) async {
  await tester.binding.setSurfaceSize(Size(width, 844));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(18),
        child: OutcomeAssessmentPanel(
          assessment: assessment,
          repository: repository,
          contentId: 24,
          analysisId: 31,
          assessmentFingerprint: 'a' * 64,
          topicLabels: const {
            'topic:low-light':
                'การถ่ายภาพในสภาพแสงน้อยและการอธิบายข้อจำกัดของผลทดสอบอย่างละเอียด'
          },
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  test('parser is backward compatible and ignores unknown fields/statuses', () {
    final legacy = AnalysisResultViewData.fromJson({
      'content_id': 1,
      'title': 'ผลเก่า',
      'analysis': {},
      'recommendation': {},
    });
    expect(legacy.outcomeAssessment.status, 'legacy_not_assessed');
    expect(legacy.outcomeAssessment.probability, isNull);

    final future = OutcomeAssessment.fromJson({
      'status': 'future_server_status',
      'probability': 0.77,
      'new_field': true,
    });
    expect(future.status, 'future_server_status');
    expect(future.isAvailable, isFalse);
    expect(outcomeStatusMessage(future.status),
        'ยังไม่สามารถประเมินผลตอบรับสำหรับผลนี้ได้');

    final nested = AnalysisResultViewData.fromJson({
      'content_id': 2,
      'recommendation': {
        'outcome_assessment': assessmentJson(),
      },
    });
    expect(nested.outcomeAssessment.isAvailable, isTrue);
    expect(nested.outcomeAssessment.probability, 0.62);
  });

  test('reference age buckets keep their exact boundaries', () {
    expect(outcomeAgeLabel('age_0_7_days'), 'อายุคลิป 0–7 วัน');
    expect(outcomeAgeLabel('age_7_30_days'), 'อายุคลิป 7–30 วัน');
    expect(outcomeAgeLabel('age_30_90_days'), 'อายุคลิป 30–90 วัน');
    expect(outcomeAgeLabel('age_90_365_days'), 'อายุคลิป 90–365 วัน');
  });

  for (final status in [
    'insufficient_data',
    'unsupported_context',
    'unassessable_transcript',
    'classification_withheld',
    'model_unavailable',
    'model_unqualified',
    'data_use_unverified',
    'legacy_not_assessed',
    'withdrawn',
    'inaccessible',
    'error',
    'future_server_status',
  ]) {
    testWidgets('$status never renders a generated zero percent',
        (tester) async {
      final repository = ScenarioRepository(scenario(1));
      await mount(
        tester,
        OutcomeAssessment.fromJson(
            assessmentJson(status: status, probability: null)),
        repository,
        width: 390,
      );
      expect(find.text(outcomeStatusMessage(status)), findsOneWidget);
      expect(find.textContaining('0.0%'), findsNothing);
      expect(find.byKey(const ValueKey('outcome-probability')), findsNothing);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('available probability explains context without uplift wording',
      (tester) async {
    await mount(
      tester,
      OutcomeAssessment.fromJson(assessmentJson()),
      ScenarioRepository(scenario(1)),
      width: 390,
    );
    expect(find.textContaining('62.0%'), findsOneWidget);
    expect(find.textContaining('คลิปยาว'), findsOneWidget);
    expect(find.textContaining('30 คลิปอิสระ'), findsOneWidget);
    expect(find.textContaining('เปอร์เซ็นต์ยอดวิวที่จะเพิ่ม'), findsOneWidget);
    expect(find.textContaining('เพิ่มยอดวิว 62.0%'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  for (final delta in [-3.5, 0.0, 2.25]) {
    testWidgets('scenario preserves signed delta $delta', (tester) async {
      final repository = ScenarioRepository(scenario(delta));
      await mount(
          tester, OutcomeAssessment.fromJson(assessmentJson()), repository);
      await tester
          .tap(find.byKey(const ValueKey('outcome-topic-topic:low-light')));
      await tester.pump();
      await tester.tap(find.byKey(const ValueKey('simulate-outcome')));
      await tester.pumpAndSettle();
      final expected =
          delta > 0 ? '+${delta.toStringAsFixed(1)}' : delta.toStringAsFixed(1);
      expect(find.textContaining('$expected จุดเปอร์เซ็นต์'), findsOneWidget);
      expect(repository.calls, 1);
      expect(find.textContaining('ยอดวิวเพิ่ม $expected%'), findsNothing);
    });
  }

  testWidgets('server failure is an error and never a success state',
      (tester) async {
    final repository = ScenarioRepository(scenario(1),
        failure: Exception('server rejected scenario'));
    await mount(
        tester, OutcomeAssessment.fromJson(assessmentJson()), repository);
    await tester
        .tap(find.byKey(const ValueKey('outcome-topic-topic:low-light')));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('simulate-outcome')));
    await tester.pumpAndSettle();
    expect(find.textContaining('server rejected scenario'), findsOneWidget);
    expect(find.text('จำลองสถานการณ์สำเร็จ'), findsNothing);
  });
}
