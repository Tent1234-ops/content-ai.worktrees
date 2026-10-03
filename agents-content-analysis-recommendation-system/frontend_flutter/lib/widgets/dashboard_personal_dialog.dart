import 'package:flutter/material.dart';

import '../models/dashboard_overview.dart';
import '../repositories/dashboard_repository.dart';
import '../state/auth_scope.dart';
import 'interest_preferences_panel.dart';

class DashboardPersonalDialog extends StatefulWidget {
  const DashboardPersonalDialog(
      {super.key,
      required this.repository,
      required this.following,
      required this.ownerId});
  final DashboardRepository repository;
  final bool following;
  final int ownerId;

  @override
  State<DashboardPersonalDialog> createState() =>
      _DashboardPersonalDialogState();
}

class _DashboardPersonalDialogState extends State<DashboardPersonalDialog> {
  List<NotificationItem> _notifications = [];
  List<FollowedTopicItem> _topics = [];
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _read() async {
    if (widget.following) {
      final topics = await widget.repository.getFollowedTopics();
      if (mounted) {
        setState(() =>
            _topics = topics.where((t) => t.platform != 'tiktok').toList());
      }
    } else {
      final notifications =
          await widget.repository.getNotifications(limit: 100);
      if (mounted) {
        setState(() => _notifications =
            notifications.where((n) => n.platform != 'tiktok').toList());
      }
    }
  }

  Future<void> _refresh() => _perform(_read);

  Future<void> _perform(Future<void> Function() action) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'ดำเนินการไม่สำเร็จ กรุณาลองอีกครั้ง');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = AuthScope.of(context);
    final allowed = auth.isAuthenticated && auth.user?.userId == widget.ownerId;
    final unread =
        _notifications.where((n) => !n.isRead).map((n) => n.id).toList();
    final topics = _topics.where((t) => t.matchType != 'category').toList();
    return AlertDialog(
      title: Row(children: [
        Icon(widget.following
            ? Icons.bookmarks_outlined
            : Icons.notifications_outlined),
        const SizedBox(width: 12),
        Expanded(
            child: Text(
                widget.following ? 'หัวข้อที่ติดตาม' : 'การแจ้งเตือนเทรนด์')),
        IconButton(
            tooltip: 'ปิด',
            onPressed: () => Navigator.pop(context),
            icon: const Icon(Icons.close)),
      ]),
      content: SizedBox(
          width: 620,
          height: 520,
          child: !allowed
              ? const Center(
                  child: Text('กรุณาเข้าสู่ระบบเพื่อดูข้อมูลส่วนตัว'))
              : Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                      if (_busy) const LinearProgressIndicator(),
                      if (_error != null)
                        Text(_error!,
                            style: TextStyle(
                                color: Theme.of(context).colorScheme.error)),
                      Row(mainAxisAlignment: MainAxisAlignment.end, children: [
                        if (!widget.following && unread.isNotEmpty)
                          TextButton.icon(
                            icon: const Icon(Icons.done_all),
                            label: const Text('ทำเครื่องหมายอ่านแล้ว'),
                            onPressed: _busy
                                ? null
                                : () => _perform(() async {
                                      await widget.repository
                                          .markNotificationsRead(unread);
                                      await _read();
                                    }),
                          ),
                        IconButton(
                            tooltip: 'โหลดรายการล่าสุด',
                            onPressed: _busy ? null : _refresh,
                            icon: const Icon(Icons.refresh)),
                      ]),
                      Expanded(
                          child: ListView(
                              children: widget.following
                                  ? [
                                      if (!_busy && topics.isEmpty)
                                        const Padding(
                                            padding: EdgeInsets.all(16),
                                            child: Text(
                                                'ยังไม่มีหัวข้อที่ติดตาม')),
                                      for (final topic in topics)
                                        ListTile(
                                          contentPadding: EdgeInsets.zero,
                                          leading: const Icon(
                                              Icons.bookmark_outline),
                                          title: Text(topic.value),
                                          trailing: IconButton(
                                            tooltip: 'เลิกติดตาม',
                                            icon: const Icon(
                                                Icons.bookmark_remove_outlined),
                                            onPressed: _busy
                                                ? null
                                                : () => _perform(() async {
                                                      await widget.repository
                                                          .unfollowTopic(
                                                              topic.id);
                                                      await _read();
                                                    }),
                                          ),
                                        ),
                                      const Divider(),
                                      ExpansionTile(
                                          title: const Text(
                                              'จัดการหมวดและการแจ้งเตือน'),
                                          children: [
                                            InterestPreferencesPanel(
                                                repository: widget.repository,
                                                topics: _topics,
                                                onChanged: _read),
                                          ]),
                                    ]
                                  : [
                                      if (!_busy && _notifications.isEmpty)
                                        const Padding(
                                            padding: EdgeInsets.all(16),
                                            child: Text(
                                                'ยังไม่มีการแจ้งเตือนเทรนด์')),
                                      for (final item in _notifications)
                                        ListTile(
                                          contentPadding: EdgeInsets.zero,
                                          leading: Icon(
                                              item.isRead
                                                  ? Icons.notifications_none
                                                  : Icons.notifications_active,
                                              color: item.isRead
                                                  ? Theme.of(context)
                                                      .disabledColor
                                                  : Theme.of(context)
                                                      .colorScheme
                                                      .primary),
                                          title: Text(item.title),
                                          subtitle: Text(
                                              '${item.platform == 'youtube' ? 'YouTube' : 'Google'} · ${_time(item.detectedAt)}'),
                                          trailing: item.isRead
                                              ? null
                                              : IconButton(
                                                  tooltip: 'อ่านแล้ว',
                                                  icon: const Icon(Icons.done),
                                                  onPressed: _busy
                                                      ? null
                                                      : () =>
                                                          _perform(() async {
                                                            await widget
                                                                .repository
                                                                .markNotificationsRead(
                                                                    [item.id]);
                                                            await _read();
                                                          }),
                                                ),
                                        ),
                                    ])),
                    ])),
    );
  }

  String _time(String raw) {
    final at = DateTime.tryParse(raw)?.toLocal();
    if (at == null) return '';
    return '${at.day}/${at.month}/${at.year} ${at.hour.toString().padLeft(2, '0')}:${at.minute.toString().padLeft(2, '0')}';
  }
}
