import 'package:flutter/material.dart';

import '../models/content_history.dart';
import '../repositories/content_repository.dart';
import '../state/auth_scope.dart';
import '../widgets/app_shell.dart';
import '../widgets/state_widgets.dart';
import '../widgets/usage_statistics_panel.dart';
import 'result_screen.dart';

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  final _repository = ContentRepository();
  List<ContentHistoryItem> _items = [];
  String? _error;
  bool _loading = false;
  String _sortBy = 'recent'; // recent, domain, duration
  String _filterDomain = 'all';
  final List<String> _domains = [];

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
    var filtered = _items;

    // Apply domain filter
    if (_filterDomain != 'all') {
      filtered =
          filtered.where((item) => item.domain == _filterDomain).toList();
    }

    // Apply sorting
    switch (_sortBy) {
      case 'domain':
        filtered.sort((a, b) => a.domain.compareTo(b.domain));
        break;
      case 'duration':
        filtered.sort(
            (a, b) => a.recommendedDuration.compareTo(b.recommendedDuration));
        break;
      case 'recent':
      default:
        // Already sorted by recent
        break;
    }

    return filtered;
  }

  @override
  Widget build(BuildContext context) {
    final auth = AuthScope.of(context);
    final filtered = _getFilteredAndSorted();
    final hasItems = _items.isNotEmpty;

    return AppShell(
      title: 'My Ideas & History',
      currentRoute: '/history',
      isAdmin: auth.isAdmin,
      child: _error != null
          ? ErrorStateView(message: _error!, onRetry: _load)
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                children: [
                  const UsageStatisticsPanel(),
                  const Divider(),
                  // Filters & Sort
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
                                'Showing ${filtered.length} of ${_items.length}',
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
                          // Sort dropdown
                          DropdownButton<String>(
                            value: _sortBy,
                            items: const [
                              DropdownMenuItem(
                                  value: 'recent', child: Text('Sort: Recent')),
                              DropdownMenuItem(
                                  value: 'domain', child: Text('Sort: Domain')),
                              DropdownMenuItem(
                                  value: 'duration',
                                  child: Text('Sort: Duration')),
                            ],
                            onChanged: (value) {
                              if (value != null) {
                                setState(() => _sortBy = value);
                              }
                            },
                          ),
                          const SizedBox(height: 8),
                          // Domain filter
                          if (_domains.isNotEmpty)
                            DropdownButton<String>(
                              value: _filterDomain,
                              items: [
                                const DropdownMenuItem(
                                    value: 'all', child: Text('All Domains')),
                                ..._domains.map((domain) => DropdownMenuItem(
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
                        title: 'No results',
                        message: 'Try adjusting your filters or sort order.',
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
                                        label: Text(item.domain),
                                        side: const BorderSide(
                                            color: Color(0xFFE0E0E0)),
                                        backgroundColor: Colors.transparent,
                                        visualDensity: VisualDensity.compact,
                                      ),
                                      const SizedBox(width: 8),
                                      Chip(
                                        label: Text(item.recommendedDuration),
                                        side: const BorderSide(
                                            color: Color(0xFFE0E0E0)),
                                        backgroundColor: Colors.transparent,
                                        visualDensity: VisualDensity.compact,
                                      ),
                                    ],
                                  ),
                                  const SizedBox(height: 6),
                                  Text(
                                    'Keywords: $keywordPreview',
                                    maxLines: 1,
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
                ],
              ),
            ),
    );
  }
}
