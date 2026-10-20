import 'package:flutter/material.dart';

import '../models/performance_overview.dart';
import '../models/performance_clustering.dart';
import '../models/reference_response.dart';
import '../repositories/content_repository.dart';
import 'performance_clustering_panel.dart';
import 'workspace_widgets.dart';

/// Automatically compares every saved topic/context cohort without asking the
/// user to choose keywords. The dropdown is only for inspecting evidence.
class AutomaticPerformanceClusteringPanel extends StatefulWidget {
  const AutomaticPerformanceClusteringPanel({
    super.key,
    required this.contentId,
    required this.repository,
    required this.topics,
  });

  final int contentId;
  final ContentRepository repository;
  final List<ReferenceResponseTopic> topics;

  @override
  State<AutomaticPerformanceClusteringPanel> createState() =>
      _AutomaticPerformanceClusteringPanelState();
}

class _AutomaticPerformanceClusteringPanelState
    extends State<AutomaticPerformanceClusteringPanel> {
  PerformanceOverview? _overview;
  bool _loading = true;
  bool _showDetails = false;
  String? _error;
  int _request = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(covariant AutomaticPerformanceClusteringPanel old) {
    super.didUpdateWidget(old);
    if (old.contentId != widget.contentId ||
        old.repository != widget.repository) {
      _showDetails = false;
      _load();
    }
  }

  @override
  void dispose() {
    _request++;
    super.dispose();
  }

  Future<void> _load() async {
    final request = ++_request;
    setState(() {
      _loading = true;
      _error = null;
      _overview = null;
    });
    try {
      final overview =
          await widget.repository.getAutomaticPerformanceOverview(widget.contentId);
      if (!mounted || request != _request) return;
      setState(() => _overview = overview);
    } catch (_) {
      if (mounted && request == _request) {
        setState(() => _error = 'โหลดผลวิเคราะห์ทุกหัวข้ออัตโนมัติไม่สำเร็จ');
      }
    } finally {
      if (mounted && request == _request) {
        setState(() => _loading = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('กำลังวิเคราะห์ Low/High ของทุกหัวข้ออ้างอิง...'),
            SizedBox(height: 12),
            LinearProgressIndicator(),
          ],
        ),
      );
    }
    if (_error != null) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(_error!),
          TextButton.icon(
            key: const ValueKey('automatic-performance-retry'),
            onPressed: _load,
            icon: const Icon(Icons.refresh),
            label: const Text('ลองอีกครั้ง'),
          ),
        ],
      );
    }
    final overview = _overview;
    if (overview == null) return const SizedBox.shrink();
    final theme = Theme.of(context);
    return Column(
      key: const ValueKey('automatic-performance-overview'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SectionHeading(
          title: 'วิเคราะห์กลุ่มผลงานอัตโนมัติ',
          icon: Icons.scatter_plot_outlined,
        ),
        Text(
          'เปรียบเทียบ Transcript ของคุณกับ Low/High ในทุกหัวข้อที่มีหลักฐานบันทึกไว้ โดยไม่ต้องเลือกคำ',
          style: theme.textTheme.bodyMedium,
        ),
        const SizedBox(height: 12),
        if (overview.groups.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 12),
            child: Text('ยังไม่มีชุดหลักฐานอ้างอิงรายหัวข้อที่ใช้จัดกลุ่มอัตโนมัติได้'),
          )
        else ...[
          Wrap(spacing: 8, runSpacing: 8, children: [
            _CountChip('หัวข้อ', overview.topicCount),
            _CountChip('ชุดเปรียบเทียบ', overview.groupCount),
            _CountChip('ใกล้ High', overview.highCount),
            _CountChip('ใกล้ Low', overview.lowCount),
            _CountChip('ยังสรุปไม่ได้', overview.inconclusiveCount),
          ]),
          const SizedBox(height: 16),
          for (final group in overview.groups) ...[
            _GroupSummary(group: group),
            const SizedBox(height: 10),
          ],
          const SizedBox(height: 12),
          ExpansionTile(
            key: const ValueKey('automatic-performance-detail-toggle'),
            initiallyExpanded: false,
            tilePadding: EdgeInsets.zero,
            title: const Text('ตรวจสอบกราฟ K-Means และคลิปอ้างอิง'),
            subtitle: const Text('เลือกหัวข้อเพื่อดูรายละเอียดได้ โดยไม่เปลี่ยนผลวิเคราะห์อัตโนมัติ'),
            onExpansionChanged: (opened) =>
                setState(() => _showDetails = opened),
            children: [
              if (_showDetails && widget.topics.isNotEmpty)
                PerformanceClusteringPanel(
                  contentId: widget.contentId,
                  repository: widget.repository,
                  topics: widget.topics,
                )
              else if (_showDetails)
                const Text('ยังไม่มีรายละเอียดที่เปิดดูได้'),
            ],
          ),
        ],
        const SizedBox(height: 12),
        Text(overview.limitation, style: theme.textTheme.bodySmall),
        const Divider(height: 36),
      ],
    );
  }
}

class _CountChip extends StatelessWidget {
  const _CountChip(this.label, this.count);
  final String label;
  final int count;

  @override
  Widget build(BuildContext context) => Chip(
        label: Text('$label $count'),
        visualDensity: VisualDensity.compact,
      );
}

class _GroupSummary extends StatelessWidget {
  const _GroupSummary({required this.group});
  final PerformanceOverviewGroup group;

  String get _format => group.format == 'long_form' ? 'คลิปปกติ' :
      group.format == 'short_form' ? 'Shorts' : 'ไม่ทราบรูปแบบ';

  String get _age => switch (group.ageGroup) {
    'age_0_7d' => 'อายุน้อยกว่า 7 วัน',
    'age_7_30d' => 'อายุ 7–30 วัน',
    'age_30_90d' => 'อายุ 30–90 วัน',
    'age_90_365d' => 'อายุ 90–365 วัน',
    'age_365d_plus' => 'อายุมากกว่า 365 วัน',
    _ => 'อายุคลิปไม่ระบุ',
  };

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final primary = theme.colorScheme.primary;
    final neutral = theme.colorScheme.onSurfaceVariant;
    return Card(
      key: ValueKey('automatic-topic-${group.topicId}-${group.groupIndex}'),
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(group.topicTitle, style: theme.textTheme.titleSmall),
            const SizedBox(height: 4),
            Text('$_format · $_age', style: theme.textTheme.bodySmall),
            Text(
              'ในหัวข้อ ${group.topicSampleSize} คลิป · ผ่านเกณฑ์ ${group.passingCount} คลิป · '
              'ใช้จัดกลุ่มจริง ${group.eligibleCount} คลิป',
              style: theme.textTheme.bodySmall,
            ),
            Text(
              'เกณฑ์เดิม: ยอดวิวมากกว่า ${group.thresholdViews} ครั้ง',
              style: theme.textTheme.bodySmall,
            ),
            if (group.clusteringStatus == 'ready') ...[
              const SizedBox(height: 12),
              _SimilarityBar('Low', group.lowScore, neutral),
              const SizedBox(height: 10),
              _SimilarityBar('High', group.highScore, primary),
            ],
            const SizedBox(height: 12),
            Text(
              group.conclusive
                  ? 'เนื้อหาคล้ายกลุ่ม ${group.closestGroup == 'high' ? 'High' : 'Low'} มากกว่า'
                  : 'ยังสรุปไม่ได้: ${performanceReason(group.reason)}',
              key: ValueKey('automatic-result-${group.topicId}-${group.groupIndex}'),
              style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600),
            ),
          ],
        ),
      ),
    );
  }
}

class _SimilarityBar extends StatelessWidget {
  const _SimilarityBar(this.name, this.value, this.color);
  final String name;
  final double? value;
  final Color color;

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(children: [
            Expanded(child: Text('ความคล้ายกลุ่ม $name')),
            Text(value == null ? 'ไม่พร้อม' : '${(value! * 100).toStringAsFixed(2)}%'),
          ]),
          const SizedBox(height: 6),
          LinearProgressIndicator(
            value: value ?? 0,
            minHeight: 7,
            color: color,
            backgroundColor: Theme.of(context).colorScheme.surfaceContainerHigh,
          ),
        ],
      );
}
