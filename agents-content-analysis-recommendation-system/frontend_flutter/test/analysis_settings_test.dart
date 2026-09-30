import 'package:content_ai_web/models/analysis_settings.dart';
import 'package:content_ai_web/models/recommendation_result.dart';
import 'package:content_ai_web/repositories/admin_repository.dart';
import 'package:content_ai_web/repositories/analysis_repository.dart';
import 'package:content_ai_web/screens/admin_analysis_settings_screen.dart';
import 'package:content_ai_web/screens/upload_screen.dart';
import 'package:content_ai_web/state/auth_controller.dart';
import 'package:content_ai_web/state/auth_scope.dart';
import 'package:content_ai_web/widgets/analysis_settings_audit.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> settingsJson() => {
      'upload_max_duration_seconds': 180,
      'asr_model': 'small',
      'hook_duration_seconds': 30,
      'asr_ready': true,
      'updated_at': '2026-09-06T10:00:00',
      'whisper_models': [
        {'name': 'base', 'ready': false},
        {'name': 'small', 'ready': true},
      ],
      'classification_model': {
        'model_id': 14,
        'model_key': 'taxonomy-tfidf-complement-nb',
        'model_version': '20260828T134420Z',
        'model_type': 'tfidf_complement_nb',
        'training_sample_count': 116,
        'unknown_threshold': 0.72,
        'status': 'qualified',
        'evaluation_metrics': [
          {
            'split': 'validation',
            'metric': 'accuracy',
            'value': 0.85,
            'sample_size': 21
          },
        ],
      },
    };

void main() {
  test('upload limit follows the server including duration tolerance', () {
    final settings = AnalysisSettings.fromJson(settingsJson());
    expect(settings.acceptsDuration(const Duration(seconds: 180)), isTrue);
    expect(
        settings.acceptsDuration(const Duration(milliseconds: 180050)), isTrue);
    expect(settings.acceptsDuration(const Duration(milliseconds: 180051)),
        isFalse);
    expect(settings.acceptsDuration(const Duration(seconds: 200)), isFalse);
  });

  test('result reads saved snapshot, including old responses with no audit',
      () {
    final snapshot = settingsJson();
    expect(
        AnalysisResultViewData.fromJson({'analysis_settings': snapshot})
            .analysisSettings,
        snapshot);
    expect(
        AnalysisResultViewData.fromJson({
          'analysis': {'analysis_settings': snapshot}
        }).analysisSettings,
        snapshot);
    expect(AnalysisResultViewData.fromJson({}).analysisSettings, isEmpty);
  });

  testWidgets(
      'admin validates Hook, disables absent models and saves three fields',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1280, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final repository = _AdminRepository();
    await tester.pumpWidget(
        MaterialApp(home: AdminAnalysisSettingsScreen(repository: repository)));
    await tester.pumpAndSettle();
    expect(find.text('เกณฑ์ Unknown จากโมเดล: 72.0%'), findsOneWidget);
    expect(find.textContaining('85.0%'), findsOneWidget);
    final dropdown = tester.widget<DropdownButtonFormField<String>>(
        find.byType(DropdownButtonFormField<String>));
    expect(dropdown.initialValue, 'small');
    await tester.tap(find.byType(DropdownButtonFormField<String>));
    await tester.pumpAndSettle();
    final unavailable = tester.widget<DropdownMenuItem<String>>(find
        .ancestor(
            of: find.text('base (ยังไม่พร้อม)').last,
            matching: find.byType(DropdownMenuItem<String>))
        .last);
    expect(unavailable.enabled, isFalse);
    await tester.tap(find.text('small').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextFormField).at(0), '30');
    await tester.enterText(find.byType(TextFormField).at(1), '60');
    await tester.tap(find.text('บันทึกการตั้งค่า'));
    await tester.pumpAndSettle();
    expect(
        find.text('ช่วงเปิดคลิปต้องไม่ยาวกว่าขีดจำกัดอัปโหลด'), findsOneWidget);
    expect(repository.saved, isNull);
    await tester.enterText(find.byType(TextFormField).at(0), '120');
    await tester.enterText(find.byType(TextFormField).at(1), '20');
    await tester.tap(find.text('บันทึกการตั้งค่า'));
    await tester.pumpAndSettle();
    expect(repository.saved, {
      'upload_max_duration_seconds': 120,
      'asr_model': 'small',
      'hook_duration_seconds': 20
    });
    await tester.tap(find.byTooltip('โหลดค่าล่าสุด'));
    await tester.pumpAndSettle();
    expect(
        tester
            .widget<TextFormField>(find.byType(TextFormField).at(0))
            .controller!
            .text,
        '120');
    expect(tester.takeException(), isNull);
  });

  testWidgets(
      'failed initial load offers retry without editable stale defaults',
      (tester) async {
    final repository = _AdminRepository()..fail = true;
    await tester.pumpWidget(
        MaterialApp(home: AdminAnalysisSettingsScreen(repository: repository)));
    await tester.pumpAndSettle();
    expect(find.byType(TextFormField), findsNothing);
    expect(find.textContaining('offline'), findsOneWidget);
    repository.fail = false;
    await tester.tap(find.byTooltip('โหลดค่าล่าสุด'));
    await tester.pumpAndSettle();
    expect(find.byType(TextFormField), findsNWidgets(2));
  });

  testWidgets(
      'upload screen displays fetched settings, unavailable ASR is explicit',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1280, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final repository = _AnalysisRepository();
    final controller = AuthController();
    addTearDown(controller.dispose);
    Widget upload() => AuthScope(
        controller: controller,
        child: MaterialApp(home: UploadScreen(repository: repository)));
    await tester.pumpWidget(upload());
    await tester.pumpAndSettle();
    expect(find.textContaining('180 วินาที'), findsOneWidget);
    expect(find.textContaining('Whisper small'), findsOneWidget);
    expect(find.textContaining('no longer than 5 minutes'), findsNothing);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
    repository.ready = false;
    await tester.pumpWidget(upload());
    await tester.pumpAndSettle();
    expect(find.textContaining('โมเดลถอดเสียงยังไม่พร้อม'), findsOneWidget);
    final pickButton = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, 'Pick a Video File'));
    expect(pickButton.onPressed, isNull);
  });

  testWidgets('audit displays historic settings instead of current defaults',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: SingleChildScrollView(
                child: AnalysisSettingsAudit(snapshot: settingsJson())))));
    await tester.tap(find.text('การตั้งค่าที่ใช้วิเคราะห์ครั้งนี้'));
    await tester.pumpAndSettle();
    expect(find.text('Whisper small'), findsOneWidget);
    expect(find.text('180 วินาที'), findsOneWidget);
    expect(find.text('30 วินาที'), findsOneWidget);
    expect(find.text('72.0%'), findsOneWidget);
    await tester.pumpWidget(const MaterialApp(
        home: Scaffold(body: AnalysisSettingsAudit(snapshot: {}))));
    await tester.tap(find.text('การตั้งค่าที่ใช้วิเคราะห์ครั้งนี้'));
    await tester.pumpAndSettle();
    expect(find.text('ผลเก่านี้ยังไม่ได้บันทึกการตั้งค่า'), findsOneWidget);
  });
}

class _AdminRepository extends AdminRepository {
  Map<String, dynamic> data = settingsJson();
  Map<String, dynamic>? saved;
  bool fail = false;
  @override
  Future<AnalysisSettings> getAnalysisSettings() async {
    if (fail) throw Exception('offline');
    return AnalysisSettings.fromJson(data);
  }

  @override
  Future<AnalysisSettings> saveAnalysisSettings(
      {required int uploadMaxDurationSeconds,
      required String asrModel,
      required int hookDurationSeconds}) async {
    saved = {
      'upload_max_duration_seconds': uploadMaxDurationSeconds,
      'asr_model': asrModel,
      'hook_duration_seconds': hookDurationSeconds
    };
    data = {...data, ...saved!};
    return AnalysisSettings.fromJson(data);
  }
}

class _AnalysisRepository extends AnalysisRepository {
  bool ready = true;
  @override
  Future<AnalysisSettings> getSettings() async =>
      AnalysisSettings.fromJson({...settingsJson(), 'asr_ready': ready});
}
