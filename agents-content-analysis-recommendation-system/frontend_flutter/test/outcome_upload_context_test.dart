import 'dart:typed_data';

import 'package:content_ai_web/models/analysis_settings.dart';
import 'package:content_ai_web/repositories/analysis_repository.dart';
import 'package:content_ai_web/screens/upload_screen.dart';
import 'package:content_ai_web/services/api_client.dart';
import 'package:content_ai_web/state/auth_controller.dart';
import 'package:content_ai_web/state/auth_scope.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _Client extends ApiClient {
  Map<String, String>? sentFields;
  @override
  Future<dynamic> postMultipart(
    String path, {
    String? filePath,
    Uint8List? fileBytes,
    Stream<List<int>>? fileStream,
    int? fileSize,
    required String fileName,
    Map<String, String> fields = const {},
  }) async {
    sentFields = fields;
    return {'job_id': 'fixture-job'};
  }
}

class _Repository extends AnalysisRepository {
  final bool available;
  _Repository({this.available = true});
  @override
  Future<AnalysisSettings> getSettings() async => AnalysisSettings.fromJson({
        'upload_max_duration_seconds': 300,
        'asr_model': 'small',
        'hook_duration_seconds': 60,
        'asr_ready': true,
        'outcome_upload': {
          'contexts': available
              ? [
                  {
                    'accepted_category': 'phone',
                    'confirmed_format': 'long_form',
                    'frozen_age_context': 'age_30_90d'
                  },
                  {
                    'accepted_category': 'camera',
                    'confirmed_format': 'short_form',
                    'frozen_age_context': 'age_7_30d'
                  },
                ]
              : []
        },
      });
}

void main() {
  test('normal upload includes explicit context but never client duration',
      () async {
    final client = _Client();
    final repository = AnalysisRepository(client: client);
    await repository.startAnalyzeAndSaveVideo(
        fileName: 'test.mp4',
        fileBytes: Uint8List(0),
        confirmedFormat: 'long_form',
        referenceAgeContext: 'age_30_90d');
    expect(client.sentFields, {
      'confirmed_format': 'long_form',
      'reference_age_context': 'age_30_90d'
    });
    await repository.startAnalyzeAndSaveVideo(
        fileName: 'test.mp4', fileBytes: Uint8List(0));
    expect(client.sentFields, isEmpty);
  });

  for (final width in [1440.0, 390.0]) {
    testWidgets('context fields require declaration and fit at width $width',
        (tester) async {
      await tester.binding.setSurfaceSize(Size(width, 1000));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final controller = AuthController();
      addTearDown(controller.dispose);
      await tester.pumpWidget(AuthScope(
          controller: controller,
          child: MaterialApp(home: UploadScreen(repository: _Repository()))));
      await tester.pumpAndSettle();
      final format = find.byKey(const ValueKey('outcome-format-'));
      await tester.ensureVisible(format);
      await tester.tap(format);
      await tester.pumpAndSettle();
      await tester.tap(find.text('วิดีโอปกติ').last);
      await tester.pumpAndSettle();
      final age = find.byKey(const ValueKey('outcome-age-long_form-'));
      await tester.ensureVisible(age);
      await tester.tap(age);
      await tester.pumpAndSettle();
      expect(find.text('7 ถึงน้อยกว่า 30 วัน'), findsNothing);
      await tester.tap(find.text('30 ถึงน้อยกว่า 90 วัน').last);
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('outcome-age-long_form-age_30_90d')),
          findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('no qualified model does not fabricate selectable contexts',
      (tester) async {
    final controller = AuthController();
    addTearDown(controller.dispose);
    await tester.pumpWidget(AuthScope(
        controller: controller,
        child: MaterialApp(
            home: UploadScreen(repository: _Repository(available: false)))));
    await tester.pumpAndSettle();
    expect(find.byType(DropdownButtonFormField<String>), findsNothing);
    expect(find.text('ยังไม่มีโมเดลประเมินผลตอบรับที่ผ่านการตรวจรับ'),
        findsOneWidget);
  });
}
