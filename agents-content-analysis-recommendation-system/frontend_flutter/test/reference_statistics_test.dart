import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:content_ai_web/repositories/admin_repository.dart';
import 'package:content_ai_web/widgets/reference_statistics_panel.dart';

void main() {
  Future<void> show(WidgetTester tester, _Statistics repo) async {
    await tester.binding.setSurfaceSize(const Size(1100, 1050));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(body: ReferenceStatisticsPanel(repository: repo))));
    await tester.pumpAndSettle();
  }

  testWidgets('missing metrics and a single sample are not zero growth',
      (tester) async {
    await show(tester, _Statistics());
    expect(find.textContaining('ไลก์ ไม่มีข้อมูล'), findsOneWidget);
    expect(find.text('ยังไม่มีข้อมูลสองครั้งที่เปรียบเทียบการเติบโตได้'),
        findsOneWidget);
    expect(find.textContaining('เฉลี่ย 0'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('growth shows observed interval and detail provenance',
      (tester) async {
    await show(tester, _Statistics()..withGrowth = true);
    expect(find.textContaining('เฉลี่ย 300 วิว/ชั่วโมง'), findsOneWidget);
    final history = find.byTooltip('ดูประวัติสถิติ #1');
    await tester.ensureVisible(history);
    await tester.tap(history);
    await tester.pumpAndSettle();
    expect(find.textContaining('Video ID abc12345678'), findsOneWidget);
    expect(find.textContaining('รอบ #2'), findsOneWidget);
    expect(find.byTooltip('เปิดคลิปต้นทาง'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('effective budget-limited interval is visible', (tester) async {
    await show(tester, _Statistics()..adapted = true);
    expect(find.text('รอบที่ปรับตามงบ: ทุก 2 ชั่วโมง'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('settings save to backend and failures can retry',
      (tester) async {
    final repo = _Statistics()..fail = true;
    await show(tester, repo);
    expect(find.text('โหลดประวัติสถิติไม่สำเร็จ'), findsOneWidget);
    repo.fail = false;
    await tester.tap(find.byTooltip('โหลดสถิติล่าสุด'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('รอบเก็บสถิติและงบคำขอ API'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '25');
    await tester.tap(find.text('บันทึก'));
    await tester.pumpAndSettle();
    expect(repo.saved?['daily_request_budget'], 25);
    expect(repo.saved?['interval_seconds'], 3600);
    expect(tester.takeException(), isNull);
  });
}

class _Statistics extends AdminRepository {
  bool fail = false, withGrowth = false, adapted = false;
  Map<String, dynamic>? saved;
  Map<String, dynamic> get point => {
        'views': withGrowth ? 1600 : 1000,
        'likes': null,
        'comments': 10,
        'observed_at': '2026-09-21T09:00:00Z',
        'status': 'partial',
        'run_id': 2,
        'video_id': 'abc12345678',
        'source_url': 'https://www.youtube.com/watch?v=abc12345678',
        'growth': withGrowth
            ? {
                'views_delta': 600,
                'views_per_hour': 300,
                'elapsed_hours': 2,
                'from_at': '2026-09-21T07:00:00Z',
                'to_at': '2026-09-21T09:00:00Z'
              }
            : null,
      };
  @override
  Future<Map<String, dynamic>> referenceStatistics({int offset = 0}) async {
    if (fail) throw Exception('offline');
    return {
      'settings': {
        'enabled': true,
        'interval_seconds': 3600,
        'daily_request_budget': 100,
        'effective_interval_seconds': adapted ? 7200 : 3600,
        'candidate_count': 117,
        'requests_per_round': 3,
        'estimated_requests_per_day': 30,
        'requests_used_today': 3
      },
      'total': 1,
      'runs': [],
      'items': [
        {
          'dataset_id': 1,
          'title': 'คลิปทดสอบ',
          'category': 'phone',
          'latest': point,
          'has_growth': withGrowth,
          'reference_eligible': true
        },
      ]
    };
  }

  @override
  Future<Map<String, dynamic>> referenceStatisticsHistory(int id) async => {
        'title': 'คลิปทดสอบ',
        'points': [point]
      };
  @override
  Future<void> saveReferenceStatisticsSettings(
      Map<String, dynamic> values) async {
    saved = values;
  }
}
