import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../repositories/usage_statistics_repository.dart';

class UsageStatisticsPanel extends StatefulWidget {
  const UsageStatisticsPanel({super.key, this.admin = false, this.repository});
  final bool admin;
  final UsageStatisticsRepository? repository;
  @override
  State<UsageStatisticsPanel> createState() => _UsageStatisticsPanelState();
}

class _UsageStatisticsPanelState extends State<UsageStatisticsPanel> {
  static const months = [
    'มกราคม',
    'กุมภาพันธ์',
    'มีนาคม',
    'เมษายน',
    'พฤษภาคม',
    'มิถุนายน',
    'กรกฎาคม',
    'สิงหาคม',
    'กันยายน',
    'ตุลาคม',
    'พฤศจิกายน',
    'ธันวาคม'
  ];
  late final _repository = widget.repository ?? UsageStatisticsRepository();
  final _today = DateTime.now().toUtc().add(const Duration(hours: 7));
  late int _year = _today.year;
  late int _month = _today.month;
  bool _daily = true, _loading = true;
  int _request = 0;
  Map<String, dynamic>? _data;
  final _scroll = ScrollController();
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final request = ++_request;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await _repository.load(
          year: _year, month: _daily ? _month : null, admin: widget.admin);
      if (mounted && request == _request) {
        setState(() => _data = data);
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (!mounted || request != _request || !_scroll.hasClients) return;
          final rows = (data['series'] as List).cast<Map>();
          final latest =
              rows.lastIndexWhere((row) => (row['count'] as num) > 0);
          final offset = (math.max(0, latest - 2) * 38.0)
              .clamp(0.0, _scroll.position.maxScrollExtent);
          _scroll.jumpTo(offset);
        });
      }
    } catch (_) {
      if (mounted && request == _request) {
        setState(() => _error = 'โหลดสถิติไม่สำเร็จ');
      }
    } finally {
      if (mounted && request == _request) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final rows = (_data?['series'] as List? ?? []).cast<Map>();
    final categories = (_data?['categories'] as List? ?? []).cast<Map>();
    final maximum = rows.fold<int>(
        1, (value, row) => math.max(value, (row['count'] as num).toInt()));
    return Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Wrap(
                alignment: WrapAlignment.spaceBetween,
                crossAxisAlignment: WrapCrossAlignment.center,
                spacing: 16,
                runSpacing: 8,
                children: [
                  Text(
                      widget.admin
                          ? 'สถิติผลวิเคราะห์ทั้งหมด'
                          : 'สถิติผลวิเคราะห์ของฉัน',
                      style: Theme.of(context).textTheme.titleMedium),
                  IconButton(
                      onPressed: _loading ? null : _load,
                      tooltip: 'โหลดสถิติล่าสุด',
                      icon: const Icon(Icons.refresh)),
                ]),
            const SizedBox(height: 8),
            Wrap(
                spacing: 16,
                runSpacing: 12,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  SizedBox(
                      width: 288,
                      child: SegmentedButton<bool>(
                          segments: const [
                            ButtonSegment(
                                value: true,
                                label: Text('รายวัน', maxLines: 1),
                                icon: Icon(Icons.calendar_today)),
                            ButtonSegment(
                                value: false,
                                label: Text('รายเดือน', maxLines: 1),
                                icon: Icon(Icons.date_range)),
                          ],
                          selected: {
                            _daily
                          },
                          onSelectionChanged: _loading
                              ? null
                              : (s) {
                                  setState(() => _daily = s.first);
                                  _load();
                                })),
                  Row(mainAxisSize: MainAxisSize.min, children: [
                    IconButton(
                        tooltip: 'ปีก่อนหน้า',
                        onPressed: _loading || _year <= 2000
                            ? null
                            : () {
                                _year--;
                                _load();
                              },
                        icon: const Icon(Icons.chevron_left)),
                    SizedBox(
                        width: 58,
                        child: Text('$_year', textAlign: TextAlign.center)),
                    IconButton(
                        tooltip: 'ปีถัดไป',
                        onPressed: _loading || _year >= _today.year
                            ? null
                            : () {
                                _year++;
                                _load();
                              },
                        icon: const Icon(Icons.chevron_right)),
                  ]),
                  if (_daily)
                    SizedBox(
                        width: 180,
                        child: DropdownButtonFormField<int>(
                          key: ValueKey(_month),
                          initialValue: _month,
                          isExpanded: true,
                          decoration: const InputDecoration(labelText: 'เดือน'),
                          items: List.generate(
                              12,
                              (i) => DropdownMenuItem(
                                  value: i + 1, child: Text(months[i]))),
                          onChanged: _loading
                              ? null
                              : (v) {
                                  if (v != null) {
                                    _month = v;
                                    _load();
                                  }
                                },
                        )),
                ]),
            const SizedBox(height: 16),
            if (_loading)
              const LinearProgressIndicator()
            else if (_error != null)
              Text(_error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error))
            else ...[
              Text('บันทึกสำเร็จ ${_data?['total'] ?? 0} ผล · เวลาไทย',
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 12),
              SizedBox(
                  height: 228,
                  child: Scrollbar(
                      controller: _scroll,
                      thumbVisibility: true,
                      child: ListView.builder(
                        controller: _scroll,
                        primary: false,
                        itemExtent: 38,
                        itemCount: rows.length,
                        itemBuilder: (context, i) {
                          final row = rows[i];
                          final count = (row['count'] as num).toInt();
                          return Row(children: [
                            SizedBox(
                                width: 100,
                                child: Text(_daily
                                    ? 'วันที่ ${row['index']}'
                                    : months[(row['index'] as int) - 1])),
                            Expanded(
                                child: LinearProgressIndicator(
                                    value: count / maximum, minHeight: 8)),
                            SizedBox(
                                width: 70,
                                child: Text('$count ผล',
                                    textAlign: TextAlign.center)),
                          ]);
                        },
                      ))),
              if (categories.isNotEmpty) ...[
                const SizedBox(height: 16),
                Text('หมวดของผลวิเคราะห์',
                    style: Theme.of(context).textTheme.titleSmall),
                const SizedBox(height: 8),
                Wrap(
                    spacing: 24,
                    runSpacing: 8,
                    children: categories.map((row) {
                      final label = const {
                            'phone': 'มือถือ',
                            'camera': 'กล้อง',
                            'laptop': 'แล็ปท็อป',
                            'unknown': 'อื่น ๆ / ไม่แน่ใจ'
                          }[row['category']] ??
                          row['category'];
                      return Text('$label: ${row['count']} ผล');
                    }).toList()),
              ],
            ],
          ],
        ));
  }
}
