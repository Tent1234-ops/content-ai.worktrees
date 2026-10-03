import 'dart:async';

import 'package:content_ai_web/models/trend_history.dart';
import 'package:content_ai_web/repositories/dashboard_repository.dart';
import 'package:content_ai_web/widgets/trend_history_panel.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> point(String time, Map<String, int> ranks,
        {bool gap = false, int total = 10}) =>
    {
      'observed_at': '2026-09-19T$time:00Z',
      'run_id': 2,
      'break_before': gap,
      'total': total,
      'ranks': ranks,
      'category_counts': {'Gaming': 2},
    };

TrendHistory fixture() => TrendHistory.fromJson({
      'items': [
        {'key': 'a', 'title': 'คลิปตัวอย่าง', 'latest_rank': 2}
      ],
      'points': [
        point('09:00', {'a': 8}),
        point('09:15', {'a': 2})
      ],
    });

class HistoryRepository extends DashboardRepository {
  final requests = <String>[];
  final selectedKeys = <String?>[];
  Future<TrendHistory> Function(String)? handler;
  @override
  Future<TrendHistory> getTrendHistory(
      {required String platform,
      int days = 7,
      String? categoryId,
      String? itemKey}) async {
    requests.add('$platform:$categoryId:$days');
    selectedKeys.add(itemKey);
    return handler == null ? fixture() : await handler!(platform);
  }
}

Widget panel(HistoryRepository repo,
        {String platform = 'youtube',
        String? category,
        String revision = '1'}) =>
    MaterialApp(
        home: Scaffold(
            body: SingleChildScrollView(
      child: TrendHistoryPanel(
          repository: repo,
          platform: platform,
          categoryId: category,
          revision: revision,
          categoryName: (c) => c),
    )));

void main() {
  TrendHistory growthFixture({String selected = 'a'}) => TrendHistory.fromJson({
        'selected_key': selected,
        'requested_from': '2026-09-19T08:00:00Z',
        'requested_to': '2026-09-19T12:00:00Z',
        'coverage': {
          'hours_observed': 2,
          'hours_requested': 5,
          'unobserved_hours': 3,
          'failed_attempts': 1
        },
        'hours': [
          {
            'hour': '2026-09-19T08:00:00Z',
            'status': 'failed',
            'observed': false,
            'failed_attempts': 1
          },
          {
            'hour': '2026-09-19T09:00:00Z',
            'status': 'observed',
            'observed': true,
            'failed_attempts': 0
          },
        ],
        'items': [
          {
            'key': 'a',
            'title': 'คลิป A',
            'latest_rank': 2,
            'movement': {'status': 'up', 'change': 6}
          },
          {'key': 'b', 'title': 'คลิป B', 'latest_rank': 3},
        ],
        'points': [
          {
            ...point('09:00', {'a': 8, 'b': 3}),
            'run_id': 1,
            'views': {selected: 1000}
          },
          {
            ...point('09:30', {'a': 2, 'b': 3}),
            'views': {selected: 1300},
            'item_ids': {selected: 22},
            'view_intervals': {
              selected: {
                'status': 'measured',
                'delta': 300,
                'per_hour': 600,
                'from_at': '2026-09-19T09:00:00Z',
                'elapsed_seconds': 1800,
                'from_views': 1000,
                'from_run_id': 1,
                'from_item_id': 11
              }
            }
          },
          {
            ...point('11:00', {'a': 2, 'b': 3}, gap: true),
            'view_intervals': {
              selected: {
                'status': 'collection_gap',
                'delta': null,
                'per_hour': null
              }
            }
          },
        ],
      });

  test('invalid or unavailable intervals never become measured zero', () {
    expect(
        ViewInterval.fromJson({'status': 'measured', 'delta': 0, 'per_hour': 0})
            .measured,
        isFalse);
    expect(ViewInterval.fromJson({'status': 'counter_decreased'}).measured,
        isFalse);
    expect(
        ViewInterval.fromJson({
          'status': 'measured',
          'delta': 0,
          'per_hour': 0,
          'elapsed_seconds': 60,
          'from_at': '2026-09-19T09:00:00Z'
        }).measured,
        isTrue);
  });

  testWidgets(
      'growth chart uses isolated interval bars and keeps requested time bounds',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1440, 1100));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final repo = HistoryRepository()..handler = (_) async => growthFixture();
    await tester.pumpWidget(panel(repo));
    await tester.pumpAndSettle();
    expect(find.byType(LineChart), findsNWidgets(3));
    expect(find.text('ขยับขึ้น 6 อันดับ'), findsOneWidget);
    final graphs =
        tester.widgetList<LineChart>(find.byType(LineChart)).toList();
    final growth = graphs[1].data;
    expect(growth.lineBarsData.length, 1);
    expect(growth.lineBarsData.single.spots.last.y, 600);
    expect(growth.lineBarsData.single.spots.first.x,
        growth.lineBarsData.single.spots.last.x);
    expect(
        graphs.first.data.lineBarsData.single.spots, contains(FlSpot.nullSpot));
    expect(
        growth.minX,
        equals(DateTime.parse('2026-09-19T08:00:00Z').millisecondsSinceEpoch /
            60000));
    await tester.ensureVisible(find.byTooltip('ดูตารางข้อมูลกราฟ'));
    await tester.tap(find.byTooltip('ดูตารางข้อมูลกราฟ'));
    await tester.pumpAndSettle();
    expect(find.text('ยอดเพิ่มจริง'), findsOneWidget);
    expect(find.text('+300'), findsOneWidget);
    expect(find.text('11 → 22'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
      'selected item reloads its metrics and coverage details are available',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(900, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final repo = HistoryRepository();
    repo.handler =
        (_) async => growthFixture(selected: repo.selectedKeys.last ?? 'a');
    await tester.pumpWidget(panel(repo));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(DropdownButtonFormField<String>).first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('คลิป B').last);
    await tester.pumpAndSettle();
    expect(repo.selectedKeys.last, 'b');
    await tester.ensureVisible(find.byTooltip('ดูความครอบคลุมรายชั่วโมง'));
    await tester.tap(find.byTooltip('ดูความครอบคลุมรายชั่วโมง'));
    await tester.pumpAndSettle();
    expect(find.text('ความครอบคลุมของข้อมูล'), findsOneWidget);
    expect(find.text('เก็บไม่สำเร็จ (1 ครั้ง)'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  test(
      'rank gaps and absent video never become zero; best rank is above worse rank',
      () {
    final points = [
      point('08:00', {'a': 8}),
      point('09:00', {}),
      point('11:00', {'a': 2}, gap: true)
    ].map(HistoryPoint.fromJson).toList();
    final chart = HistoryLineChart(
        points: points,
        rank: true,
        color: Colors.blue,
        value: (p) => p.ranks['a']?.toDouble(),
        tooltip: (_) => '');
    expect(chart.spots.where((p) => p == FlSpot.nullSpot).length, 2);
    expect(chart.spots.first.y, -8);
    expect(chart.spots.last.y, -2);
    expect(points.first.share('Gaming'), 20);
    expect(HistoryPoint.fromJson(point('12:00', {}, total: 0)).share('Gaming'),
        isNull);
  });

  testWidgets('public history has working charts, periods and evidence table',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1440, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final repo = HistoryRepository();
    await tester.pumpWidget(panel(repo));
    await tester.pumpAndSettle();
    expect(find.byType(LineChart), findsNWidgets(2));
    expect(find.text('หมวดไหนติดอันดับรวมมากขึ้น'), findsOneWidget);
    expect(find.text('7 วันล่าสุด'), findsOneWidget);
    expect(find.byType(SegmentedButton<int>), findsNothing);
    expect(find.text('24 ชั่วโมง'), findsNothing);
    expect(find.text('90 วัน'), findsNothing);
    expect(repo.requests.last, 'youtube:null:7');
    await tester.ensureVisible(find.byTooltip('ดูตารางข้อมูลกราฟ'));
    await tester.tap(find.byTooltip('ดูตารางข้อมูลกราฟ'));
    await tester.pumpAndSettle();
    expect(find.byType(DataTable), findsOneWidget);
    expect(find.text('#8'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Google and category scope hide global category chart',
      (tester) async {
    final repo = HistoryRepository();
    await tester.pumpWidget(panel(repo, platform: 'google'));
    await tester.pumpAndSettle();
    expect(find.byType(LineChart), findsOneWidget);
    expect(find.text('หมวดไหนติดอันดับรวมมากขึ้น'), findsNothing);
    expect(find.text('ลำดับจาก Google Trends ไม่ใช่อันดับจำนวนผู้ค้นหาทั้งหมด'),
        findsOneWidget);
    await tester.pumpWidget(panel(repo, category: '20'));
    await tester.pumpAndSettle();
    expect(repo.requests.last, 'youtube:20:7');
    expect(find.byType(LineChart), findsOneWidget);
  });

  testWidgets('late old platform response cannot replace current platform',
      (tester) async {
    final old = Completer<TrendHistory>();
    final repo = HistoryRepository()
      ..handler = (platform) => platform == 'youtube'
          ? old.future
          : Future.value(TrendHistory.fromJson({}));
    await tester.pumpWidget(panel(repo));
    await tester.pump();
    await tester.pumpWidget(panel(repo, platform: 'google'));
    await tester.pumpAndSettle();
    old.complete(fixture());
    await tester.pumpAndSettle();
    expect(find.text('ยังไม่มีประวัติที่เก็บได้ในช่วงนี้'), findsOneWidget);
    expect(find.byType(LineChart), findsNothing);
  });

  testWidgets('empty, one point and error retry do not fabricate history',
      (tester) async {
    final repo = HistoryRepository()
      ..handler = (_) => Future.error(Exception('offline'));
    await tester.pumpWidget(panel(repo));
    await tester.pumpAndSettle();
    expect(find.byTooltip('ลองโหลดประวัติอีกครั้ง'), findsOneWidget);
    repo.handler = (_) async => TrendHistory.fromJson({
          'items': [
            {'key': 'a', 'title': 'one'}
          ],
          'points': [
            point('10:00', {'a': 1})
          ]
        });
    await tester.tap(find.byTooltip('ลองโหลดประวัติอีกครั้ง'));
    await tester.pumpAndSettle();
    expect(find.byType(LineChart), findsOneWidget);
    expect(find.text('พบเพียงรอบเดียว ยังสรุปการเปลี่ยนอันดับไม่ได้'),
        findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('compact web layout has no overflow and revision reloads',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(850, 950));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final repo = HistoryRepository();
    await tester.pumpWidget(panel(repo));
    await tester.pumpAndSettle();
    await tester.pumpWidget(panel(repo, revision: '2'));
    await tester.pumpAndSettle();
    expect(repo.requests.length, 2);
    expect(find.byType(LineChart), findsNWidgets(2));
    expect(tester.takeException(), isNull);
  });
}
