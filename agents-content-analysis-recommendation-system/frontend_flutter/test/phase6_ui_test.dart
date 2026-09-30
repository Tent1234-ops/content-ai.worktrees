import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:content_ai_web/models/recommendation_result.dart';
import 'package:content_ai_web/repositories/admin_repository.dart';
import 'package:content_ai_web/screens/result_screen.dart';
import 'package:content_ai_web/services/api_client.dart';
import 'package:content_ai_web/state/auth_controller.dart';
import 'package:content_ai_web/state/auth_scope.dart';
import 'package:content_ai_web/ui/app_theme.dart';
import 'package:content_ai_web/widgets/source_health_panel.dart';

void main() {
  test('both themes use explicit zero letter spacing for every text style', () {
    for (final brightness in Brightness.values) {
      final text = buildAppTheme(brightness).textTheme;
      for (final style in [
        text.displayLarge,
        text.displayMedium,
        text.displaySmall,
        text.headlineLarge,
        text.headlineMedium,
        text.headlineSmall,
        text.titleLarge,
        text.titleMedium,
        text.titleSmall,
        text.bodyLarge,
        text.bodyMedium,
        text.bodySmall,
        text.labelLarge,
        text.labelMedium,
        text.labelSmall,
      ]) {
        expect(style?.letterSpacing, 0);
      }
    }
  });

  test('mutation responses must explicitly confirm the requested record',
      () async {
    final client = _ResponseClient();
    final repository = AdminRepository(client: client);
    await expectLater(repository.deleteDataset(42), throwsStateError);
    await expectLater(repository.restoreDataset(42), throwsStateError);
    await expectLater(
        repository.updateDataset(42, {'title': 'x'}), throwsStateError);
    client.response = {'dataset_id': 42, 'deleted': true};
    await repository.deleteDataset(42);
    client.response = {'dataset_id': 42, 'deleted_at': '2026-09-26T00:00:00Z'};
    await expectLater(repository.restoreDataset(42), throwsStateError);
    client.response = {'dataset_id': 42, 'deleted_at': null};
    expect((await repository.restoreDataset(42)).datasetId, 42);
  });

  testWidgets(
      'source health failure is explicit and retry reads persisted outcomes',
      (tester) async {
    final repository = _HealthRepository();
    await tester.pumpWidget(MaterialApp(
        theme: buildAppTheme(Brightness.light),
        home: Scaffold(body: SourceHealthPanel(repository: repository))));
    await tester.pumpAndSettle();
    expect(find.textContaining('ยังยืนยันสุขภาพแหล่งข้อมูลไม่ได้'),
        findsOneWidget);
    repository.failed = false;
    await tester.tap(find.byTooltip('ตรวจสถานะแหล่งข้อมูลอีกครั้ง'));
    await tester.pumpAndSettle();
    expect(find.textContaining('รอบล่าสุดเก็บไม่สำเร็จ'), findsOneWidget);
    await tester.tap(find.text('YouTube · อันดับรวม'));
    await tester.pumpAndSettle();
    expect(find.textContaining('ตรวจบันทึกการทำงานระบบ'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  for (final brightness in Brightness.values) {
    testWidgets(
        'three result stages and expandable evidence fit compact web in $brightness',
        (tester) async {
      await tester.binding.setSurfaceSize(const Size(700, 950));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final data = AnalysisResultViewData.fromJson({
        'title': 'ตัวอย่าง',
        'transcript': 'ข้อความที่ตรวจพบ',
        'recommendation': {
          'domain': 'phone',
          'content_keywords': ['แบตเตอรี่', 'หน้าจอ'],
          'hook_terms': ['หน้าจอ'],
          'comparable_keywords': ['battery life'],
          'missing_keywords': [
            {
              'keyword': 'thermal control',
              'score': 0.8,
              'support_count': 2,
              'sample_size': 10,
              'total_frequency': 4,
              'supporting_dataset_row_ids': [8, 9],
              'supporting_examples': [
                {
                  'dataset_id': 8,
                  'title':
                      'ชื่อคลิปอ้างอิงที่มีข้อความยาวเพื่อทดสอบการตัดบรรทัด ' *
                          5,
                  'frequency': 2,
                  'video_url': 'https://youtu.be/abc'
                }
              ]
            }
          ],
          'dataset_profile': {'sample_size': 10},
        }
      });
      await tester.pumpWidget(MaterialApp(
          theme: buildAppTheme(brightness),
          home: Scaffold(
              body: SingleChildScrollView(child: AnalysisReport(data: data)))));
      await tester.pumpAndSettle();
      final first = tester.getTopLeft(find.text('1. พบอะไรในคลิป')).dy;
      final second = tester.getTopLeft(find.text('2. ควรเพิ่มอะไร')).dy;
      final third = tester.getTopLeft(find.text('3. เพราะอะไรจึงแนะนำ')).dy;
      expect(first < second && second < third, isTrue);
      expect(find.textContaining('Dataset IDs: 8, 9'), findsNothing);
      await tester.ensureVisible(find.text('เปิดดูหลักฐานและเวอร์ชัน'));
      await tester.tap(find.text('เปิดดูหลักฐานและเวอร์ชัน'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('หลักฐาน: thermal control'));
      await tester.tap(find.text('หลักฐาน: thermal control'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Dataset IDs: 8, 9'), findsOneWidget);
      expect(find.text('0.00'), findsNothing);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets(
      'result without arguments shows empty state not an endless spinner or fake save',
      (tester) async {
    final auth = AuthController();
    addTearDown(auth.dispose);
    await tester.pumpWidget(AuthScope(
        controller: auth, child: const MaterialApp(home: ResultScreen())));
    await tester.pumpAndSettle();
    expect(find.text('ยังไม่มีผลวิเคราะห์'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsNothing);
    expect(find.byTooltip('Save to My Ideas'), findsNothing);
  });
}

class _ResponseClient extends ApiClient {
  Map<String, dynamic> response = {};
  @override
  Future<dynamic> delete(String path, {Map<String, dynamic>? body}) async =>
      response;
  @override
  Future<dynamic> post(String path, Map<String, dynamic> body) async =>
      response;
  @override
  Future<dynamic> put(String path, Map<String, dynamic> body) async => response;
}

class _HealthRepository extends AdminRepository {
  bool failed = true;
  @override
  Future<Map<String, dynamic>> sourceHealth() async {
    if (failed) throw StateError('offline');
    return {
      'region': 'TH',
      'checked_at': '2026-09-26T08:00:00Z',
      'items': [
        {
          'platform': 'youtube',
          'scope': 'global',
          'status': 'failed',
          'failed_24h': 1,
          'observed_24h': 2,
          'last_run_id': 10,
          'last_success_at': '2026-09-26T07:00:00Z'
        }
      ]
    };
  }
}
