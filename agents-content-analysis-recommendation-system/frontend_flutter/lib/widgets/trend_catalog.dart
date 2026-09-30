import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../models/dashboard_overview.dart';

class TrendCatalog extends StatefulWidget {
  const TrendCatalog({
    super.key,
    required this.platform,
    required this.title,
    required this.subtitle,
    required this.trends,
    required this.emptyMessage,
    required this.isFollowing,
    required this.onToggleFollow,
    required this.onOpenDetails,
    required this.onOpenSource,
  });

  final String platform;
  final String title;
  final String subtitle;
  final List<DashboardTrendItem> trends;
  final String emptyMessage;
  final bool Function(DashboardTrendItem) isFollowing;
  final Future<void> Function(DashboardTrendItem) onToggleFollow;
  final Future<void> Function(DashboardTrendItem) onOpenDetails;
  final Future<void> Function(DashboardTrendItem) onOpenSource;

  @override
  State<TrendCatalog> createState() => _TrendCatalogState();
}

class _TrendCatalogState extends State<TrendCatalog> {
  static const _pageSize = 12;
  int _visibleCount = _pageSize;

  Widget _actions(DashboardTrendItem item) => Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          IconButton(
            tooltip: 'ดูรายละเอียด',
            onPressed: () => widget.onOpenDetails(item),
            icon: const Icon(Icons.info_outline, size: 20),
          ),
          IconButton(
            tooltip: switch (widget.platform) {
              'google' => 'เปิด Google Trends',
              'tiktok' => 'ดูบน TikTok',
              _ => 'ดูบน YouTube',
            },
            onPressed:
                item.videoUrl.isEmpty ? null : () => widget.onOpenSource(item),
            icon: const Icon(Icons.open_in_new, size: 20),
          ),
          IconButton(
            tooltip: widget.isFollowing(item) ? 'เลิกติดตาม' : 'ติดตามหัวข้อ',
            onPressed: () => widget.onToggleFollow(item),
            icon: Icon(
                widget.isFollowing(item)
                    ? Icons.bookmark
                    : Icons.bookmark_border,
                size: 20),
          ),
        ],
      );

  @override
  Widget build(BuildContext context) {
    final visible = widget.trends.take(_visibleCount).toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(widget.title, style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 4),
        Text(widget.subtitle, style: Theme.of(context).textTheme.bodySmall),
        const SizedBox(height: 16),
        if (visible.isEmpty)
          Padding(
              padding: const EdgeInsets.symmetric(vertical: 24),
              child: Text(widget.emptyMessage))
        else if (widget.platform == 'google')
          ...visible.map((item) => _SearchTrendRow(
                item: item,
                actions: _actions(item),
                onTap: () => widget.onOpenDetails(item),
              ))
        else
          LayoutBuilder(builder: (context, constraints) {
            final columns = constraints.maxWidth >= 1150
                ? 4
                : constraints.maxWidth >= 840
                    ? 3
                    : constraints.maxWidth >= 560
                        ? 2
                        : 1;
            final width = (constraints.maxWidth - (columns - 1) * 16) / columns;
            return Wrap(
              spacing: 16,
              runSpacing: 20,
              children: visible
                  .map((item) => SizedBox(
                        width: width,
                        child: _VideoTrendCard(
                          item: item,
                          actions: _actions(item),
                          onTap: () => widget.onOpenDetails(item),
                        ),
                      ))
                  .toList(),
            );
          }),
        if (visible.isNotEmpty) ...[
          const SizedBox(height: 20),
          Center(
              child: Text(
                  'แสดง ${visible.length} จาก ${widget.trends.length} รายการ',
                  style: Theme.of(context).textTheme.bodySmall)),
        ],
        if (_visibleCount < widget.trends.length) ...[
          const SizedBox(height: 8),
          Center(
              child: OutlinedButton.icon(
            key: const Key('trends-load-more'),
            onPressed: () => setState(() => _visibleCount =
                math.min(_visibleCount + _pageSize, widget.trends.length)),
            icon: const Icon(Icons.expand_more),
            label: const Text('ดูเพิ่มเติม'),
          )),
        ],
      ],
    );
  }
}

class _VideoTrendCard extends StatelessWidget {
  const _VideoTrendCard(
      {required this.item, required this.actions, required this.onTap});

  final DashboardTrendItem item;
  final Widget actions;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final duration = item.durationSeconds;
    return Card(
      margin: EdgeInsets.zero,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: BorderSide(color: Theme.of(context).colorScheme.outlineVariant),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          InkWell(
            onTap: onTap,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                AspectRatio(
                  aspectRatio: 16 / 9,
                  child: Stack(fit: StackFit.expand, children: [
                    if (item.thumbnailUrl.isNotEmpty)
                      Image.network(item.thumbnailUrl,
                          fit: BoxFit.cover,
                          errorBuilder: (_, __, ___) =>
                              const _ThumbnailFallback())
                    else
                      const _ThumbnailFallback(),
                    Positioned(
                        left: 8,
                        top: 8,
                        child: _MediaBadge(
                            text: item.rank > 0 ? '#${item.rank}' : '-')),
                    if (duration != null && duration > 0)
                      Positioned(
                          right: 8,
                          bottom: 8,
                          child: _MediaBadge(text: _duration(duration))),
                  ]),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 12, 12, 0),
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        SizedBox(
                            height:
                                MediaQuery.textScalerOf(context).scale(14) * 3,
                            child: Tooltip(
                                message: item.title,
                                child: Text(item.title,
                                    maxLines: 2,
                                    overflow: TextOverflow.ellipsis,
                                    style: Theme.of(context)
                                        .textTheme
                                        .titleSmall))),
                        const SizedBox(height: 8),
                        Text(
                            item.channelTitle.isEmpty
                                ? 'ไม่ระบุชื่อช่อง'
                                : item.channelTitle,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: Theme.of(context).textTheme.bodySmall),
                        const SizedBox(height: 4),
                        Text(
                            item.viewsAvailable
                                ? '${_number(item.views)} ครั้ง'
                                : 'ไม่ระบุยอดวิว',
                            style: Theme.of(context).textTheme.bodySmall),
                      ]),
                ),
              ],
            ),
          ),
          Padding(
              padding: const EdgeInsets.fromLTRB(8, 4, 8, 4),
              child: Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [actions])),
        ],
      ),
    );
  }
}

class _SearchTrendRow extends StatelessWidget {
  const _SearchTrendRow(
      {required this.item, required this.actions, required this.onTap});
  final DashboardTrendItem item;
  final Widget actions;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Column(children: [
        InkWell(
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 12),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              SizedBox(
                  width: 48,
                  child: Text('#${item.rank}',
                      style: Theme.of(context).textTheme.titleMedium)),
              Expanded(
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                    Text(item.title,
                        style: Theme.of(context).textTheme.titleMedium),
                    const SizedBox(height: 6),
                    Text(
                        item.searchVolume == null
                            ? 'ไม่ระบุปริมาณการค้นหา'
                            : 'ปริมาณการค้นหาโดยประมาณ ${_number(item.searchVolume!)}+ ครั้ง',
                        style: Theme.of(context).textTheme.bodySmall),
                    actions,
                  ])),
            ]),
          ),
        ),
        const Divider(height: 1),
      ]);
}

class _ThumbnailFallback extends StatelessWidget {
  const _ThumbnailFallback();
  @override
  Widget build(BuildContext context) => ColoredBox(
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      child: const Center(child: Icon(Icons.video_library_outlined, size: 36)));
}

class _MediaBadge extends StatelessWidget {
  const _MediaBadge({required this.text});
  final String text;
  @override
  Widget build(BuildContext context) => DecoratedBox(
      decoration: BoxDecoration(
          color: Colors.black87, borderRadius: BorderRadius.circular(4)),
      child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
          child: Text(text,
              style: const TextStyle(color: Colors.white, fontSize: 12))));
}

String _number(int value) => value.toString().replaceAllMapped(
    RegExp(r'(\d)(?=(\d{3})+(?!\d))'), (match) => '${match[1]},');

String _duration(int seconds) {
  final minutes = seconds ~/ 60;
  final remainder = (seconds % 60).toString().padLeft(2, '0');
  if (minutes < 60) return '$minutes:$remainder';
  return '${minutes ~/ 60}:${(minutes % 60).toString().padLeft(2, '0')}:$remainder';
}
