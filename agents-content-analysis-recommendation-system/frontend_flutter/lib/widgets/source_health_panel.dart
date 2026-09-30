import 'package:flutter/material.dart';
import '../repositories/admin_repository.dart';

class SourceHealthPanel extends StatefulWidget {
  const SourceHealthPanel({super.key, required this.repository});
  final AdminRepository repository;
  @override
  State<SourceHealthPanel> createState() => _SourceHealthPanelState();
}

class _SourceHealthPanelState extends State<SourceHealthPanel> {
  Map<String, dynamic>? _data;
  bool _loading = true;
  bool _error = false;
  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = false;
    });
    try {
      final data = await widget.repository
          .sourceHealth()
          .timeout(const Duration(seconds: 20));
      if (mounted) setState(() => _data = data);
    } catch (_) {
      if (mounted) setState(() => _error = true);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  String _time(dynamic value) {
    final parsed = DateTime.tryParse(value?.toString() ?? '')?.toLocal();
    if (parsed == null) return 'ยังไม่มีข้อมูล';
    return '${parsed.day}/${parsed.month}/${parsed.year} ${parsed.hour.toString().padLeft(2, '0')}:${parsed.minute.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    Widget itemTile(Map row) => ExpansionTile(
            tilePadding: EdgeInsets.zero,
            leading: Icon(
                row['status'] == 'observed'
                    ? Icons.check_circle_outline
                    : Icons.info_outline,
                color: row['status'] == 'observed'
                    ? Theme.of(context).colorScheme.secondary
                    : Theme.of(context).colorScheme.error),
            title: Text(
                '${row['platform'] == 'youtube' ? 'YouTube' : 'Google'} · ${row['scope'] == 'global' ? 'อันดับรวม' : 'หมวด ${row['scope'].toString().split(':').last}'}'),
            subtitle: Text('${const {
                      'observed': 'รอบล่าสุดมีข้อมูล',
                      'failed': 'รอบล่าสุดเก็บไม่สำเร็จ',
                      'stale': 'ไม่มีข้อมูลใหม่เกิน 24 ชั่วโมง',
                      'empty': 'ต้นทางส่งรายการว่าง',
                      'excluded_mock': 'ข้อมูลจำลอง ไม่ใช้เป็นหลักฐาน',
                      'no_data': 'ยังไม่มีประวัติ'
                    }[row['status']] ?? 'ยังไม่ทราบสถานะ'}'
                ' · สำเร็จ ${row['observed_24h'] ?? 0} / ไม่สำเร็จ ${row['failed_24h'] ?? 0} ครั้งใน 24 ชม.'),
            children: [
              Align(
                  alignment: Alignment.centerLeft,
                  child: Padding(
                      padding: const EdgeInsets.only(bottom: 16),
                      child: Text(
                          'พยายามเก็บล่าสุด: ${_time(row['last_attempt_at'])}\n'
                          'สำเร็จล่าสุด: ${_time(row['last_success_at'])}\n'
                          'รอบ #${row['last_run_id'] ?? '-'} · ${row['sample_count'] ?? '-'} รายการ\n'
                          '${row['status'] == 'failed' ? 'ตรวจบันทึกการทำงานระบบและรอบอัปเดตที่ตั้งไว้' : row['status'] == 'stale' || row['status'] == 'no_data' ? 'ตรวจว่าเปิดตัวเก็บข้อมูลและถึงรอบตามตารางแล้วหรือไม่' : 'สถานะนี้อ้างอิงรอบที่เก็บไว้ ไม่ใช่การทดสอบการเชื่อมต่อสด'}')))
            ]);
    final rows = (_data?['items'] as List? ?? []).cast<Map>();
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Row(children: [
        const Icon(Icons.monitor_heart_outlined),
        const SizedBox(width: 8),
        Expanded(
            child: Text('สุขภาพแหล่งข้อมูล',
                style: Theme.of(context).textTheme.titleMedium)),
        IconButton(
            onPressed: _loading ? null : _load,
            icon: const Icon(Icons.refresh),
            tooltip: 'ตรวจสถานะแหล่งข้อมูลอีกครั้ง')
      ]),
      if (_loading)
        const LinearProgressIndicator()
      else if (_error)
        const Text(
            'โหลดสถานะแหล่งข้อมูลไม่สำเร็จ ยังยืนยันสุขภาพแหล่งข้อมูลไม่ได้')
      else if (rows.isEmpty)
        const Text('ยังไม่มีประวัติการเก็บข้อมูล')
      else ...[
        Text(
            '${_data?['region'] == 'TH' ? 'ประเทศไทย' : _data?['region']} · ตรวจจากประวัติ ณ ${_time(_data?['checked_at'])}',
            style: Theme.of(context).textTheme.bodySmall),
        for (final row in rows.where((row) => row['scope'] == 'global'))
          itemTile(row),
        if (rows.any((row) => row['scope'] != 'global'))
          ExpansionTile(
              tilePadding: EdgeInsets.zero,
              title: const Text('สถานะอันดับรายหมวดของ YouTube'),
              children: [
                for (final row in rows.where((row) => row['scope'] != 'global'))
                  itemTile(row)
              ]),
      ],
    ]);
  }
}
