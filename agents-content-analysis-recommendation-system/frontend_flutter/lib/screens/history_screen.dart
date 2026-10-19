import 'package:flutter/material.dart';

import '../models/content_history.dart';
import '../models/outcome_prediction.dart';
import '../repositories/content_repository.dart';
import '../state/auth_scope.dart';
import '../widgets/app_shell.dart';
import '../widgets/state_widgets.dart';
import '../widgets/workspace_widgets.dart';
import '../widgets/usage_statistics_panel.dart';
import 'result_screen.dart';

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key, this.repository});

  final ContentRepository? repository;

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  late final ContentRepository _repository;
  List<ContentHistoryItem> _items = [];
  String? _error;
  bool _loading = false;
  String _filterDomain = 'all';
  final List<String> _domains = [];

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? ContentRepository();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final response = await _repository.listMyContents(limit: 50);
      if (!mounted) return;

      // Extract unique domains
      final uniqueDomains = <String>{};
      for (var item in response.items) {
        uniqueDomains.add(item.domain);
      }

      setState(() {
        _items = response.items;
        _domains.clear();
        _domains.addAll(uniqueDomains);
        _domains.sort();
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

  List<ContentHistoryItem> _getFilteredAndSorted() {
    var filtered = List<ContentHistoryItem>.of(_items);

    // Apply domain filter
    if (_filterDomain != 'all') {
      filtered =
          filtered.where((item) => item.domain == _filterDomain).toList();
    }

    // The API orders by created_at descending; filtering preserves that order.
    return filtered;
  }

  @override
  Widget build(BuildContext context) {
    final auth = AuthScope.of(context);
    final filtered = _getFilteredAndSorted();
    final hasItems = _items.isNotEmpty;
    return AppShell(
      title: 'ไอเดียและประวัติ',
      currentRoute: '/history',
      isAdmin: auth.isAdmin,
      actions: [
        IconButton(
            onPressed: _loading ? null : _load,
            tooltip: 'โหลดประวัติล่าสุด',
            icon: const Icon(Icons.refresh)),
      ],
      child: _error != null
          ? ErrorStateView(message: _error!, onRetry: _load)
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.all(24),
                children: [
                  PageHeader(
                    title: 'ไอเดียและประวัติ',
                    subtitle: _loading && !hasItems
                        ? null
                        : 'ผลวิเคราะห์ ${filtered.length} จาก ${_items.length} รายการ',
                    action: FilledButton.icon(
                      onPressed: () => Navigator.pushNamed(context, '/upload'),
                      icon: const Icon(Icons.add),
                      label: const Text('วิเคราะห์คลิปใหม่'),
                    ),
                  ),
                  if (_loading) const LinearProgressIndicator(),
                  if (hasItems) ...[
                    Align(
                      alignment: Alignment.centerLeft,
                      child: SizedBox(
                        width: 300,
                        child: DropdownButtonFormField<String>(
                          initialValue: _filterDomain,
                          isExpanded: true,
                          decoration: const InputDecoration(
                              labelText: 'หมวดหมู่',
                              prefixIcon: Icon(Icons.filter_list)),
                          items: [
                            const DropdownMenuItem(
                                value: 'all', child: Text('ทุกหมวดหมู่')),
                            ..._domains.map((domain) => DropdownMenuItem(
                                value: domain,
                                child: Text(domain,
                                    overflow: TextOverflow.ellipsis))),
                          ],
                          onChanged: (value) {
                            if (value != null) {
                              setState(() => _filterDomain = value);
                            }
                          },
                        ),
                      ),
                    ),
                    const SizedBox(height: 24),
                  ],
                  if (!_loading && filtered.isEmpty)
                    EmptyStateView(
                      title: 'ไม่พบผลวิเคราะห์',
                      message: hasItems
                          ? 'ลองเปลี่ยนหมวดหมู่'
                          : 'ยังไม่มีคลิปที่วิเคราะห์และบันทึกไว้',
                      icon: hasItems
                          ? Icons.filter_list_off
                          : Icons.video_library_outlined,
                    ),
                  if (filtered.isNotEmpty)
                    LayoutBuilder(builder: (context, constraints) {
                      final columns = constraints.maxWidth >= 900 ? 2 : 1;
                      final width =
                          (constraints.maxWidth - (columns - 1) * 16) / columns;
                      return Wrap(spacing: 16, runSpacing: 16, children: [
                        for (final item in filtered)
                          SizedBox(
                              width: width,
                              child: _HistoryCard(
                                key: ValueKey('history-${item.contentId}'),
                                item: item,
                                onOpen: () => Navigator.pushNamed(
                                    context, '/result',
                                    arguments: ResultScreenArgs(
                                        contentId: item.contentId)),
                              )),
                      ]);
                    }),
                  if (hasItems) ...[
                    const SizedBox(height: 32),
                    const Divider(),
                    const UsageStatisticsPanel(),
                  ],
                ],
              ),
            ),
    );
  }
}

class _HistoryCard extends StatelessWidget {
  const _HistoryCard({super.key, required this.item, required this.onOpen});
  final ContentHistoryItem item;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final keywords = item.recommendedKeywords;
    final keywordPreview = keywords.isEmpty
        ? '-'
        : keywords.take(3).join(', ') +
            (keywords.length > 3 ? ' +${keywords.length - 3}' : '');
    final date = item.createdAt?.toLocal();
    final stamp = date == null
        ? 'ไม่พบวันที่บันทึก'
        : '${date.day}/${date.month}/${date.year} · ${date.hour.toString().padLeft(2, '0')}:${date.minute.toString().padLeft(2, '0')}';
    return Card(
      margin: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onOpen,
        hoverColor: theme.colorScheme.primary.withValues(alpha: 0.05),
        focusColor: theme.colorScheme.primary.withValues(alpha: 0.10),
        child: Padding(
          padding: const EdgeInsets.all(20),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Icon(Icons.video_file_outlined,
                  size: 28, color: theme.colorScheme.primary),
              const SizedBox(width: 12),
              Expanded(
                  child: Text(item.title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.titleMedium)),
              const SizedBox(width: 8),
              const Icon(Icons.arrow_forward, size: 20),
            ]),
            const SizedBox(height: 16),
            Wrap(spacing: 8, runSpacing: 8, children: [
              StatusBadge(
                  label: _domainLabel(item.domain),
                  icon: Icons.category_outlined),
              StatusBadge(
                  label:
                      'ความยาวแนะนำ: ${_durationLabel(item.recommendedDuration)}',
                  icon: Icons.timer_outlined,
                  color: theme.colorScheme.onSurfaceVariant),
            ]),
            const SizedBox(height: 16),
            Text('คำแนะนำ: $keywordPreview',
                maxLines: 2, overflow: TextOverflow.ellipsis),
            const SizedBox(height: 8),
            Text(outcomeStatusMessage(item.outcomeAssessmentStatus),
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodySmall),
            if (item.transcriptPreview.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text(item.transcriptPreview,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.bodySmall),
            ],
            const Divider(height: 28),
            Text(stamp, style: theme.textTheme.bodySmall),
          ]),
        ),
      ),
    );
  }
}

String _domainLabel(String value) => switch (value.toLowerCase()) {
      'phone' => 'มือถือ',
      'camera' => 'กล้อง',
      'laptop' => 'แล็ปท็อป',
      'unknown' => 'ไม่ทราบหมวดหมู่',
      _ => value,
    };

String _durationLabel(String value) {
  final seconds = int.tryParse(value.trim());
  return seconds == null || seconds <= 0 ? 'ไม่มีข้อมูล' : '$seconds วินาที';
}
