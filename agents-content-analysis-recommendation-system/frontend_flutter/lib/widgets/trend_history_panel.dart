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
  int _days = 5;
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
                SegmentedButton<int>(
                  segments: const [
                    ButtonSegment(value: 1, label: Text('24 ชั่วโมง')),
                    ButtonSegment(value: 5, label: Text('5 วัน')),
                    ButtonSegment(value: 7, label: Text('7 วัน')),
                    ButtonSegment(value: 30, label: Text('30 วัน')),
                    ButtonSegment(value: 90, label: Text('90 วัน')),
                  ],
                  selected: {_days},
                  onSelectionChanged: (value) {
                    setState(() {
                      _days = value.first;
                      _data = null;
                    });
                    _load();
                  },
                ),
              ]),
          const SizedBox(height: 12),
          if (data != null) _coverage(data),
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
            Text(
                '${historyTime(data.points.first.at)} ถึง ${historyTime(data.points.last.at)}'
                ' · ${data.points.length} จุดข้อมูล · เวลาท้องถิ่น',
                style: theme.textTheme.bodySmall),
            const SizedBox(height: 4),
            Text('ข้อมูลต้นและท้ายชั่วโมงที่เก็บได้จริง ไม่ใช่ข้อมูลทุกนาที',
                style: theme.textTheme.bodySmall),
            if (data.stale || data.gaps > 0 || data.latestUnavailable)
              Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(
                      data.latestUnavailable
                          ? 'รอบล่าสุดไม่มีข้อมูลที่ใช้ได้ กราฟแสดงเฉพาะรอบที่เก็บสำเร็จ'
                          : data.stale
                              ? 'ยังไม่มีข้อมูลรอบใหม่ในช่วง 90 นาทีล่าสุด'
                              : 'ข้อมูลขาดช่วง ${data.gaps} ช่วง',
                      style: const TextStyle(color: Color(0xFF986000)))),
            const SizedBox(height: 20),
            _itemSelector(data),
            const SizedBox(height: 16),
            _decisionSummary(data),
            const SizedBox(height: 20),
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
            const SizedBox(height: 8),
            Align(
                alignment: Alignment.centerRight,
                child: IconButton(
                  tooltip: 'ดูตารางข้อมูลกราฟ',
                  icon: const Icon(Icons.table_chart_outlined),
                  onPressed: () => _showTable(data),
                )),
          ],
        ]),
      ),
    );
  }

  Widget _coverage(TrendHistory data) => Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Wrap(
            spacing: 16,
            runSpacing: 4,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text(
                  'มีข้อมูล ${data.hoursObserved} / ${data.hoursRequested} ช่วงชั่วโมง',
                  style: Theme.of(context).textTheme.labelLarge),
              Text(
                  'เก็บไม่สำเร็จ ${data.failedAttempts} ครั้ง · ไม่มีข้อมูล ${data.unobservedHours} ช่วงชั่วโมง'),
              IconButton(
                  tooltip: 'ดูความครอบคลุมรายชั่วโมง',
                  icon: const Icon(Icons.calendar_view_week_outlined),
                  onPressed: () => showDialog<void>(
                      context: context,
                      builder: (context) => AlertDialog(
                            title: const Text('ความครอบคลุมของข้อมูล'),
                            content: SizedBox(
                                width: 650,
                                height: 430,
                                child: ListView.builder(
                                    itemCount: data.hours.length,
                                    itemBuilder: (_, index) {
                                      final hour = data
                                          .hours[data.hours.length - 1 - index];
                                      final label = switch (hour.status) {
                                        'partial' =>
                                          'มีข้อมูลบางรอบ และมีรอบที่เก็บไม่สำเร็จ',
                                        'observed' => 'มีข้อมูลที่เก็บสำเร็จ',
                                        'failed' => 'เก็บไม่สำเร็จ',
                                        _ => 'ไม่มีข้อมูลที่เก็บได้',
                                      };
                                      return ListTile(
                                          dense: true,
                                          leading: Icon(
                                              hour.observed
                                                  ? Icons.check_circle_outline
                                                  : Icons.remove_circle_outline,
                                              color: hour.observed
                                                  ? const Color(0xFF168067)
                                                  : Colors.grey),
                                          title: Text(
                                              '${historyTime(hour.at)} - ${historyTime(hour.at.add(const Duration(hours: 1)))}'),
                                          subtitle: Text(
                                              '$label${hour.failures > 0 ? ' (${hour.failures} ครั้ง)' : ''}'));
                                    })),
                            actions: [
                              TextButton(
                                  onPressed: () => Navigator.pop(context),
                                  child: const Text('ปิด'))
                            ],
                          ))),
            ]),
      );

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

  Widget _decisionSummary(TrendHistory data) {
    final matches = data.items.where((item) => item.key == _itemKey);
    if (matches.isEmpty) return const SizedBox.shrink();
    final item = matches.first;
    final movement = item.movement;
    final change = (movement['change'] as num?)?.abs().toInt();
    final label = switch (movement['status']) {
      'up' => 'ขยับขึ้น $change อันดับ',
      'down' => 'ลดลง $change อันดับ',
      'unchanged' => 'อันดับเท่าเดิม',
      'new_entry' => 'พบในรอบนี้ แต่ไม่พบในรอบก่อน',
      'not_in_latest' => 'ไม่พบในรายการรอบล่าสุด',
      'collection_gap' => 'ข้อมูลขาดช่วง ยังสรุปการขยับไม่ได้',
      'empty_sample' => 'รอบที่เปรียบเทียบไม่มีรายการ',
      'latest_unavailable' => 'รอบล่าสุดเก็บข้อมูลไม่ได้',
      'stale' => 'ข้อมูลเก่า ยังสรุปสถานะตอนนี้ไม่ได้',
      _ => 'ยังมีข้อมูลไม่พอเปรียบเทียบอันดับ',
    };
    final at = data.points.last.at;
    final before =
        DateTime.tryParse(movement['from_at']?.toString() ?? '')?.toLocal();
    final interval = data.points.last.viewIntervals[_itemKey];
    Widget fact(String title, String value, String detail) => SizedBox(
        width: 280,
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title, style: Theme.of(context).textTheme.labelMedium),
          const SizedBox(height: 4),
          Text(value, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 4),
          Text(detail, style: Theme.of(context).textTheme.bodySmall),
        ]));
    return Wrap(spacing: 24, runSpacing: 16, children: [
      fact(
          'อันดับที่เก็บได้ล่าสุด',
          item.latestRank == null ? 'ไม่พบในรายการ' : '#${item.latestRank}',
          historyTime(at)),
      fact(
          'การเปลี่ยนอันดับ',
          label,
          before == null
              ? 'ต้องมีข้อมูลอย่างน้อยสองรอบ'
              : '${historyTime(before)} ถึง ${historyTime(at)}'),
      if (widget.platform == 'youtube') ...[
        fact(
            'ยอดวิวสะสม ณ รอบนี้',
            historyNumber(data.points.last.views[_itemKey]),
            'ยอดสะสม ไม่ใช่ยอดวิวที่เพิ่มในช่วงนี้'),
        fact(
            'ยอดวิวเพิ่มจากรอบก่อน',
            interval?.measured == true
                ? '+${historyNumber(interval!.delta)}'
                : 'ยังเปรียบเทียบไม่ได้',
            interval?.measured == true
                ? '${(interval!.seconds! / 60).toStringAsFixed(1)} นาที · เฉลี่ย ${historyNumber(interval.perHour)} ครั้ง/ชม.'
                : viewIntervalStatus(interval?.status)),
      ],
    ]);
  }

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
      if (data.points.length < 2 || occurrences < 2)
        const SizedBox(
            height: 230,
            child: Center(
                child: Text('ยังมีจุดข้อมูลของรายการนี้ไม่พอเปรียบเทียบ')))
      else
        HistoryLineChart(
          points: data.points,
          rank: true,
          color: const Color(0xFF007FAB),
          from: data.requestedFrom,
          to: data.requestedTo,
          value: (p) => p.ranks[_itemKey]?.toDouble(),
          tooltip: (p) => '#${p.ranks[_itemKey]} · รอบ #${p.runId}',
        ),
      const SizedBox(height: 8),
      Text(
          'พบใน $occurrences จาก ${data.points.length} จุดข้อมูล'
          ' · ไม่พบในรายการที่เก็บได้ ไม่ได้หมายถึงอันดับ 0 หรือ 51',
          style: Theme.of(context).textTheme.bodySmall),
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
                  '${historyNumber(interval.perHour)} ครั้ง/ชม. · รอบ #${interval.fromRunId} → #${p.runId}';
            }),
      const SizedBox(height: 8),
      Text(
          '$measured ช่วงที่คำนวณได้ · ยอดวิวต่างกัน ÷ เวลาที่ผ่านไปเป็นชั่วโมง\n'
          'แท่งอยู่ที่เวลาสิ้นสุดช่วง ค่าเฉลี่ยนี้ไม่ใช่การพยากรณ์ยอดวิวชั่วโมงถัดไป',
          style: Theme.of(context).textTheme.bodySmall),
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
              ' (${p.share(_category ?? '')?.toStringAsFixed(1)}%) · รอบ #${p.runId}',
        ),
      const SizedBox(height: 8),
      Text('จำนวนคลิปหมวดนี้ ÷ จำนวนรายการในรอบนั้น × 100',
          style: Theme.of(context).textTheme.bodySmall),
    ]);
  }

  void _showTable(TrendHistory data) {
    final rows = data.points.reversed.toList();
    final youtube = widget.platform == 'youtube';
    final categories = youtube && widget.categoryId == null;
    final source = _HistoryTableSource(rows.length, (index) {
      final p = rows[index];
      final interval = p.viewIntervals[_itemKey];
      return DataRow(cells: [
        DataCell(Text(historyEvidenceTime(p.at))),
        DataCell(Text(p.ranks[_itemKey] == null
            ? 'ไม่พบในรายการ'
            : '#${p.ranks[_itemKey]}')),
        if (youtube) ...[
          DataCell(Text(historyNumber(p.views[_itemKey]))),
          DataCell(Text(historyNumber(interval?.fromViews))),
          DataCell(Text(interval?.measured == true
              ? '+${historyNumber(interval!.delta)}'
              : '-')),
          DataCell(Text(interval?.measured == true
              ? historyNumber(interval!.perHour)
              : '-')),
          DataCell(Text(interval?.from == null
              ? '-'
              : '${historyEvidenceTime(interval!.from!)} ถึง ${historyEvidenceTime(p.at)}\n${interval.seconds!.toStringAsFixed(6)} วินาที')),
          DataCell(Text(viewIntervalStatus(interval?.status))),
        ],
        if (categories)
          DataCell(Text('${p.categories[_category] ?? 0} / ${p.total}')),
        DataCell(Text(youtube
            ? '${interval?.fromRunId ?? '-'} → ${p.runId}'
            : '${p.runId}')),
        DataCell(Text(youtube
            ? '${interval?.fromItemId ?? '-'} → ${p.itemIds[_itemKey] ?? '-'}'
            : '${p.itemIds[_itemKey] ?? '-'}')),
      ]);
    });
    showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
              title: const Text('ข้อมูลที่ใช้วาดกราฟ'),
              content: SizedBox(
                  width: 1120,
                  height: 500,
                  child: SingleChildScrollView(
                    child: PaginatedDataTable(
                        source: source,
                        rowsPerPage: 10,
                        availableRowsPerPage: const [],
                        showFirstLastButtons: true,
                        columns: [
                          const DataColumn(label: Text('วัน / เวลา')),
                          const DataColumn(label: Text('อันดับรายการที่เลือก')),
                          if (youtube) ...[
                            const DataColumn(label: Text('ยอดวิวปลายช่วง')),
                            const DataColumn(label: Text('ยอดวิวต้นช่วง')),
                            const DataColumn(label: Text('ยอดเพิ่มจริง')),
                            const DataColumn(label: Text('เฉลี่ยต่อชั่วโมง')),
                            const DataColumn(
                                label: Text('ช่วงเวลาที่เปรียบเทียบ')),
                            const DataColumn(label: Text('สถานะยอดวิว')),
                          ],
                          if (categories)
                            const DataColumn(
                                label: Text('คลิปหมวดที่เลือก / ทั้งหมด')),
                          const DataColumn(label: Text('รหัสรอบข้อมูล')),
                          const DataColumn(label: Text('รหัสรายการต้นทาง')),
                        ]),
                  )),
              actions: [
                TextButton(
                    onPressed: () => Navigator.pop(context),
                    child: const Text('ปิด'))
              ],
            )).whenComplete(source.dispose);
  }
}

class _HistoryTableSource extends DataTableSource {
  _HistoryTableSource(this.rowCount, this.builder);
  @override
  final int rowCount;
  final DataRow Function(int) builder;
  @override
  DataRow? getRow(int index) => index < rowCount ? builder(index) : null;
  @override
  bool get isRowCountApproximate => false;
  @override
  int get selectedRowCount => 0;
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
