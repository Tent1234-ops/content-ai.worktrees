import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/dashboard_overview.dart';

Future<void> showTrendDetailPanel({
  required BuildContext context,
  required DashboardTrendItem item,
}) {
  return showGeneralDialog<void>(
    context: context,
    barrierDismissible: true,
    barrierLabel: 'ปิดรายละเอียดเทรนด์',
    barrierColor: Colors.black54,
    transitionDuration: const Duration(milliseconds: 220),
    pageBuilder: (context, animation, secondaryAnimation) {
      final size = MediaQuery.sizeOf(context);
      final panelWidth =
          size.width < 720 ? size.width : math.min(640.0, size.width * 0.55);
      return Align(
        alignment: Alignment.centerRight,
        child: SizedBox(
          width: panelWidth,
          height: size.height,
          child: Material(
            color: Theme.of(context).colorScheme.surface,
            elevation: 16,
            child: _TrendDetailPanel(item: item),
          ),
        ),
      );
    },
    transitionBuilder: (context, animation, secondaryAnimation, child) {
      final curved = CurvedAnimation(
        parent: animation,
        curve: Curves.easeOutCubic,
        reverseCurve: Curves.easeInCubic,
      );
      return SlideTransition(
        position: Tween<Offset>(
          begin: const Offset(1, 0),
          end: Offset.zero,
        ).animate(curved),
        child: child,
      );
    },
  );
}

class _TrendDetailPanel extends StatelessWidget {
  const _TrendDetailPanel({required this.item});

  final DashboardTrendItem item;

  Future<void> _openSource(BuildContext context) async {
    final uri = Uri.tryParse(item.videoUrl);
    if (uri == null || !uri.hasScheme) return;
    final opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!opened && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('ไม่สามารถเปิดลิงก์ต้นทางได้')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final thumbnail = item.thumbnailUrl.isNotEmpty
        ? item.thumbnailUrl
        : _youtubeThumbnailFromUrl(item.videoUrl);
    final canOpenSource = Uri.tryParse(item.videoUrl)?.hasScheme == true;
    final hasMetadata = item.category.isNotEmpty ||
        item.publishedAt.isNotEmpty ||
        item.durationSeconds != null;
    final hasMetrics =
        item.viewsAvailable || item.likesAvailable || item.commentsAvailable;

    return SafeArea(
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 12, 8, 12),
            child: Row(
              children: [
                const Icon(Icons.insights_outlined),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'รายละเอียดเทรนด์',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                IconButton(
                  onPressed: () => Navigator.of(context).pop(),
                  icon: const Icon(Icons.close),
                  tooltip: 'ปิด',
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (thumbnail.isNotEmpty) ...[
                    _TrendThumbnail(url: thumbnail),
                    const SizedBox(height: 18),
                  ],
                  Text(
                    item.title,
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  if (item.channelTitle.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        const Icon(Icons.account_circle_outlined, size: 18),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            item.channelTitle,
                            style: Theme.of(context).textTheme.bodyMedium,
                          ),
                        ),
                      ],
                    ),
                  ],
                  const SizedBox(height: 18),
                  _RankSummary(item: item),
                  if (item.platform.toLowerCase() == 'google' &&
                      item.searchVolume != null) ...[
                    const SizedBox(height: 18),
                    _GoogleSearchEvidence(item: item),
                  ],
                  if (hasMetadata) ...[
                    const SizedBox(height: 18),
                    _MetadataRows(item: item),
                  ],
                  if (hasMetrics) ...[
                    const SizedBox(height: 22),
                    Text(
                      'สถิติปัจจุบันจาก ${_platformName(item.platform)}',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 12),
                    _MetricsGrid(item: item),
                  ],
                  if (item.description.isNotEmpty) ...[
                    const SizedBox(height: 24),
                    Text(
                      'คำอธิบายจากช่อง',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 8),
                    SelectableText(
                      item.description,
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                  ],
                ],
              ),
            ),
          ),
          const Divider(height: 1),
          Padding(
            padding: const EdgeInsets.all(16),
            child: SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: canOpenSource ? () => _openSource(context) : null,
                icon: const Icon(Icons.open_in_new),
                label: Text(_sourceButtonLabel(item.platform)),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _GoogleSearchEvidence extends StatelessWidget {
  const _GoogleSearchEvidence({required this.item});

  final DashboardTrendItem item;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        border: Border.all(color: Theme.of(context).dividerColor),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.search, size: 19),
              const SizedBox(width: 8),
              Text(
                'จำนวนการค้นหาโดยประมาณ',
                style: Theme.of(context).textTheme.titleSmall,
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            'ประมาณ ${_formatInteger(item.searchVolume!)} ครั้ง',
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          const SizedBox(height: 8),
          Text(
            'เป็นจำนวนครั้งที่มีการค้นหา ไม่ใช่จำนวนผู้ใช้แบบไม่ซ้ำ',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          if (item.rank > 0) ...[
            const SizedBox(height: 4),
            Text(
              'อันดับ #${item.rank} คือลำดับ Trending Now ที่ Google ส่งมาในรอบล่าสุด โดยจำนวนค้นหาเป็นหลักฐานประกอบและไม่ใช่สูตรจัดอันดับเพียงค่าเดียว',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ],
      ),
    );
  }
}

class _TrendThumbnail extends StatelessWidget {
  const _TrendThumbnail({required this.url});

  final String url;

  @override
  Widget build(BuildContext context) {
    return AspectRatio(
      aspectRatio: 16 / 9,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(6),
        child: Image.network(
          url,
          fit: BoxFit.cover,
          errorBuilder: (context, error, stackTrace) => ColoredBox(
            color: Theme.of(context).colorScheme.surfaceContainerHighest,
            child: const Center(
              child: Icon(Icons.video_library_outlined, size: 42),
            ),
          ),
        ),
      ),
    );
  }
}

class _RankSummary extends StatelessWidget {
  const _RankSummary({required this.item});

  final DashboardTrendItem item;

  @override
  Widget build(BuildContext context) {
    final movement = _rankMovementText(item);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 150,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _rankScopeLabel(item),
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                const SizedBox(height: 4),
                Text(
                  item.rank > 0 ? '#${item.rank}' : '-',
                  style: Theme.of(context).textTheme.headlineMedium,
                ),
              ],
            ),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'การเปลี่ยนแปลงจากรอบก่อน',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                const SizedBox(height: 6),
                Text(
                  movement,
                  style: Theme.of(context).textTheme.titleSmall,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _MetadataRows extends StatelessWidget {
  const _MetadataRows({required this.item});

  final DashboardTrendItem item;

  @override
  Widget build(BuildContext context) {
    final rows = <({IconData icon, String label, String value})>[];
    if (item.category.isNotEmpty) {
      rows.add((
        icon: Icons.category_outlined,
        label: 'หมวดหมู่',
        value: _categoryName(item.category),
      ));
    }
    if (item.publishedAt.isNotEmpty) {
      rows.add((
        icon: Icons.calendar_today_outlined,
        label: 'เผยแพร่',
        value: _formatDateTime(item.publishedAt),
      ));
    }
    if (item.durationSeconds != null && item.durationSeconds! > 0) {
      rows.add((
        icon: Icons.schedule_outlined,
        label: 'ความยาว',
        value: _formatDuration(item.durationSeconds!),
      ));
    }

    return Column(
      children: rows
          .map(
            (row) => Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: Row(
                children: [
                  Icon(row.icon, size: 18),
                  const SizedBox(width: 10),
                  SizedBox(
                    width: 82,
                    child: Text(
                      row.label,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ),
                  Expanded(child: Text(row.value)),
                ],
              ),
            ),
          )
          .toList(),
    );
  }
}

class _MetricsGrid extends StatelessWidget {
  const _MetricsGrid({required this.item});

  final DashboardTrendItem item;

  @override
  Widget build(BuildContext context) {
    final metrics = <({String label, int value, IconData icon})>[];
    if (item.viewsAvailable) {
      metrics.add((
        label: 'ยอดวิว',
        value: item.views,
        icon: Icons.visibility_outlined,
      ));
    }
    if (item.likesAvailable) {
      metrics.add((
        label: 'ยอดไลก์',
        value: item.likes,
        icon: Icons.thumb_up_outlined,
      ));
    }
    if (item.commentsAvailable) {
      metrics.add((
        label: 'ความคิดเห็น',
        value: item.comments,
        icon: Icons.mode_comment_outlined,
      ));
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        final columns = math.min(
          metrics.length,
          constraints.maxWidth < 430 ? 2 : 3,
        );
        return GridView.builder(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: metrics.length,
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: math.max(1, columns),
            mainAxisExtent: 94,
            crossAxisSpacing: 8,
            mainAxisSpacing: 8,
          ),
          itemBuilder: (context, index) {
            final metric = metrics[index];
            return Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                border: Border.all(color: Theme.of(context).dividerColor),
                borderRadius: BorderRadius.circular(6),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Row(
                    children: [
                      Icon(metric.icon, size: 17),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(
                          metric.label,
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text(
                    _formatInteger(metric.value),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }
}

String _rankMovementText(DashboardTrendItem item) {
  if (item.changeKind == 'new') {
    return 'เพิ่งเข้ามาในอันดับรอบล่าสุด';
  }
  if (!item.hasPreviousSnapshot || item.rank <= 0) {
    return 'ยังไม่มีรอบก่อนสำหรับเปรียบเทียบ';
  }
  final previousRank = item.rank + item.rankChange;
  if (item.rankChange > 0) {
    return 'ขยับขึ้น ${item.rankChange} อันดับ จาก #$previousRank เป็น #${item.rank}';
  }
  if (item.rankChange < 0) {
    return 'ลดลง ${item.rankChange.abs()} อันดับ จาก #$previousRank เป็น #${item.rank}';
  }
  return 'อันดับคงเดิม';
}

String _rankScopeLabel(DashboardTrendItem item) {
  if (item.rankingScope != 'global') {
    final category = _categoryName(item.category).trim();
    return category.isEmpty
        ? 'อันดับภายในหมวดเดียวกัน'
        : 'อันดับในหมวด$category';
  }
  if (item.platform.toLowerCase() == 'google') {
    return 'อันดับคำค้นบน Google';
  }
  return 'อันดับรวมบน ${_platformName(item.platform)}';
}

String _sourceButtonLabel(String platform) {
  switch (platform.toLowerCase()) {
    case 'youtube':
      return 'ดูบน YouTube';
    case 'google':
      return 'เปิดบน Google Trends';
    case 'tiktok':
      return 'ดูบน TikTok';
    default:
      return 'เปิดลิงก์ต้นทาง';
  }
}

String _platformName(String platform) {
  switch (platform.toLowerCase()) {
    case 'youtube':
      return 'YouTube';
    case 'google':
      return 'Google';
    case 'tiktok':
      return 'TikTok';
    default:
      return platform;
  }
}

String _categoryName(String category) {
  return switch (category.toLowerCase()) {
    'music' => 'เพลงและดนตรี',
    'gaming' => 'เกม',
    'entertainment' => 'บันเทิง',
    'people & blogs' => 'บุคคลและบล็อก',
    'film & animation' => 'ภาพยนตร์และแอนิเมชัน',
    'autos & vehicles' => 'รถยนต์และยานพาหนะ',
    'pets & animals' => 'สัตว์เลี้ยงและสัตว์',
    'sports' => 'กีฬา',
    'news & politics' => 'ข่าวและการเมือง',
    'science & technology' => 'วิทยาศาสตร์และเทคโนโลยี',
    'education' => 'การศึกษา',
    _ => category,
  };
}

String _youtubeThumbnailFromUrl(String value) {
  final uri = Uri.tryParse(value);
  if (uri == null) return '';
  String? videoId;
  if (uri.host.contains('youtu.be') && uri.pathSegments.isNotEmpty) {
    videoId = uri.pathSegments.first;
  } else if (uri.host.contains('youtube.com')) {
    videoId = uri.queryParameters['v'];
    if ((videoId == null || videoId.isEmpty) &&
        uri.pathSegments.length >= 2 &&
        {'shorts', 'embed'}.contains(uri.pathSegments.first)) {
      videoId = uri.pathSegments[1];
    }
  }
  if (videoId == null || videoId.isEmpty) return '';
  return 'https://i.ytimg.com/vi/$videoId/hqdefault.jpg';
}

String _formatInteger(int value) {
  final digits = value.abs().toString();
  final parts = <String>[];
  for (var end = digits.length; end > 0; end -= 3) {
    final start = math.max(0, end - 3);
    parts.add(digits.substring(start, end));
  }
  final formatted = parts.reversed.join(',');
  return value < 0 ? '-$formatted' : formatted;
}

String _formatDuration(int seconds) {
  final duration = Duration(seconds: seconds);
  final hours = duration.inHours;
  final minutes = duration.inMinutes.remainder(60).toString().padLeft(2, '0');
  final remainingSeconds =
      duration.inSeconds.remainder(60).toString().padLeft(2, '0');
  return hours > 0
      ? '$hours:$minutes:$remainingSeconds'
      : '${duration.inMinutes}:$remainingSeconds';
}

String _formatDateTime(String value) {
  final trimmed = value.trim();
  final hasTimezone = RegExp(
    r'(z|[+-]\d{2}:?\d{2})$',
    caseSensitive: false,
  ).hasMatch(trimmed);
  final parsed = DateTime.tryParse(hasTimezone ? trimmed : '${trimmed}Z');
  if (parsed == null) return value;
  final local = parsed.toLocal();
  final day = local.day.toString().padLeft(2, '0');
  final month = local.month.toString().padLeft(2, '0');
  final year = local.year;
  final hour = local.hour.toString().padLeft(2, '0');
  final minute = local.minute.toString().padLeft(2, '0');
  return '$day/$month/$year $hour:$minute';
}
