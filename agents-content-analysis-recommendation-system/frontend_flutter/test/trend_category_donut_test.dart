import 'package:content_ai_web/models/dashboard_overview.dart';
import 'package:content_ai_web/widgets/trend_category_donut.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

DashboardTrendItem item(int rank, String category,
        {String? key, String scope = 'global', String platform = 'youtube'}) =>
    DashboardTrendItem.fromJson({
      'key': key ?? '$platform:$rank',
      'rank': rank,
      'category': category,
      'source_platform': platform,
      'ranking_scope': scope,
    });

void main() {
  for (final width in [360.0, 1000.0, 1440.0]) {
    testWidgets('donut counts overall top 50 at $width px', (tester) async {
      await tester.binding.setSurfaceSize(Size(width, 1000));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final items = [
        for (var i = 1; i <= 22; i++) item(i, 'เพลงและดนตรี'),
        for (var i = 23; i <= 43; i++) item(i, 'เกม'),
        for (var i = 44; i <= 50; i++) item(i, 'ภาพยนตร์และแอนิเมชัน'),
        item(1, 'เพลงและดนตรี'),
        item(1, 'คนละขอบเขต', scope: 'category:20', key: 'category'),
        item(51, 'นอก 50'),
        item(1, 'คำค้น', platform: 'google'),
      ];
      await tester.pumpWidget(MaterialApp(
          home: Scaffold(
        body: SingleChildScrollView(
            child: TrendCategoryDonut(
          trends: items,
          categoryName: (i) => i.category,
        )),
      )));
      await tester.pumpAndSettle();
      expect(find.text('22 คลิป (44%)'), findsOneWidget);
      expect(find.text('21 คลิป (42%)'), findsOneWidget);
      expect(find.text('7 คลิป (14%)'), findsOneWidget);
      expect(find.text('คนละขอบเขต'), findsNothing);
      final pie = tester.widget<PieChart>(find.byType(PieChart)).data;
      expect(pie.sections.map((s) => s.value), [22.0, 21.0, 7.0]);
      expect(pie.sections.map((s) => s.color).toSet().length, 3);
      expect(pie.centerSpaceRadius, greaterThan(0));
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('partial and empty samples do not pretend 50 clips exist',
      (tester) async {
    Future<void> draw(List<DashboardTrendItem> items) =>
        tester.pumpWidget(MaterialApp(
            home: Scaffold(
                body: TrendCategoryDonut(
          trends: items,
          categoryName: (i) => i.category,
        ))));
    await draw([item(1, 'เกม'), item(2, 'เกม'), item(3, 'เพลง')]);
    await tester.pumpAndSettle();
    expect(find.text('2 คลิป (66.7%)'), findsOneWidget);
    expect(find.text('1 คลิป (33.3%)'), findsOneWidget);
    expect(find.textContaining('สัดส่วนจาก 3 คลิป'), findsOneWidget);
    await draw([]);
    await tester.pumpAndSettle();
    expect(find.byType(PieChart), findsNothing);
    expect(find.text('ยังไม่มีข้อมูลหมวดหมู่ในอันดับรวม'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
