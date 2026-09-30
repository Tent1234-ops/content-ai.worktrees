import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../repositories/admin_repository.dart';
import 'source_health_panel.dart';

class TrendSettingsPanel extends StatefulWidget {
  const TrendSettingsPanel({super.key, required this.repository});
  final AdminRepository repository;
  @override
  State<TrendSettingsPanel> createState() => _TrendSettingsPanelState();
}

class _TrendSettingsPanelState extends State<TrendSettingsPanel> {
  final _form = GlobalKey<FormState>();
  final _global = TextEditingController(), _category = TextEditingController();
  bool _enabled = true, _loading = true, _saving = false;
  String _mode = 'interval';
  int _startHour = 14, _endHour = 23;
  String? _error;
  Map<String, dynamic>? _data;
  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _global.dispose();
    _category.dispose();
    super.dispose();
  }

  void _apply(Map<String, dynamic> data) {
    _data = data;
    _enabled = data['enabled'] == true;
    _global.text = '${data['global_interval_seconds']}';
    _category.text = '${data['category_interval_seconds']}';
    _mode = data['schedule_mode'] as String? ?? 'interval';
    _startHour = (data['window']?['start_hour'] as num?)?.toInt() ?? 14;
    _endHour = (data['window']?['end_hour'] as num?)?.toInt() ?? 23;
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await widget.repository.trendSettings();
      if (mounted) setState(() => _apply(data));
    } catch (_) {
      if (mounted) setState(() => _error = 'โหลดรอบอัปเดตไม่สำเร็จ');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _save() async {
    if (!_form.currentState!.validate()) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final data = await widget.repository.saveTrendSettings({
        'enabled': _enabled,
        'global_interval_seconds':
            _mode == 'hourly_window' ? 3600 : int.parse(_global.text),
        'category_interval_seconds':
            _mode == 'hourly_window' ? 3600 : int.parse(_category.text),
        'schedule_mode': _mode,
        'start_hour': _startHour,
        'end_hour': _endHour,
      });
      if (!mounted) return;
      setState(() => _apply(data));
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('บันทึกรอบอัปเดตเทรนด์แล้ว')));
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'บันทึกไม่สำเร็จ ค่ายังไม่ถูกยืนยัน');
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Widget _seconds(TextEditingController controller, String label) =>
      TextFormField(
        controller: controller,
        enabled: !_saving,
        keyboardType: TextInputType.number,
        inputFormatters: [FilteringTextInputFormatter.digitsOnly],
        decoration: InputDecoration(labelText: label, suffixText: 'วินาที'),
        validator: (v) {
          final n = int.tryParse(v ?? '');
          return n == null || n < 60 || n > 86400
              ? 'ระบุ 60 ถึง 86400 วินาที'
              : null;
        },
      );

  String _hour(int value) => '${value.toString().padLeft(2, '0')}:00';

  Widget _hourInput(String label, int value, ValueChanged<int> change) =>
      DropdownButtonFormField<int>(
        initialValue: value,
        key: ValueKey('$label:$value'),
        decoration: InputDecoration(labelText: label),
        items: List.generate(
            24, (h) => DropdownMenuItem(value: h, child: Text(_hour(h)))),
        onChanged: _saving
            ? null
            : (h) {
                if (h != null) change(h);
              },
        validator: (_) =>
            _endHour < _startHour ? 'รอบสุดท้ายต้องไม่ก่อนรอบแรก' : null,
      );

  String _status(dynamic status) =>
      const {
        'completed': 'สำเร็จ',
        'partial': 'ได้ข้อมูลบางส่วน',
        'failed': 'ไม่สำเร็จ',
        'running': 'กำลังเก็บ',
        'pending': 'ถึงเวลาแล้ว',
        'upcoming': 'ยังไม่ถึงเวลา',
        'missed': 'ไม่ได้เก็บในรอบนี้',
        'interrupted': 'งานถูกขัดจังหวะ',
        'not_due': 'ตรวจแล้ว ยังไม่มีรอบที่ต้องเก็บ',
        'paused': 'พักการเก็บ',
        'busy': 'มีตัวเก็บข้อมูลทำงานอยู่',
        'interval_mode': 'ใช้รอบจาก Backend',
        'already_claimed': 'รอบนี้มีผู้รับงานแล้ว',
      }[status] ??
      'ยังไม่มีข้อมูล';

  String _time(dynamic text) {
    final time =
        DateTime.tryParse('$text')?.toUtc().add(const Duration(hours: 7));
    if (time == null) return 'ยังไม่มีข้อมูล';
    return '${time.day}/${time.month}/${time.year} ${time.hour.toString().padLeft(2, '0')}:${time.minute.toString().padLeft(2, '0')}:${time.second.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) => Padding(
      padding: const EdgeInsets.all(24),
      child: Center(
        child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 880),
            child: Form(
                key: _form,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    SourceHealthPanel(repository: widget.repository),
                    const Divider(height: 32),
                    Row(children: [
                      Expanded(
                          child: Text('รอบอัปเดตเทรนด์',
                              style: Theme.of(context).textTheme.titleLarge)),
                      IconButton(
                          tooltip: 'โหลดรอบอัปเดตล่าสุด',
                          onPressed: _saving || _loading ? null : _load,
                          icon: const Icon(Icons.refresh)),
                    ]),
                    if (_loading) const LinearProgressIndicator(),
                    if (_error != null)
                      Padding(
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          child: Text(_error!,
                              style: TextStyle(
                                  color: Theme.of(context).colorScheme.error))),
                    if (_data != null) ...[
                      SwitchListTile.adaptive(
                          contentPadding: EdgeInsets.zero,
                          title: const Text('อัปเดตอัตโนมัติ'),
                          value: _enabled,
                          onChanged: _saving
                              ? null
                              : (v) => setState(() => _enabled = v)),
                      const SizedBox(height: 24),
                      SegmentedButton<String>(
                        segments: const [
                          ButtonSegment(
                              value: 'hourly_window',
                              icon: Icon(Icons.schedule),
                              label: Text('ตามเวลารายวัน')),
                          ButtonSegment(
                              value: 'interval',
                              icon: Icon(Icons.timer_outlined),
                              label: Text('ตามช่วงเวลา')),
                        ],
                        selected: {_mode},
                        onSelectionChanged: _saving
                            ? null
                            : (v) => setState(() => _mode = v.first),
                      ),
                      const SizedBox(height: 24),
                      if (_mode == 'hourly_window') ...[
                        Row(children: [
                          Expanded(
                              child: _hourInput('รอบแรก', _startHour,
                                  (v) => setState(() => _startHour = v))),
                          const SizedBox(width: 16),
                          Expanded(
                              child: _hourInput('รอบสุดท้าย', _endHour,
                                  (v) => setState(() => _endHour = v))),
                        ]),
                        const SizedBox(height: 16),
                        Text(
                            'ทุก 1 ชั่วโมง · ${_endHour >= _startHour ? _endHour - _startHour + 1 : 0} รอบ/วัน · เวลาไทย'),
                        const SizedBox(height: 8),
                        Text(_endHour >= _startHour
                            ? List.generate(_endHour - _startHour + 1,
                                (i) => _hour(_startHour + i)).join('  ·  ')
                            : ''),
                      ] else ...[
                        _seconds(_global, 'อันดับรวมแต่ละแพลตฟอร์ม'),
                        const SizedBox(height: 24),
                        _seconds(_category, 'อันดับรายหมวด YouTube'),
                      ],
                      const SizedBox(height: 24),
                      Align(
                          alignment: Alignment.centerLeft,
                          child: FilledButton.icon(
                              onPressed: _saving || _loading ? null : _save,
                              icon: const Icon(Icons.save_outlined),
                              label: Text(_saving
                                  ? 'กำลังบันทึก'
                                  : 'บันทึกรอบอัปเดต'))),
                      const SizedBox(height: 24),
                      Text('สถานะจากระบบ',
                          style: Theme.of(context).textTheme.titleMedium),
                      if (_data![
                              'estimated_youtube_video_list_calls_per_day'] !=
                          null)
                        Text(
                            'ประมาณ ${_data!['estimated_youtube_video_list_calls_per_day']} คำขอ videos.list/วัน ตามรอบที่ตั้ง · ไม่รวมรายชื่อหมวด สถิติคลิป และการกดอัปเดตเอง'),
                      const Divider(),
                      if (_data!['schedule_mode'] == 'hourly_window') ...[
                        Text(_data!['enabled'] == true
                            ? 'รอบที่ถึงเวลาถัดไป: ${_time(_data!['window']['next_at'])}'
                            : 'พักอัปเดตอัตโนมัติ'),
                        Text(
                            'สคริปต์ภายนอกติดต่อล่าสุด: ${_time(_data!['worker']?['last_seen_at'])}'),
                        Text(
                            'ผลตรวจครั้งล่าสุด: ${_status(_data!['worker']?['status'])}'),
                        const SizedBox(height: 16),
                        Text('รอบวันนี้',
                            style: Theme.of(context).textTheme.titleMedium),
                        for (final slot
                            in (_data!['window']['slots_today'] as List? ?? []))
                          ListTile(
                            dense: true,
                            contentPadding: EdgeInsets.zero,
                            leading: Icon(
                                slot['status'] == 'completed'
                                    ? Icons.check_circle_outline
                                    : slot['status'] == 'failed'
                                        ? Icons.error_outline
                                        : Icons.schedule,
                                color: slot['status'] == 'completed'
                                    ? Colors.green
                                    : null),
                            title: Text(
                                '${_time(slot['scheduled_for'])} · ${_status(slot['status'])}'),
                            subtitle: slot['started_at'] == null
                                ? null
                                : Text(
                                    'เริ่มจริง ${_time(slot['started_at'])} · ${slot['actor'] == 'task_scheduler' ? 'Windows Scheduler' : 'Backend'}'),
                          ),
                        const Divider(),
                      ],
                      for (final entry in const {
                        'global': 'อันดับรวม',
                        'youtube_categories': 'รายหมวด YouTube'
                      }.entries) ...[
                        Text(entry.value,
                            style: Theme.of(context).textTheme.titleSmall),
                        Text(
                            'ได้ข้อมูลล่าสุด: ${_time(_data!['runs'][entry.key]['last_success_at'])}'),
                        if (_data!['schedule_mode'] != 'hourly_window')
                          Text(_data!['enabled'] == true
                              ? 'ครบกำหนดรอบถัดไป: ${_time(_data!['runs'][entry.key]['next_at'])}'
                              : 'พักอัปเดตอัตโนมัติ'),
                        const SizedBox(height: 16),
                      ],
                    ],
                  ],
                ))),
      ));
}
