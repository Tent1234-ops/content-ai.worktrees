import 'package:flutter/material.dart';

import '../models/system_log.dart';
import '../repositories/admin_repository.dart';
import '../utils/system_log_presenter.dart';
import '../widgets/app_shell.dart';
import '../widgets/state_widgets.dart';

class AdminLogsScreen extends StatefulWidget {
  const AdminLogsScreen({super.key, this.repository});

  final AdminRepository? repository;

  @override
  State<AdminLogsScreen> createState() => _AdminLogsScreenState();
}

class _AdminLogsScreenState extends State<AdminLogsScreen> {
  late final AdminRepository _repository;
  List<SystemLogItem> _items = [];
  String _status = 'all';
  String? _error;
  bool _loading = false;
  int _offset = 0;
  final int _limit = 16;
  int _total = 0;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? AdminRepository();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final response = await _repository.listLogs(
        limit: _limit,
        offset: _offset,
        status: _status,
      );
      if (!mounted) return;
      setState(() {
        _items = response.items;
        _total = response.total;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
    } finally {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }

  Color _statusColor(String status, BuildContext context) {
    switch (status.toLowerCase()) {
      case 'success':
        return Colors.green;
      case 'failed':
      case 'error':
        return Theme.of(context).colorScheme.error;
      default:
        return Theme.of(context).colorScheme.primary;
    }
  }

  void _applyFilters() {
    setState(() => _offset = 0);
    _load();
  }

  @override
  Widget build(BuildContext context) {
    return AppShell(
      title: 'บันทึกการทำงานระบบ',
      currentRoute: '/admin-logs',
      isAdmin: true,
      actions: [
        IconButton(
          onPressed: _load,
          icon: const Icon(Icons.refresh),
          tooltip: 'โหลดข้อมูลใหม่',
        ),
      ],
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: DropdownButtonFormField<String>(
              initialValue: _status,
              decoration: const InputDecoration(labelText: 'สถานะ'),
              items: const [
                DropdownMenuItem(value: 'all', child: Text('ทั้งหมด')),
                DropdownMenuItem(value: 'success', child: Text('สำเร็จ')),
                DropdownMenuItem(value: 'failed', child: Text('ไม่สำเร็จ')),
                DropdownMenuItem(value: 'error', child: Text('เกิดข้อผิดพลาด')),
              ],
              onChanged: (value) {
                if (value == null) return;
                setState(() => _status = value);
                _applyFilters();
              },
            ),
          ),
          if (_loading) const LinearProgressIndicator(),
          Expanded(
            child: _error != null
                ? ErrorStateView(message: _error!, onRetry: _load)
                : _items.isEmpty
                    ? const EmptyStateView(
                        title: 'ไม่พบบันทึกการทำงาน',
                        message: 'ยังไม่มีบันทึกที่ตรงกับสถานะที่เลือก',
                        icon: Icons.receipt_long_outlined,
                      )
                    : RefreshIndicator(
                        onRefresh: _load,
                        child: ListView.builder(
                          padding: const EdgeInsets.symmetric(horizontal: 16),
                          itemCount: _items.length + 1,
                          itemBuilder: (context, index) {
                            if (index == _items.length) {
                              return PaginationBar(
                                offset: _offset,
                                limit: _limit,
                                total: _total,
                                onPrevious: _offset <= 0
                                    ? null
                                    : () {
                                        setState(() => _offset =
                                            (_offset - _limit)
                                                .clamp(0, _offset));
                                        _load();
                                      },
                                onNext: _offset + _limit >= _total
                                    ? null
                                    : () {
                                        setState(() => _offset += _limit);
                                        _load();
                                      },
                              );
                            }
                            final item = _items[index];
                            return _SystemLogCard(
                              item: item,
                              statusColor: _statusColor(item.status, context),
                            );
                          },
                        ),
                      ),
          ),
        ],
      ),
    );
  }
}

class _SystemLogCard extends StatelessWidget {
  const _SystemLogCard({
    required this.item,
    required this.statusColor,
  });

  final SystemLogItem item;
  final Color statusColor;

  @override
  Widget build(BuildContext context) {
    final detail = item.detail.trim();
    final actor = systemLogActorLabel(item.userId, item.detail);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Text(
                    systemLogActionLabel(item.action),
                    style: Theme.of(context).textTheme.titleSmall,
                  ),
                ),
                const SizedBox(width: 12),
                Chip(
                  label: Text(systemLogStatusLabel(item.status)),
                  backgroundColor: statusColor.withValues(alpha: 0.12),
                  side: BorderSide(color: statusColor),
                ),
              ],
            ),
            const SizedBox(height: 2),
            SelectableText(
              item.action,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
            ),
            const SizedBox(height: 10),
            SelectableText(
              detail.isEmpty || detail == '-'
                  ? 'ไม่มีรายละเอียดเพิ่มเติม'
                  : detail,
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 18,
              runSpacing: 8,
              children: [
                _LogMetadata(
                  icon: Icons.schedule_outlined,
                  label: formatSystemLogTimestamp(item.timestamp),
                ),
                _LogMetadata(
                  icon: item.userId == null
                      ? Icons.settings_outlined
                      : Icons.person_outline,
                  label: actor,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _LogMetadata extends StatelessWidget {
  const _LogMetadata({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 16),
        const SizedBox(width: 6),
        Text(label),
      ],
    );
  }
}
