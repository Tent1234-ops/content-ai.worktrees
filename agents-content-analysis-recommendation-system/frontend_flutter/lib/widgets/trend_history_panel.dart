import 'dart:math' as math;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../models/trend_history.dart';
import '../repositories/dashboard_repository.dart';

String historyTime(DateTime at) =>
    '${at.day}/${at.month} ${at.hour.toString().padLeft(2, '0')}:${at.minute.toString().padLeft(2, '0')}';

String historyEvidenceTime(DateTime at) =>
    '${historyTime(at)}:${at.second.toString().padLeft(2, '0')}';

String historyNumber(num? value) => value == null
    ? '-'
    : value
        .round()
        .toString()
        .replaceAllMapped(RegExp(r'(\d)(?=(\d{3})+(?!\d))'), (m) => '${m[1]},');

String viewIntervalStatus(String? status) => switch (status) {
      'measured' => 'เปรียบเทียบได้',
      'collection_gap' => 'ข้อมูลขาดช่วง',
      'not_in_both_samples' => 'ไม่พบคลิปในทั้งสองรอบ',
      'metric_changed' => 'นิยามตัวนับเปลี่ยน / ไม่ทราบ',
      'counter_decreased' => 'ยอดสะสมถูกปรับลด ไม่ใช่ยอดเติบโตติดลบ',
      'no_baseline' => 'ยังไม่มีรอบก่อนหน้า',
      _ => 'ไม่มีข้อมูลยอดวิวสำหรับเปรียบเทียบ',
    };

class TrendHistoryPanel extends StatefulWidget {
  const TrendHistoryPanel(
      {super.key,
      required this.repository,
      required this.platform,
      this.categoryId,
      this.categoryLabel,
      required this.categoryName,
      required this.revision});

  final DashboardRepository repository;
  final String platform;
  final String? categoryId;
  final String? categoryLabel;
  final String Function(String) categoryName;
  final String revision;

  @override
  State<TrendHistoryPanel> createState() => _TrendHistoryPanelState();
}

class _TrendHistoryPanelState extends State<TrendHistoryPanel> {
  TrendHistory? _data;
  static const _days = 7;
  int _request = 0;
  bool _loading = true;
  bool _failed = false;
  String? _itemKey;
  String? _category;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(covariant TrendHistoryPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.platform != widget.platform ||
        oldWidget.categoryId != widget.categoryId) {
      _data = null;
      _itemKey = null;
      _category = null;
      _load();
    } else if (oldWidget.revision != widget.revision) {
      _load();
    }
  }

  Future<void> _load() async {
    final request = ++_request;
    setState(() {
      _loading = true;
      _failed = false;
    });
    try {
      final data = await widget.repository.getTrendHistory(
          platform: widget.platform,
          days: _days,
          itemKey: _itemKey,
          categoryId: widget.categoryId);
      if (!mounted || request != _request) return;
      setState(() {
        _data = data;
        if (data.selectedKey != null) _itemKey = data.selectedKey;
        if (!data.items.any((i) => i.key == _itemKey)) {
          _itemKey = data.items.isEmpty ? null : data.items.first.key;
        }
        final categories = _categories(data);
        if (!categories.contains(_category)) {
          _category = categories.isEmpty ? null : categories.first;
        }
        _loading = false;
      });
    } catch (_) {
      if (!mounted || request != _request) return;
      setState(() {
        _loading = false;
        _failed = true;
      });
    }
  }

  List<String> _categories(TrendHistory data) {
    final all = data.points.expand((p) => p.categories.keys).toSet().toList();
    final latest =
        data.points.isEmpty ? <String, int>{} : data.points.last.categories;
    all.sort((a, b) => (latest[b] ?? 0).compareTo(latest[a] ?? 0));
    return all;
  }

  @override
  Widget build(BuildContext context) {
    final data = _data;
    final theme = Theme.of(context);
    return ColoredBox(
      color: theme.colorScheme.surface,
      child: Padding(
        padding: const EdgeInsets.all(20),
        child:
            Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Wrap(
              alignment: WrapAlignment.spaceBetween,
              crossAxisAlignment: WrapCrossAlignment.center,
              spacing: 16,
              runSpacing: 12,
              children: [
                Text(
                    'แนวโน้มย้อนหลัง · ${widget.platform == 'youtube' ? 'YouTube' : 'Google'}',
                    style: theme.textTheme.titleLarge),
                const Text('7 วันล่าสุด'),
              ]),
          const SizedBox(height: 12),
          if (_loading) const LinearProgressIndicator(),
          if (_failed)
            Row(children: [
              const Expanded(
                  child: Text(
                      'โหลดประวัติไม่สำเร็จ อันดับปัจจุบันยังดูได้ตามปกติ')),
              IconButton(
                  onPressed: _load,
                  icon: const Icon(Icons.refresh),
                  tooltip: 'ลองโหลดประวัติอีกครั้ง'),
            ]),
          if (data != null && data.points.isEmpty)
            const Padding(
                padding: EdgeInsets.symmetric(vertical: 20),
                child: Text('ยังไม่มีประวัติที่เก็บได้ในช่วงนี้')),
          if (data != null && data.points.isNotEmpty) ...[
            _itemSelector(data),
            const SizedBox(height: 16),
            LayoutBuilder(builder: (context, constraints) {
              final rank = _rankChart(data);
              if (widget.platform != 'youtube') return rank;
              final growth = _growthChart(data);
              if (constraints.maxWidth < 1050) {
                return Column(
                    children: [rank, const Divider(height: 40), growth]);
              }
              return Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(child: rank),
                    const SizedBox(width: 32),
                    Expanded(child: growth),
                  ]);
            }),
            if (widget.platform == 'youtube' && widget.categoryId == null) ...[
              const Divider(height: 40),
              _categoryChart(data),
            ],
          ],
        ]),
      ),
    );
  }

  Widget _itemSelector(TrendHistory data) => data.items.isEmpty
      ? const SizedBox.shrink()
      : DropdownButtonFormField<String>(
          key: ValueKey('history-item-$_itemKey'),
          initialValue: _itemKey,
          isExpanded: true,
          menuMaxHeight: 360,
          decoration: InputDecoration(
              labelText: widget.platform == 'google' ? 'คำค้น' : 'คลิป'),
          items: data.items
              .map((item) => DropdownMenuItem(
                  value: item.key,
                  child: Text(item.title,
                      maxLines: 1, overflow: TextOverflow.ellipsis)))
              .toList(),
          onChanged: (value) {
            setState(() {
              _itemKey = value;
              _data = null;
            });
            _load();
          },
        );

  Widget _rankChart(TrendHistory data) {
    final occurrences =
        data.points.where((p) => p.ranks.containsKey(_itemKey)).length;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Text('อันดับย้อนหลัง', style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 4),
      Text(
          widget.platform == 'google'
              ? 'ลำดับจาก Google Trends ไม่ใช่อันดับจำนวนผู้ค้นหาทั้งหมด'
              : widget.categoryLabel == null
                  ? 'อันดับรวม YouTube ${data.region == 'TH' ? 'ประเทศไทย' : data.region}'
                  : 'อันดับในหมวด${widget.categoryLabel}',
          style: Theme.of(context).textTheme.bodySmall),
      const SizedBox(height: 12),
      if (occurrences == 0)
        const SizedBox(
            height: 230,
            child: Center(child: Text('ไม่พบรายการนี้ในรอบที่เก็บได้')))
      else
        HistoryLineChart(
          points: data.points,
          rank: true,
          color: const Color(0xFF007FAB),
          from: data.requestedFrom,
          to: data.requestedTo,
          value: (p) => p.ranks[_itemKey]?.toDouble(),
          tooltip: (p) => '#${p.ranks[_itemKey]}',
        ),
    ]);
  }

  Widget _growthChart(TrendHistory data) {
    final measured = data.points
        .where((p) => p.viewIntervals[_itemKey]?.measured == true)
        .length;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Text('ยอดวิวกำลังเพิ่มเร็วแค่ไหน',
          style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 4),
      Text('ยอดวิวเพิ่มเฉลี่ยต่อชั่วโมง · เฉพาะคลิปที่เลือก',
          style: Theme.of(context).textTheme.bodySmall),
      const SizedBox(height: 12),
      if (measured == 0)
        const SizedBox(
            height: 230,
            child: Center(
                child: Text('ยังไม่มีคู่ยอดวิวที่เปรียบเทียบได้ในช่วงนี้')))
      else
        HistoryLineChart(
            points: data.points,
            rank: false,
            viewGrowth: true,
            from: data.requestedFrom,
            to: data.requestedTo,
            color: const Color(0xFFAD651D),
            value: (p) => p.viewIntervals[_itemKey]?.measured == true
                ? p.viewIntervals[_itemKey]!.perHour
                : null,
            tooltip: (p) {
              final interval = p.viewIntervals[_itemKey]!;
              return '${historyTime(interval.from!)} ถึง ${historyTime(p.at)}\n'
                  '+${historyNumber(interval.delta)} ใน ${(interval.seconds! / 60).toStringAsFixed(1)} นาที\n'
                  '${historyNumber(interval.perHour)} ครั้ง/ชม.';
            }),
    ]);
  }

  Widget _categoryChart(TrendHistory data) {
    final categories = _categories(data);
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Text('หมวดไหนติดอันดับรวมมากขึ้น',
          style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 4),
      Text('สัดส่วนคลิปในอันดับรวมที่เก็บได้ ไม่ใช่ส่วนแบ่งผู้ชม YouTube',
          style: Theme.of(context).textTheme.bodySmall),
      const SizedBox(height: 12),
      if (categories.isNotEmpty)
        DropdownButtonFormField<String>(
          key: ValueKey('history-category-$_category'),
          initialValue: _category,
          isExpanded: true,
          decoration:
              const InputDecoration(labelText: 'หมวดที่เปรียบเทียบย้อนหลัง'),
          items: categories
              .map((c) => DropdownMenuItem(
                  value: c,
                  child: Text(widget.categoryName(c),
                      overflow: TextOverflow.ellipsis)))
              .toList(),
          onChanged: (value) => setState(() => _category = value),
        ),
      const SizedBox(height: 12),
      if (data.points.where((p) => p.total > 0).length < 2)
        const SizedBox(
            height: 230,
            child: Center(child: Text('ยังมีข้อมูลไม่พอเปรียบเทียบสัดส่วน')))
      else
        HistoryLineChart(
          points: data.points,
          rank: false,
          color: const Color(0xFF168067),
          from: data.requestedFrom,
          to: data.requestedTo,
          value: (p) => p.share(_category ?? ''),
          tooltip: (p) => '${p.categories[_category] ?? 0}/${p.total} คลิป'
              ' (${p.share(_category ?? '')?.toStringAsFixed(1)}%)',
        ),
    ]);
  }
}

class HistoryLineChart extends StatelessWidget {
  const HistoryLineChart(
      {super.key,
      required this.points,
      required this.rank,
      required this.value,
      required this.tooltip,
      required this.color,
      this.viewGrowth = false,
      this.from,
      this.to});
  final List<HistoryPoint> points;
  final bool rank;
  final double? Function(HistoryPoint) value;
  final String Function(HistoryPoint) tooltip;
  final Color color;
  final bool viewGrowth;
  final DateTime? from, to;

  List<FlSpot> get spots {
    final result = <FlSpot>[];
    for (final p in points) {
      if (p.breakBefore) result.add(FlSpot.nullSpot);
      final y = value(p);
      result.add(y == null
          ? FlSpot.nullSpot
          : FlSpot(p.at.millisecondsSinceEpoch / 60000, rank ? -y : y));
    }
    return result;
  }

  @override
  Widget build(BuildContext context) {
    final min = (from ?? points.first.at).millisecondsSinceEpoch / 60000;
    final max = (to ?? points.last.at).millisecondsSinceEpoch / 60000;
    final range = math.max(1.0, max - min);
    final maxValue =
        points.map(value).whereType<double>().fold<double>(0, math.max);
    final top = viewGrowth ? math.max(1.0, maxValue * 1.15) : 100.0;
    final textStyle = Theme.of(context).textTheme.bodySmall!;
    return SizedBox(
        height: 230,
        child: Padding(
          padding: const EdgeInsets.only(right: 20, top: 8),
          child: LineChart(
              duration: Duration.zero,
              LineChartData(
                minX: from == null ? min - range * 0.04 : min,
                maxX: to == null ? max + range * 0.04 : max,
                minY: rank ? -50 : 0,
                maxY: rank ? -1 : top,
                lineBarsData: viewGrowth
                    ? [
                        for (final point in points)
                          if (value(point) != null)
                            LineChartBarData(
                              spots: [
                                FlSpot(
                                    point.at.millisecondsSinceEpoch / 60000, 0),
                                FlSpot(point.at.millisecondsSinceEpoch / 60000,
                                    value(point)!)
                              ],
                              color: color,
                              barWidth: 7,
                              isCurved: false,
                              dotData: FlDotData(show: value(point) == 0),
                            ),
                      ]
                    : [
                        LineChartBarData(
                            spots: spots,
                            color: color,
                            barWidth: 2,
                            isCurved: false,
                            dotData: FlDotData(
                                show: true,
                                getDotPainter: (spot, percent, bar, index) =>
                                    FlDotCirclePainter(
                                        radius: 3,
                                        color: color,
                                        strokeWidth: 1,
                                        strokeColor: Colors.white)))
                      ],
                gridData: FlGridData(
                    show: true,
                    drawVerticalLine: false,
                    horizontalInterval: rank
                        ? 10
                        : viewGrowth
                            ? top / 4
                            : 25),
                borderData: FlBorderData(show: false),
                titlesData: FlTitlesData(
                  topTitles: const AxisTitles(
                      sideTitles: SideTitles(showTitles: false)),
                  rightTitles: const AxisTitles(
                      sideTitles: SideTitles(showTitles: false)),
                  leftTitles: AxisTitles(
                      sideTitles: SideTitles(
                          showTitles: true,
                          reservedSize: viewGrowth ? 74 : 42,
                          interval: rank
                              ? 10
                              : viewGrowth
                                  ? top / 4
                                  : 25,
                          getTitlesWidget: (v, meta) => Text(
                              rank
                                  ? '#${(-v).round()}'
                                  : viewGrowth
                                      ? historyNumber(v)
                                      : '${v.round()}%',
                              style: textStyle))),
                  bottomTitles: AxisTitles(
                      sideTitles: SideTitles(
                          showTitles: true,
                          reservedSize: 42,
                          interval: range / 3,
                          minIncluded: false,
                          maxIncluded: false,
                          getTitlesWidget: (v, meta) {
                            final at = DateTime.fromMillisecondsSinceEpoch(
                                (v * 60000).round());
                            return Padding(
                                padding: const EdgeInsets.only(top: 8),
                                child: Text(
                                    historyTime(at).replaceFirst(' ', '\n'),
                                    textAlign: TextAlign.center,
                                    style: textStyle));
                          })),
                ),
                lineTouchData: LineTouchData(
                    touchTooltipData: LineTouchTooltipData(
                  fitInsideHorizontally: true,
                  fitInsideVertically: true,
                  getTooltipItems: (spots) => spots.map((spot) {
                    final p = points.reduce((a, b) =>
                        (a.at.millisecondsSinceEpoch / 60000 - spot.x).abs() <
                                (b.at.millisecondsSinceEpoch / 60000 - spot.x)
                                    .abs()
                            ? a
                            : b);
                    return LineTooltipItem(
                        '${historyTime(p.at)}\n${tooltip(p)}',
                        const TextStyle(color: Colors.white, fontSize: 12));
                  }).toList(),
                )),
              )),
        ));
  }
}
