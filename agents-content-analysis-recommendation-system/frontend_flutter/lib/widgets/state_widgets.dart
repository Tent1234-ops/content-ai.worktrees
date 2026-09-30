import 'package:flutter/material.dart';

import '../models/common_models.dart';

class ErrorStateView extends StatelessWidget {
  const ErrorStateView({
    super.key,
    required this.message,
    this.onRetry,
  });

  final String message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline,
                size: 42, color: Theme.of(context).colorScheme.error),
            const SizedBox(height: 12),
            Text(
              message,
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            if (onRetry != null) ...[
              const SizedBox(height: 16),
              FilledButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh),
                label: const Text('Try again'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class EmptyStateView extends StatelessWidget {
  const EmptyStateView({
    super.key,
    required this.title,
    required this.message,
    this.icon = Icons.inbox_outlined,
  });

  final String title;
  final String message;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 42, color: Theme.of(context).colorScheme.primary),
            const SizedBox(height: 12),
            Text(title, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Text(message, textAlign: TextAlign.center),
          ],
        ),
      ),
    );
  }
}

class PaginationBar extends StatelessWidget {
  const PaginationBar({
    super.key,
    required this.offset,
    required this.limit,
    required this.total,
    required this.onPrevious,
    required this.onNext,
  });

  final int offset;
  final int limit;
  final int total;
  final VoidCallback? onPrevious;
  final VoidCallback? onNext;

  @override
  Widget build(BuildContext context) {
    final start = total == 0 ? 0 : offset + 1;
    final end =
        total == 0 ? 0 : (offset + limit > total ? total : offset + limit);
    return Row(
      children: [
        Text('Showing $start-$end of $total'),
        const Spacer(),
        IconButton(
          onPressed: onPrevious,
          icon: const Icon(Icons.chevron_left),
          tooltip: 'Previous page',
        ),
        IconButton(
          onPressed: onNext,
          icon: const Icon(Icons.chevron_right),
          tooltip: 'Next page',
        ),
      ],
    );
  }
}

class SimpleBarChart extends StatelessWidget {
  const SimpleBarChart({
    super.key,
    required this.items,
    this.maxItems = 6,
  });

  final List<ChartItem> items;
  final int maxItems;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) {
      return const EmptyStateView(
        title: 'No chart data',
        message: 'This section will populate when more records are available.',
        icon: Icons.bar_chart_outlined,
      );
    }
    final visible = items.take(maxItems).toList();
    final maxValue = visible
        .map((item) => item.count.toDouble())
        .fold<double>(0, (current, value) => value > current ? value : current);
    return Column(
      children: visible.map((row) {
        final label = row.label;
        final value = row.count.toDouble();
        final factor = maxValue <= 0 ? 0.0 : value / maxValue;
        return Padding(
          padding: const EdgeInsets.symmetric(vertical: 6),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(child: Text(label, overflow: TextOverflow.ellipsis)),
                  const SizedBox(width: 12),
                  Text(value.toStringAsFixed(
                      value.truncateToDouble() == value ? 0 : 1)),
                ],
              ),
              const SizedBox(height: 6),
              LinearProgressIndicator(value: factor, minHeight: 10),
            ],
          ),
        );
      }).toList(),
    );
  }
}
