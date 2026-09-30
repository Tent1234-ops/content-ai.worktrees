import 'package:content_ai_web/repositories/admin_repository.dart';
import 'package:content_ai_web/widgets/dataset_readiness_panel.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Future<void> show(WidgetTester tester, _Readiness repo) async {
    await tester.binding.setSurfaceSize(const Size(1000, 1050));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(body: DatasetReadinessPanel(repository: repo))));
    await tester.pumpAndSettle();
  }

  testWidgets('shows separate roles, collection plan and concrete source dates',
      (tester) async {
    final repo = _Readiness();
    await show(tester, repo);
    expect(find.text('กันไว้ประเมิน'), findsOneWidget);
    expect(find.textContaining('Train เท่านั้น'), findsOneWidget);
    await tester.tap(find.text('มือถือ').first);
    await tester.pumpAndSettle();
    expect(find.text('เพิ่ม Test อีก 2 คลิปจากช่องที่กันไว้'), findsOneWidget);
    expect(find.textContaining('ความพร้อมเปรียบเทียบหัวข้อ: 30 คลิป'),
        findsOneWidget);
    expect(find.textContaining('ความเร็วในการชาร์จ: พบ 20 / ยังไม่พบ 10 คลิป'),
        findsOneWidget);
    await tester.ensureVisible(find.text('#42 คลิปมือถือ'));
    await tester.tap(find.text('#42 คลิปมือถือ'));
    await tester.pumpAndSettle();
    expect(find.text('กันไว้ประเมินโมเดล ห้ามใช้สร้างคำแนะนำ'), findsOneWidget);
    expect(find.text('เผยแพร่ 1/9/2026 07:00'), findsOneWidget);
    expect(find.text('เก็บสถิติ 20/9/2026 08:00'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
  testWidgets('filters roles and handles an empty result', (tester) async {
    final repo = _Readiness();
    await show(tester, repo);
    await tester.ensureVisible(find.byKey(const ValueKey('audit-role')));
    await tester.tap(find.byKey(const ValueKey('audit-role')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('พบในเทรนด์ล่าสุด').last);
    await tester.pumpAndSettle();
    expect(repo.role, 'current_trend');
    expect(find.text('ไม่มีรายการที่ตรงกับตัวกรอง'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
  testWidgets('failed audit does not display zero counts and can retry',
      (tester) async {
    final repo = _Readiness()..fail = true;
    await show(tester, repo);
    expect(find.text('ตรวจคุณภาพข้อมูลไม่สำเร็จ'), findsOneWidget);
    expect(find.text('ผ่านเกณฑ์อ้างอิง'), findsNothing);
    repo.fail = false;
    await tester.tap(find.text('Try again'));
    await tester.pumpAndSettle();
    expect(find.text('ผ่านเกณฑ์อ้างอิง'), findsOneWidget);
  });
}

class _Readiness extends AdminRepository {
  bool fail = false;
  String role = 'all';
  @override
  Future<Map<String, dynamic>> datasetReadiness(
      {String category = 'all', String role = 'all', int offset = 0}) async {
    if (fail) throw Exception('unavailable');
    this.role = role;
    return {
      'generated_at': '2026-09-20T01:00:00Z',
      'summary': {
        'classification': 39,
        'evaluation': 11,
        'reference': 39,
        'reference_selected': 15,
        'needs_attention': 0,
        'current_trend': 0
      },
      'current_trends': {'feeds': []},
      'plans': [
        {
          'category': 'phone',
          'classification_count': 50,
          'channels': 21,
          'split_counts': {'train': 39, 'validation': 8, 'test': 3},
          'upper_pool_count': 15,
          'comparison_pool_count': 21,
          'duration_count': 7,
          'largest_channel_share': 0.2,
          'topic_comparison': {
            'eligible_video_count': 30,
            'channels': 10,
            'representativeness_limitation':
                'คลิปอ้างอิงเป็นข้อมูลที่คัดเก็บ ไม่ใช่ตัวแทน YouTube ทั้งหมด',
            'metadata_or_statistics_gaps': {
              'no_recent_successful_observation': 2
            },
            'topics': [
              {
                'title': 'ความเร็วในการชาร์จ',
                'detected_count': 20,
                'not_detected_count': 10,
                'paired_channel_count': 10,
                'views_status': 'comparison_supported'
              }
            ]
          },
          'actions': ['เพิ่ม Test อีก 2 คลิปจากช่องที่กันไว้']
        }
      ],
      'total': role == 'current_trend' ? 0 : 1,
      'items': role == 'current_trend'
          ? []
          : [
              {
                'dataset_id': 42,
                'title': 'คลิปมือถือ',
                'roles': ['evaluation'],
                'data_split': 'test',
                'channel': 'ช่องทดสอบ',
                'source_channel_id': 'channel-42',
                'published_at': '2026-09-01T00:00:00Z',
                'statistics_captured_at': '2026-09-20T01:00:00Z',
                'duration_seconds': 180,
                'language': 'th',
                'reference_selected': false,
                'checks': [
                  {'key': 'published_at', 'label': 'วันที่เผยแพร่', 'ok': true}
                ],
                'reference_blockers': [
                  'กันไว้ประเมินโมเดล ห้ามใช้สร้างคำแนะนำ'
                ],
                'trend_evidence': [],
              }
            ],
    };
  }
}
