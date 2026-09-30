import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';
import '../repositories/admin_repository.dart';
import 'state_widgets.dart';

String _time(dynamic value) {
  final date =
      DateTime.tryParse('$value')?.toUtc().add(const Duration(hours: 7));
  if (date == null) return 'ยังไม่มีข้อมูล';
  String two(int n) => n.toString().padLeft(2, '0');
  return '${date.day}/${date.month}/${date.year} ${two(date.hour)}:${two(date.minute)}:${two(date.second)}';
}

String _number(dynamic value) => value is num
    ? (value == value.roundToDouble()
        ? value.toInt().toString()
        : value.toStringAsFixed(2))
    : 'ไม่มีข้อมูล';

String _status(dynamic value) =>
    const {
      'completed': 'เก็บสำเร็จ',
      'complete': 'ข้อมูลครบ',
      'partial': 'ข้อมูลบางส่วน',
      'failed': 'เก็บไม่สำเร็จ',
      'running': 'กำลังเก็บ',
      'interrupted': 'งานถูกขัดจังหวะ',
      'unavailable': 'API ไม่ส่งคลิปนี้กลับมา',
      'counter_correction': 'ยอดถูกปรับลด',
      'observed_interval': 'คำนวณจากช่วงเวลาที่เก็บจริง',
      'not_comparable': 'เปรียบเทียบไม่ได้',
      'not_due': 'เพิ่งเก็บข้อมูลไป ยังไม่ถึงรอบถัดไป',
      'quota_wait': 'พักรอโควตา API',
      'busy': 'มีงานเก็บข้อมูลกำลังทำงานอยู่',
      'paused': 'พักการเก็บข้อมูล',
      'no_candidates': 'ยังไม่มีคลิปอ้างอิงผ่านเกณฑ์',
      'queued': 'รอเริ่มเก็บสถิติ',
    }[value] ??
    'ยังไม่มีข้อมูล';

class ReferenceStatisticsPanel extends StatefulWidget {
  const ReferenceStatisticsPanel({super.key, required this.repository});
  final AdminRepository repository;
  @override
  State<ReferenceStatisticsPanel> createState() =>
      _ReferenceStatisticsPanelState();
}

class _ReferenceStatisticsPanelState extends State<ReferenceStatisticsPanel> {
  Map<String, dynamic>? _data;
  String? _error;
  bool _loading = true, _saving = false, _enabled = true;
  int _offset = 0, _interval = 3600;
  final _budget = TextEditingController();
  Timer? _timer;
  String? _jobId, _jobStatus;
  int _request = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _timer?.cancel();
    _budget.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final request = ++_request;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await widget.repository.referenceStatistics(offset: _offset);
      if (!mounted || request != _request) return;
      setState(() {
        _data = data;
        final settings = data['settings'] as Map;
        _enabled = settings['enabled'] == true;
        _interval = (settings['interval_seconds'] as num).toInt();
        _budget.text = '${settings['daily_request_budget']}';
      });
    } catch (_) {
      if (mounted && request == _request) {
        setState(() => _error = 'โหลดประวัติสถิติไม่สำเร็จ');
      }
    } finally {
      if (mounted && request == _request) setState(() => _loading = false);
    }
  }

  Future<void> _save() async {
    final budget = int.tryParse(_budget.text);
    if (budget == null || budget < 1 || budget > 1000) {
      setState(() => _error = 'ระบุจำนวนคำขอ 1 ถึง 1,000 ต่อวัน');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.repository.saveReferenceStatisticsSettings({
        'enabled': _enabled,
        'interval_seconds': _interval,
        'daily_request_budget': budget,
      });
      if (mounted) await _load();
    } catch (_) {
      if (mounted) setState(() => _error = 'บันทึกรอบเก็บสถิติไม่สำเร็จ');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _refresh() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final jobId = await widget.repository.refreshReferenceStatistics();
      if (!mounted) return;
      setState(() {
        _jobId = jobId;
        _jobStatus = 'queued';
      });
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('ส่งงานอัปเดตสถิติแล้ว')));
      _timer?.cancel();
      _timer = Timer(const Duration(seconds: 2), _pollJob);
    } catch (_) {
      if (mounted) setState(() => _error = 'ส่งงานไม่สำเร็จ');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _pollJob() async {
    final id = _jobId;
    if (id == null || !mounted) return;
    try {
      final job = await widget.repository.referenceStatisticsJob(id);
      if (!mounted) return;
      final done = job['status'] == 'completed' ||
          job['status'] == 'failed' ||
          job['status'] == 'not_found';
      setState(() {
        _jobStatus = job['status'] == 'completed'
            ? (job['result']?['status'] as String?)
            : (job['status'] as String?);
        if (done) _jobId = null;
      });
      if (done) {
        await _load();
      } else {
        _timer = Timer(const Duration(seconds: 3), _pollJob);
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _jobId = null;
          _error = 'ตรวจสถานะงานไม่สำเร็จ ตรวจประวัติรอบเก็บได้อีกครั้ง';
        });
      }
    }
  }

  Future<void> _history(int id) async {
    await showDialog<void>(
        context: context,
        builder: (_) =>
            _StatisticsHistoryDialog(repository: widget.repository, id: id));
  }

  @override
  Widget build(BuildContext context) {
    final data = _data;
    final settings = data?['settings'] as Map?;
    final theme = Theme.of(context);
    return ListView(padding: const EdgeInsets.all(24), children: [
      Center(
          child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 1200),
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Row(children: [
                      Expanded(
                          child: Text('สถิติคลิปอ้างอิง',
                              style: theme.textTheme.titleLarge)),
                      IconButton(
                          tooltip: 'โหลดสถิติล่าสุด',
                          onPressed: _loading || _saving ? null : _load,
                          icon: const Icon(Icons.refresh))
                    ]),
                    if (_loading) const LinearProgressIndicator(),
                    if (_error != null)
                      Text(_error!,
                          style: TextStyle(color: theme.colorScheme.error)),
                    if (_jobStatus != null) Text(_status(_jobStatus)),
                    if (settings != null) ...[
                      ExpansionTile(
                          tilePadding: EdgeInsets.zero,
                          title: const Text('รอบเก็บสถิติและงบคำขอ API'),
                          children: [
                            SwitchListTile(
                                contentPadding: EdgeInsets.zero,
                                title:
                                    const Text('เก็บสถิติคลิปอ้างอิงอัตโนมัติ'),
                                value: _enabled,
                                onChanged: _saving
                                    ? null
                                    : (v) => setState(() => _enabled = v)),
                            Wrap(spacing: 16, runSpacing: 16, children: [
                              SizedBox(
                                  width: 260,
                                  child: DropdownButtonFormField<int>(
                                      key: ValueKey(_interval),
                                      initialValue: _interval,
                                      isExpanded: true,
                                      decoration: const InputDecoration(
                                          labelText: 'รอบอัปเดต'),
                                      items: ({
                                        3600,
                                        10800,
                                        21600,
                                        86400,
                                        _interval
                                      }.toList()
                                            ..sort())
                                          .map((v) => DropdownMenuItem(
                                              value: v,
                                              child: Text(
                                                  'ทุก ${_number(v / 3600)} ชั่วโมง')))
                                          .toList(),
                                      onChanged: _saving
                                          ? null
                                          : (v) =>
                                              setState(() => _interval = v!))),
                              SizedBox(
                                  width: 260,
                                  child: TextField(
                                      controller: _budget,
                                      enabled: !_saving,
                                      keyboardType: TextInputType.number,
                                      inputFormatters: [
                                        FilteringTextInputFormatter.digitsOnly
                                      ],
                                      decoration: const InputDecoration(
                                          labelText:
                                              'งบคำขอ/วัน เฉพาะสถิติคลิป'))),
                              FilledButton.icon(
                                  onPressed: _saving ? null : _save,
                                  icon: const Icon(Icons.save_outlined),
                                  label: const Text('บันทึก')),
                            ]),
                            const SizedBox(height: 16),
                          ]),
                      const SizedBox(height: 16),
                      Text(
                          'คลิปอ้างอิง ${settings['candidate_count']} รายการ · ${settings['requests_per_round']} คำขอ/รอบ · ประมาณ ${settings['estimated_requests_per_day']} คำขอ/วัน'),
                      Text(
                          'ใช้ไป ${settings['requests_used_today']}/${settings['daily_request_budget']} คำขอวันนี้ (เวลาไทย) · ไม่รวมโควตาดึงเทรนด์และงานอื่น'),
                      if ((settings['effective_interval_seconds'] as num? ??
                              _interval) >
                          _interval)
                        Text(
                            'รอบที่ปรับตามงบ: ทุก ${_number((settings['effective_interval_seconds'] as num) / 3600)} ชั่วโมง'),
                      Text(
                          'ครบช่วงอัปเดตครั้งถัดไป: ${_time(settings['next_due_at'])}'),
                      if (settings['blocked_until'] != null)
                        Text(
                            'พักหลัง API แจ้งโควตา: ${_time(settings['blocked_until'])}'),
                      const SizedBox(height: 12),
                      Align(
                          alignment: Alignment.centerLeft,
                          child: OutlinedButton.icon(
                              onPressed: _saving ||
                                      _loading ||
                                      !_enabled ||
                                      _jobId != null
                                  ? null
                                  : _refresh,
                              icon: const Icon(Icons.sync),
                              label: const Text('อัปเดตสถิติตอนนี้'))),
                      const SizedBox(height: 20),
                      Text('ยอดสะสมและการเพิ่มระหว่างสองเวลา',
                          style: theme.textTheme.titleMedium),
                      const SizedBox(height: 8),
                      for (final item in data!['items'] as List) ...[
                        const Divider(),
                        ListTile(
                            contentPadding: EdgeInsets.zero,
                            title:
                                Text('#${item['dataset_id']} ${item['title']}'),
                            subtitle: Padding(
                                padding: const EdgeInsets.only(top: 8),
                                child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                          '${item['category']} · เก็บเมื่อ ${_time(item['latest']?['observed_at'])}'),
                                      Text(
                                          'ยอดวิว ${_number(item['latest']?['views'])} · ไลก์ ${_number(item['latest']?['likes'])} · ความคิดเห็น ${_number(item['latest']?['comments'])}'),
                                      if (item['has_growth'] == true) ...[
                                        Text(
                                            'วิวเพิ่ม ${_number(item['latest']['growth']['views_delta'])} ใน ${_number(item['latest']['growth']['elapsed_hours'])} ชั่วโมง · เฉลี่ย ${_number(item['latest']['growth']['views_per_hour'])} วิว/ชั่วโมง'),
                                        Text(
                                            '${_time(item['latest']['growth']['from_at'])} ถึง ${_time(item['latest']['growth']['to_at'])}'),
                                      ] else
                                        Text(item['latest']?['growth']
                                                    ?['status'] ==
                                                'counter_correction'
                                            ? 'ยอดถูกปรับลด ยังไม่สรุปอัตราเติบโต'
                                            : 'ยังไม่มีข้อมูลสองครั้งที่เปรียบเทียบการเติบโตได้'),
                                      if (item['latest'] != null)
                                        Text(_status(item['latest']['status'])),
                                      if (item['reference_eligible'] != true)
                                        const Text(
                                            'เก็บประวัติไว้ แต่ปัจจุบันไม่ผ่านเกณฑ์คลิปอ้างอิง'),
                                    ])),
                            trailing: IconButton(
                                tooltip:
                                    'ดูประวัติสถิติ #${item['dataset_id']}',
                                icon: const Icon(Icons.history),
                                onPressed: () => _history(
                                    (item['dataset_id'] as num).toInt()))),
                      ],
                      if ((data['items'] as List).isEmpty)
                        const Text('ยังไม่มีคลิปอ้างอิงที่ผ่านเกณฑ์'),
                      PaginationBar(
                          offset: _offset,
                          limit: 20,
                          total: (data['total'] as num).toInt(),
                          onPrevious: _offset == 0 || _loading
                              ? null
                              : () {
                                  _offset -= 20;
                                  _load();
                                },
                          onNext:
                              _loading || _offset + 20 >= (data['total'] as num)
                                  ? null
                                  : () {
                                      _offset += 20;
                                      _load();
                                    }),
                      const Divider(),
                      Text('ประวัติรอบเก็บล่าสุด',
                          style: theme.textTheme.titleMedium),
                      for (final run in data['runs'] as List)
                        Padding(
                            padding: const EdgeInsets.symmetric(vertical: 6),
                            child: Text(
                                '#${run['run_id']} · ${_time(run['started_at'])} · ${_status(run['status'])} · ${run['requests_used']} คำขอ${run['error_code'] == null ? '' : ' · ${run['error_code']}'}')),
                    ],
                  ]))),
    ]);
  }
}

class _StatisticsHistoryDialog extends StatefulWidget {
  const _StatisticsHistoryDialog({required this.repository, required this.id});
  final AdminRepository repository;
  final int id;
  @override
  State<_StatisticsHistoryDialog> createState() =>
      _StatisticsHistoryDialogState();
}

class _StatisticsHistoryDialogState extends State<_StatisticsHistoryDialog> {
  late Future<Map<String, dynamic>> _future;
  @override
  void initState() {
    super.initState();
    _future = widget.repository.referenceStatisticsHistory(widget.id);
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
          title: Text('ประวัติสถิติ #${widget.id}'),
          content: SizedBox(
              width: 950,
              height: 480,
              child: FutureBuilder<Map<String, dynamic>>(
                  future: _future,
                  builder: (context, snapshot) {
                    if (snapshot.hasError) {
                      return Center(
                          child: TextButton.icon(
                              onPressed: () => setState(() {
                                    _future = widget.repository
                                        .referenceStatisticsHistory(widget.id);
                                  }),
                              icon: const Icon(Icons.refresh),
                              label: const Text('โหลดไม่สำเร็จ ลองอีกครั้ง')));
                    }
                    if (!snapshot.hasData) {
                      return const Center(child: CircularProgressIndicator());
                    }
                    final data = snapshot.data!;
                    final points = data['points'] as List;
                    if (points.isEmpty) {
                      return const Center(
                          child: Text('ยังไม่มีประวัติสถิติจาก API'));
                    }
                    return ListView(children: [
                      Text('${data['title']}'),
                      for (final point in points.reversed)
                        ListTile(
                            contentPadding: EdgeInsets.zero,
                            title: Text(
                                '${_time(point['observed_at'])} · ${_status(point['status'])}'),
                            subtitle: Text(
                                'วิว ${_number(point['views'])} · ไลก์ ${_number(point['likes'])} · ความคิดเห็น ${_number(point['comments'])}\nรอบ #${point['run_id']} · Video ID ${point['video_id']}'),
                            trailing: IconButton(
                                tooltip: 'เปิดคลิปต้นทาง',
                                icon: const Icon(Icons.open_in_new),
                                onPressed: () {
                                  final uri =
                                      Uri.tryParse('${point['source_url']}');
                                  if (uri != null &&
                                      uri.scheme == 'https' &&
                                      uri.host == 'www.youtube.com') {
                                    launchUrl(uri);
                                  }
                                })),
                    ]);
                  })),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('ปิด'))
          ]);
}
