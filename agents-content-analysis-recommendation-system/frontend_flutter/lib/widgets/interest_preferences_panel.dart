import 'package:flutter/material.dart';
import '../models/dashboard_overview.dart';
import '../repositories/dashboard_repository.dart';

class InterestPreferencesPanel extends StatefulWidget {
  const InterestPreferencesPanel(
      {super.key,
      required this.repository,
      required this.topics,
      required this.onChanged});
  final DashboardRepository repository;
  final List<FollowedTopicItem> topics;
  final Future<void> Function() onChanged;
  @override
  State<InterestPreferencesPanel> createState() =>
      _InterestPreferencesPanelState();
}

class _InterestPreferencesPanelState extends State<InterestPreferencesPanel> {
  static const _labels = {
    '1': 'ภาพยนตร์และแอนิเมชัน',
    '2': 'รถยนต์และยานพาหนะ',
    '10': 'เพลงและดนตรี',
    '15': 'สัตว์เลี้ยงและสัตว์',
    '17': 'กีฬา',
    '20': 'เกม',
    '22': 'บุคคลและบล็อก',
    '23': 'ตลก',
    '24': 'บันเทิง',
    '25': 'ข่าวและการเมือง',
    '26': 'วิธีทำและไลฟ์สไตล์',
    '28': 'วิทยาศาสตร์และเทคโนโลยี'
  };
  List<Map> _categories = [];
  String _mode = 'all';
  String? _error;
  bool _loading = true, _busy = false;
  bool _loaded = false;
  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await widget.repository.followPreferences();
      if (mounted) {
        setState(() {
          _mode = data['notification_mode'] as String;
          _categories = (data['categories'] as List).cast<Map>();
          _loaded = true;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _error = 'โหลดการติดตามไม่สำเร็จ');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _change(Future<void> Function() action) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
      await widget.onChanged();
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'บันทึกไม่สำเร็จ กรุณาโหลดค่าล่าสุด');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(children: [
              Expanded(
                  child: Text('หมวดที่ติดตามและการแจ้งเตือน',
                      style: Theme.of(context).textTheme.titleMedium)),
              IconButton(
                  tooltip: 'โหลดการติดตามล่าสุด',
                  onPressed: _busy || _loading ? null : _load,
                  icon: const Icon(Icons.refresh))
            ]),
            if (_loading || _busy) const LinearProgressIndicator(),
            if (_error != null)
              Text(_error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error)),
            const SizedBox(height: 12),
            Text('การแจ้งเตือนเทรนด์ใหม่ระหว่างเข้าสู่ระบบ',
                style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 12),
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (final entry in const {
                'all': 'ทุกเทรนด์',
                'following': 'เฉพาะที่ติดตาม',
                'off': 'ปิดแจ้งเตือน'
              }.entries)
                ChoiceChip(
                    label: Text(entry.value),
                    selected: _mode == entry.key,
                    onSelected: !_loaded || _loading || _busy
                        ? null
                        : (_) => _change(() async {
                              await widget.repository
                                  .saveNotificationMode(entry.key);
                              if (mounted) setState(() => _mode = entry.key);
                            })),
            ]),
            const SizedBox(height: 20),
            const Text('หมวด YouTube'),
            const SizedBox(height: 8),
            LayoutBuilder(
                builder: (context, constraints) => Wrap(children: [
                      for (final category in _categories)
                        SizedBox(
                          width: constraints.maxWidth >= 900
                              ? constraints.maxWidth / 3
                              : constraints.maxWidth >= 600
                                  ? constraints.maxWidth / 2
                                  : constraints.maxWidth,
                          child: CheckboxListTile(
                            contentPadding: EdgeInsets.zero,
                            controlAffinity: ListTileControlAffinity.leading,
                            title: Text(_labels[category['id']] ??
                                '${category['title']}'),
                            value: widget.topics.any((t) =>
                                t.matchType == 'category' &&
                                t.platform == 'youtube' &&
                                t.value == category['id']),
                            onChanged: _loading || _busy
                                ? null
                                : (selected) => _change(() async {
                                      final existing = widget.topics.where(
                                          (t) =>
                                              t.matchType == 'category' &&
                                              t.platform == 'youtube' &&
                                              t.value == category['id']);
                                      if (selected == true) {
                                        await widget.repository.followTopic(
                                            category['id'] as String,
                                            matchType: 'category',
                                            platform: 'youtube');
                                      } else if (existing.isNotEmpty) {
                                        await widget.repository
                                            .unfollowTopic(existing.first.id);
                                      }
                                    }),
                          ),
                        ),
                    ])),
            if (_mode == 'following' && widget.topics.isEmpty)
              const Text(
                  'ยังไม่ได้ติดตามหมวดหรือหัวข้อ จึงยังไม่มีการแจ้งเตือนใหม่'),
          ],
        ));
  }
}
