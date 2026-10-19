import 'dart:convert';

import 'package:content_ai_web/models/outcome_prediction.dart';
import 'package:content_ai_web/models/performance_clustering.dart';
import 'package:content_ai_web/models/recommendation_result.dart';
import 'package:content_ai_web/repositories/content_repository.dart';
import 'package:content_ai_web/screens/result_screen.dart';
import 'package:content_ai_web/state/auth_controller.dart';
import 'package:content_ai_web/state/auth_scope.dart';
import 'package:content_ai_web/ui/app_theme.dart';
import 'package:content_ai_web/widgets/actionable_advice_panel.dart';
import 'package:content_ai_web/widgets/clip_revision_planner.dart';
import 'package:content_ai_web/widgets/outcome_assessment_panel.dart';
import 'package:content_ai_web/widgets/reference_response_panel.dart';
import 'package:content_ai_web/widgets/revision_comparison_panel.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'group_response_summary_test.dart' as groups;
import 'performance_clustering_test.dart' as performance;

Map<String, dynamic> _payload() => {
      'content_id': 41,
      'analysis_id': 81,
      'title': 'รีวิวกล้องและการทดสอบภาพในสถานการณ์จริง',
      'raw_transcript': 'ข้อความต้นฉบับจากคลิป\nทดสอบการจับถือกล้อง',
      'cleaned_transcript': 'NORMALIZED INTERNAL TEXT',
      'outcome_assessment_fingerprint': 'a' * 64,
      'outcome_assessment': {
        'status': 'available',
        'probability': 0.65,
        'evidence_topic_ids': ['low-light'],
        'context': {
          'accepted_category': 'camera',
          'confirmed_format': 'long_form',
          'frozen_age_context': 'age_30_90d',
        },
      },
      'recommendation': {
        'domain': 'camera',
        'classification': {
          'domain': 'camera',
          'category_level_3': 'Camera',
          'confidence': 0.97,
          'is_unknown': false,
        },
        'content_keywords': ['กล้อง', 'การทดสอบภาพในสถานการณ์จริง'],
        'hook_terms': ['การจับถือ'],
        'comparable_keywords': ['camera handling'],
        'recommended_duration': {
          'evidence_status': 'sufficient',
          'median_seconds': 79,
          'percentile_low_seconds': 59,
          'percentile_high_seconds': 91,
        },
        'evidence_bundle': groups.fixture(),
        'actionable_recommendations': {
          'status': 'ready',
          'items': [
            {
              'id': 'low-light-advice',
              'evidence_topic_id': 'low-light',
              'title': 'ภาพในสภาพแสงน้อย',
              'finding': 'พบการทดสอบการจับถือกล้อง',
              'proposal': 'เพิ่มฉากทดสอบแสงน้อย',
              'condition': 'ทดสอบด้วยอุปกรณ์ที่ใช้งานจริง',
              'steps': ['บันทึกภาพจากสถานที่เดิม'],
              'example': 'จะทดสอบภาพในห้องเดิม',
              'reason': 'มีข้อความจากคลิปอ้างอิงที่ตรวจสอบได้',
              'relevance_reason': 'เกี่ยวข้องกับการทดสอบกล้อง',
            },
          ],
        },
      },
    };

Future<void> _tab(WidgetTester tester, String name) async {
  final tab = find.byKey(ValueKey('result-tab-$name'));
  await tester.ensureVisible(tab);
  await tester.tap(tab);
  await tester.pumpAndSettle();
}

Future<void> _report(WidgetTester tester, Map<String, dynamic> payload,
    {ContentRepository? repository}) async {
  await tester.pumpWidget(MaterialApp(
      theme: buildAppTheme(Brightness.light),
      home: Scaffold(
          body: SingleChildScrollView(
              child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: AnalysisReport(
                      data: AnalysisResultViewData.fromJson(payload),
                      repository: repository))))));
  await tester.pumpAndSettle();
}

class _Repository extends ContentRepository {
  _Repository(this.data);
  final AnalysisResultViewData data;
  final List<int> reads = [];
  final List<int> performanceReads = [];
  Map<String, dynamic>? simulation;

  @override
  Future<PerformanceComparison> getPerformanceComparison(int contentId,
      {int? minimumViews}) async {
    performanceReads.add(contentId);
    return PerformanceComparison.fromJson(performance.fixture());
  }

  @override
  Future<AnalysisResultViewData> getContentResult(int contentId) async {
    reads.add(contentId);
    return data;
  }

  @override
  Future<OutcomeScenario> simulateOutcomeScenario({
    required int contentId,
    required int analysisId,
    required String assessmentFingerprint,
    required List<String> selectedTopicIds,
  }) async {
    simulation = {
      'content_id': contentId,
      'analysis_id': analysisId,
      'fingerprint': assessmentFingerprint,
      'topics': selectedTopicIds,
    };
    return OutcomeScenario.fromJson({
      'status': 'available',
      'hypothetical': true,
      'probability_before': 0.65,
      'probability_after': 0.7,
      'delta_percentage_points': 5,
    });
  }
}

void main() {
  for (final width in [390.0, 768.0, 1280.0, 1600.0]) {
    for (final brightness in Brightness.values) {
      testWidgets('result workspace fits $width in $brightness',
          (tester) async {
        await tester.binding.setSurfaceSize(Size(width, 1000));
        addTearDown(() => tester.binding.setSurfaceSize(null));
        final payload = _payload();
        final before = jsonEncode(payload);
        final data = AnalysisResultViewData.fromJson(payload);
        final repository = _Repository(data);
        final auth = AuthController();
        addTearDown(auth.dispose);
        await tester.pumpWidget(AuthScope(
            controller: auth,
            child: MaterialApp(
                theme: buildAppTheme(brightness),
                onGenerateRoute: (_) => MaterialPageRoute<void>(
                    settings: RouteSettings(
                        name: '/result',
                        arguments: ResultScreenArgs(initialData: data)),
                    builder: (_) => ResultScreen(repository: repository)))));
        await tester.pumpAndSettle();
        expect(repository.reads, [41]);
        expect(find.text('ผลวิเคราะห์บันทึกแล้ว · #41'), findsOneWidget);
        expect(find.text('หมวดหมู่ของคลิป: Camera'), findsOneWidget);
        expect(find.text('97%'), findsOneWidget);
        expect(find.textContaining('ไม่ใช่คะแนนคุณภาพคลิป'), findsOneWidget);
        expect(find.text('1 ข้อ'), findsOneWidget);
        expect(
            find.text('ค่ากลาง 79 วินาที · ช่วง 59–91 วินาที'), findsOneWidget);
        expect(find.text('กล้อง'), findsOneWidget);
        expect(find.text('การจับถือ'), findsOneWidget);
        expect(find.byType(ExpansionTile), findsNothing);
        expect(tester.takeException(), isNull);

        await _tab(tester, 'recommendations');
        expect(find.byType(ActionableAdvicePanel), findsOneWidget);
        expect(find.text('เพิ่มฉากทดสอบแสงน้อย'), findsOneWidget);
        expect(find.text('เหตุผล'), findsOneWidget);
        expect(find.textContaining('มีข้อความจากคลิปอ้างอิงที่ตรวจสอบได้'),
            findsOneWidget);
        expect(find.byType(ExpansionTile), findsNothing);
        expect(tester.takeException(), isNull);

        await _tab(tester, 'transcript');
        final transcript = find.byKey(const ValueKey('result-transcript-text'));
        expect(tester.widget<SelectableText>(transcript).data,
            payload['raw_transcript']);
        expect(find.text('NORMALIZED INTERNAL TEXT'), findsNothing);
        expect(find.byTooltip('คัดลอกข้อความถอดเสียง'), findsOneWidget);
        expect(find.byType(ExpansionTile), findsNothing);
        expect(tester.takeException(), isNull);

        expect(repository.performanceReads, isEmpty);
        await _tab(tester, 'evidence');
        expect(repository.performanceReads, [41]);
        expect(find.byType(ReferenceResponsePanel), findsOneWidget);
        expect(find.byType(OutcomeAssessmentPanel), findsOneWidget);
        expect(find.textContaining('จำนวน 1 จาก 2 คลิป คิดเป็น 50%'),
            findsOneWidget);
        expect(
            find.byKey(const ValueKey('outcome-probability')), findsOneWidget);
        expect(find.byType(ClipRevisionPlanner, skipOffstage: false),
            findsNothing);
        expect(tester.takeException(), isNull);

        await _tab(tester, 'overview');
        expect(repository.performanceReads, [41]);
        expect(find.text('พบอะไรในคลิป'), findsOneWidget);
        expect(find.text('ควรเพิ่มอะไร'), findsNothing);
        expect(jsonEncode(payload), before);
        expect(tester.takeException(), isNull);
      });
    }
  }

  for (final gate in [
    'unknown',
    'partial',
    'unavailable',
    'fixture',
    'no-model'
  ]) {
    testWidgets('result preserves $gate gates with stale populated data',
        (tester) async {
      final payload = _payload();
      final recommendation = payload['recommendation'] as Map;
      if (gate == 'unknown') {
        (recommendation['classification'] as Map).addAll(<String, Object>{
          'is_unknown': true,
          'raw_taxonomy_leaf_key': 'camera',
        });
      } else if (gate == 'partial' || gate == 'unavailable') {
        recommendation['evidence_bundle']['input'] = {'availability': gate};
      } else if (gate == 'fixture') {
        payload['outcome_assessment']['fixture_only'] = true;
      } else {
        payload['outcome_assessment']['status'] = 'model_unavailable';
      }
      await _report(tester, payload);
      final withheld =
          gate == 'unknown' || gate == 'partial' || gate == 'unavailable';
      expect(find.text(withheld ? '0 ข้อ' : '1 ข้อ'), findsOneWidget);
      if (gate == 'unknown') {
        expect(find.text('หมวดหมู่ของคลิป: Unknown/Other'), findsOneWidget);
        expect(find.textContaining('ค่ากลาง 79 วินาที'), findsNothing);
        expect(find.text('งดแนะนำความยาวจนกว่าจะยืนยันหมวดหมู่ได้'),
            findsOneWidget);
      }
      await _tab(tester, 'recommendations');
      expect(find.text('เพิ่มฉากทดสอบแสงน้อย'),
          withheld ? findsNothing : findsOneWidget);
      await _tab(tester, 'evidence');
      expect(find.byType(OutcomeAssessmentPanel, skipOffstage: false),
          findsNothing);
      expect(find.byKey(const ValueKey('outcome-probability')), findsNothing);
      if (withheld) {
        expect(find.textContaining('หมวดหรือข้อความถอดเสียงยังไม่พร้อม'),
            findsOneWidget);
        expect(find.text('12,000'), findsNothing);
      }
      if (gate == 'unknown') {
        expect(find.text('ผลทายก่อนตรวจรับ'), findsOneWidget);
        expect(find.textContaining('ไม่ใช้เลือกคลิปอ้างอิง'), findsOneWidget);
      }
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('summary does not invent confidence, duration or evidence counts',
      (tester) async {
    final payload = _payload();
    final recommendation = payload['recommendation'] as Map;
    (recommendation['classification'] as Map).remove('confidence');
    recommendation['recommended_duration']['evidence_status'] =
        'insufficient_evidence';
    recommendation['evidence_bundle']['reference_documents'] = [];
    await _report(tester, payload);
    expect(find.text('ความมั่นใจของโมเดล'), findsNothing);
    expect(find.text('0%'), findsNothing);
    expect(find.text('0 ข้อ'), findsOneWidget);
    expect(find.textContaining('ค่ากลาง 79 วินาที'), findsNothing);
    expect(find.text('ข้อมูลอ้างอิงยังไม่เพียงพอ'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  for (final failure in [false, true]) {
    testWidgets('copy uses only the raw transcript, clipboard failure=$failure',
        (tester) async {
      String? copied;
      tester.binding.defaultBinaryMessenger
          .setMockMethodCallHandler(SystemChannels.platform, (call) async {
        if (call.method == 'Clipboard.setData') {
          if (failure) throw PlatformException(code: 'denied');
          copied = (call.arguments as Map)['text'] as String;
        }
        return null;
      });
      addTearDown(() => tester.binding.defaultBinaryMessenger
          .setMockMethodCallHandler(SystemChannels.platform, null));
      final payload = _payload();
      await _report(tester, payload);
      await _tab(tester, 'transcript');
      final copy = find.byKey(const ValueKey('result-copy-transcript'));
      await tester.ensureVisible(copy);
      await tester.tap(copy);
      await tester.pumpAndSettle();
      expect(copied, failure ? isNull : payload['raw_transcript']);
      expect(
          find.text(failure
              ? 'คัดลอกข้อความถอดเสียงไม่สำเร็จ'
              : 'คัดลอกข้อความถอดเสียงแล้ว'),
          findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets(
      'empty transcript disables copy; legacy transcript remains readable',
      (tester) async {
    await _report(tester, {'recommendation': <String, dynamic>{}});
    await _tab(tester, 'transcript');
    expect(find.text('ไม่มีข้อความถอดเสียงในผลนี้'), findsOneWidget);
    expect(
        tester
            .widget<IconButton>(
                find.byKey(const ValueKey('result-copy-transcript')))
            .onPressed,
        isNull);
    await _report(tester, {
      'transcript': 'LEGACY SPEECH',
      'recommendation': <String, dynamic>{},
    });
    await _tab(tester, 'transcript');
    expect(find.text('LEGACY SPEECH'), findsOneWidget);
    expect(
        tester
            .widget<IconButton>(
                find.byKey(const ValueKey('result-copy-transcript')))
            .onPressed,
        isNotNull);
  });

  testWidgets('outcome simulation request and state survive tab navigation',
      (tester) async {
    final payload = _payload();
    final repository = _Repository(AnalysisResultViewData.fromJson(payload));
    await _report(tester, payload, repository: repository);
    await _tab(tester, 'evidence');
    final choice = find.byType(CheckboxListTile);
    await tester.ensureVisible(choice);
    await tester.tap(choice);
    await tester.pumpAndSettle();
    final simulate = find.byKey(const ValueKey('simulate-outcome'));
    await tester.ensureVisible(simulate);
    await tester.tap(simulate);
    await tester.pumpAndSettle();
    expect(repository.simulation, {
      'content_id': 41,
      'analysis_id': 81,
      'fingerprint': 'a' * 64,
      'topics': ['low-light'],
    });
    expect(find.textContaining('หลังจำลอง 70.0%'), findsOneWidget);
    await _tab(tester, 'transcript');
    await _tab(tester, 'evidence');
    expect(tester.widget<CheckboxListTile>(choice).value, isTrue);
    expect(find.textContaining('หลังจำลอง 70.0%'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('revision comparison still opens the original result route',
      (tester) async {
    final payload = _payload()
      ..['revision_comparison'] = {
        'status': 'no_topics_selected',
        'parent': {'content_id': 12, 'title': 'Original'},
        'child': {'content_id': 41, 'title': 'Revision'},
      };
    final repository = _Repository(AnalysisResultViewData.fromJson(payload));
    RouteSettings? opened;
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: SingleChildScrollView(
                child: AnalysisReport(
                    data: repository.data, repository: repository))),
        onGenerateRoute: (settings) {
          opened = settings;
          return MaterialPageRoute<void>(
              settings: settings, builder: (_) => const Scaffold());
        }));
    await tester.pumpAndSettle();
    expect(find.byType(RevisionComparisonPanel), findsOneWidget);
    final parent = find.text('เปิดผลวิเคราะห์ต้นฉบับ');
    await tester.ensureVisible(parent);
    await tester.tap(parent);
    await tester.pumpAndSettle();
    expect(opened?.name, '/result');
    expect((opened?.arguments as ResultScreenArgs).contentId, 12);
    expect(tester.takeException(), isNull);
  });
}
