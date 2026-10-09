import 'package:flutter/material.dart';

import '../models/content_history.dart';
import '../models/outcome_prediction.dart';
import '../repositories/content_repository.dart';
import '../state/auth_scope.dart';
import '../widgets/app_shell.dart';
import '../widgets/state_widgets.dart';
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
      child: _error != null
          ? ErrorStateView(message: _error!, onRetry: _load)
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.only(bottom: 24),
                children: [
                  // Category filter
                  if (hasItems) ...[
                    Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text(
                                'ผลวิเคราะห์ ${filtered.length} จาก ${_items.length} รายการ',
                                style: Theme.of(context).textTheme.labelMedium,
                              ),
                              if (_loading)
                                const SizedBox(
                                  width: 16,
                                  height: 16,
                                  child:
                                      CircularProgressIndicator(strokeWidth: 2),
                                ),
                            ],
                          ),
                          const SizedBox(height: 12),
                          Wrap(
                            spacing: 12,
                            runSpacing: 12,
                            children: [
                              if (_domains.isNotEmpty)
                                SizedBox(
                                  width: 220,
                                  child: DropdownButtonFormField<String>(
                                    initialValue: _filterDomain,
                                    decoration: const InputDecoration(
                                        labelText: 'หมวดหมู่'),
                                    items: [
                                      const DropdownMenuItem(
                                          value: 'all',
                                          child: Text('ทุกหมวดหมู่')),
                                      ..._domains
                                          .map((domain) => DropdownMenuItem(
                                                value: domain,
                                                child: Text(domain),
                                              )),
                                    ],
                                    onChanged: (value) {
                                      if (value != null) {
                                        setState(() => _filterDomain = value);
                                      }
                                    },
                                  ),
                                ),
                            ],
                          ),
                        ],
                      ),
                    ),
                    const Divider(height: 1),
                  ],

                  // Items list
                  if (filtered.isEmpty)
                    const Padding(
                      padding: EdgeInsets.all(32),
                      child: EmptyStateView(
                        title: 'ไม่พบผลวิเคราะห์',
                        message: 'ลองเปลี่ยนหมวดหมู่',
                        icon: Icons.filter_list_off,
                      ),
                    )
                  else
                    Padding(
                      padding: const EdgeInsets.symmetric(
                          vertical: 8, horizontal: 8),
                      child: ListView.builder(
                        shrinkWrap: true,
                        physics: const NeverScrollableScrollPhysics(),
                        itemCount: filtered.length,
                        itemBuilder: (context, index) {
                          final item = filtered[index];
                          final keywords = item.recommendedKeywords;
                          final keywordPreview = keywords.isEmpty
                              ? '-'
                              : keywords.take(3).join(', ') +
                                  (keywords.length > 3
                                      ? ' +${keywords.length - 3}'
                                      : '');

                          return Card(
                            margin: const EdgeInsets.symmetric(vertical: 4),
                            child: ListTile(
                              contentPadding: const EdgeInsets.symmetric(
                                  horizontal: 16, vertical: 12),
                              leading: CircleAvatar(
                                backgroundColor: Theme.of(context)
                                    .colorScheme
                                    .primaryContainer,
                                child: Icon(Icons.video_camera_back,
                                    color: Theme.of(context)
                                        .colorScheme
                                        .onPrimaryContainer),
                              ),
                              title: Text(
                                item.title,
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: Theme.of(context).textTheme.titleSmall,
                              ),
                              subtitle: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  const SizedBox(height: 4),
                                  Row(
                                    children: [
                                      Chip(
                                        label: Text(_domainLabel(item.domain)),
                                        side: const BorderSide(
                                            color: Color(0xFFE0E0E0)),
                                        backgroundColor: Colors.transparent,
                                        visualDensity: VisualDensity.compact,
                                      ),
                                      const SizedBox(width: 8),
                                      Chip(
                                        label: Text(_durationLabel(
                                            item.recommendedDuration)),
                                        side: const BorderSide(
                                            color: Color(0xFFE0E0E0)),
                                        backgroundColor: Colors.transparent,
                                        visualDensity: VisualDensity.compact,
                                      ),
                                    ],
                                  ),
                                  const SizedBox(height: 6),
                                  Text(
                                    'คำแนะนำ: $keywordPreview',
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style:
                                        Theme.of(context).textTheme.bodySmall,
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    outcomeStatusMessage(
                                        item.outcomeAssessmentStatus),
                                    maxLines: 2,
                                    overflow: TextOverflow.ellipsis,
                                    style:
                                        Theme.of(context).textTheme.bodySmall,
                                  ),
                                  if (item.transcriptPreview.isNotEmpty) ...[
                                    const SizedBox(height: 4),
                                    Text(
                                      item.transcriptPreview,
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                      style: Theme.of(context)
                                          .textTheme
                                          .bodySmall
                                          ?.copyWith(
                                            color: Colors.grey,
                                          ),
                                    ),
                                  ],
                                ],
                              ),
                              onTap: () => Navigator.pushNamed(
                                context,
                                '/result',
                                arguments:
                                    ResultScreenArgs(contentId: item.contentId),
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                  if (hasItems) ...[
                    const Divider(),
                    const UsageStatisticsPanel(),
                  ],
                ],
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
  return seconds == null ? value : '$seconds วินาที';
}
