import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../models/dashboard_overview.dart';

class TrendCategoryDonut extends StatelessWidget {
  const TrendCategoryDonut({
    super.key,
    required this.trends,
    required this.categoryName,
  });

  // Only the overall YouTube snapshot belongs here, never category samples.
  final List<DashboardTrendItem> trends;
  final String Function(DashboardTrendItem) categoryName;
  static const _colors = [
    Color(0xFF007A9D),
    Color(0xFFE08C27),
    Color(0xFF249B78),
    Color(0xFFB95A86),
    Color(0xFF6F69AD),
    Color(0xFFC85F4A),
    Color(0xFF668342),
    Color(0xFF477AB0),
    Color(0xFF877360),
    Color(0xFF488C91),
    Color(0xFFAF7E35),
    Color(0xFF777777),
  ];

  @override
  Widget build(BuildContext context) {
    final seen = <String>{};
    final counts = <String, int>{};
    for (final item in trends) {
      if (!item.sourcePlatform.toLowerCase().contains('youtube') ||
          item.rankingScope.startsWith('category') ||
          item.rank < 1 ||
          item.rank > 50 ||
          !seen.add(item.key)) {
        continue;
      }
      final name = categoryName(item).trim();
      final label = name.isEmpty ? 'ไม่ระบุหมวด' : name;
      counts[label] = (counts[label] ?? 0) + 1;
    }
    final entries = counts.entries.toList()
      ..sort((a, b) {
        final order = b.value.compareTo(a.value);
        return order == 0 ? a.key.compareTo(b.key) : order;
      });
    final total = counts.values.fold<int>(0, (sum, count) => sum + count);
    String percent(int count) {
      final value = count * 100 / total;
      return value.toStringAsFixed(value == value.roundToDouble() ? 0 : 1);
    }

    final theme = Theme.of(context);
    return ColoredBox(
      color: theme.colorScheme.surface,
      child: Padding(
        padding: const EdgeInsets.all(20),
        child:
            Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text('เทรนด์ตามหมวดหมู่', style: theme.textTheme.titleMedium),
          const SizedBox(height: 4),
          Text('สัดส่วนจาก $total คลิปในอันดับรวม YouTube (สูงสุด 50)',
              style: theme.textTheme.bodySmall),
          const SizedBox(height: 20),
          if (total == 0)
            const Text('ยังไม่มีข้อมูลหมวดหมู่ในอันดับรวม')
          else
            LayoutBuilder(builder: (context, constraints) {
              final chart = SizedBox(
                width: 240,
                height: 240,
                child: Stack(alignment: Alignment.center, children: [
                  Semantics(
                    label: 'สัดส่วนหมวดหมู่ในอันดับรวม YouTube $total คลิป',
                    child: PieChart(
                      PieChartData(
                        centerSpaceRadius: 65,
                        sectionsSpace: 3,
                        startDegreeOffset: -90,
                        sections: [
                          for (var i = 0; i < entries.length; i++)
                            PieChartSectionData(
                              value: entries[i].value.toDouble(),
                              color: _colors[i % _colors.length],
                              radius: 48,
                              showTitle: false,
                            ),
                        ],
                      ),
                      duration: Duration.zero,
                    ),
                  ),
                  IgnorePointer(
                      child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text('$total', style: theme.textTheme.headlineMedium),
                      const Text('คลิปในอันดับรวม'),
                    ],
                  )),
                ]),
              );
              final legend = Column(children: [
                for (var i = 0; i < entries.length; i++)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Padding(
                            padding: const EdgeInsets.only(top: 5),
                            child: SizedBox(
                                width: 12,
                                height: 12,
                                child: ColoredBox(
                                    color: _colors[i % _colors.length])),
                          ),
                          const SizedBox(width: 10),
                          Expanded(child: Text(entries[i].key)),
                          const SizedBox(width: 12),
                          Text(
                              '${entries[i].value} คลิป (${percent(entries[i].value)}%)'),
                        ]),
                  ),
              ]);
              return constraints.maxWidth >= 620
                  ? Row(children: [
                      chart,
                      const SizedBox(width: 36),
                      Expanded(child: legend)
                    ])
                  : Column(children: [
                      Center(child: chart),
                      const SizedBox(height: 16),
                      legend
                    ]);
            }),
        ]),
      ),
    );
  }
}
