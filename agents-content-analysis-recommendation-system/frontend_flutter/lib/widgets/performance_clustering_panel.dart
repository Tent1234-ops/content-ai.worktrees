import 'dart:math' as math;
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/performance_clustering.dart';
import '../models/reference_response.dart';
import '../repositories/content_repository.dart';
import 'state_widgets.dart';
import 'workspace_widgets.dart';

String _number(num value) => value
    .round()
    .toString()
    .replaceAllMapped(RegExp(r'(\d)(?=(\d{3})+(?!\d))'), (m) => '${m[1]},');
String _date(dynamic value) {
  final d = DateTime.tryParse(value?.toString() ?? '')?.toLocal();
  return d == null
      ? 'ไม่มีข้อมูล'
      : '${d.day}/${d.month}/${d.year} ${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
}

String _level(String value) => value == 'high' ? 'High' : 'Low';
Color _tone(BuildContext context, String level) => level == 'high'
    ? Theme.of(context).colorScheme.primary
    : Theme.of(context).colorScheme.onSurfaceVariant;

class PerformanceClusteringPanel extends StatefulWidget {
  const PerformanceClusteringPanel(
      {super.key,
      required this.contentId,
      required this.repository,
      this.topics = const []});
  final int contentId;
  final ContentRepository repository;
  final List<ReferenceResponseTopic> topics;
  @override
  State<PerformanceClusteringPanel> createState() =>
      _PerformanceClusteringPanelState();
}

class _PerformanceClusteringPanelState
    extends State<PerformanceClusteringPanel> {
  final _threshold = TextEditingController();
  PerformanceComparison? _data;
  bool _loading = true;
  String? _error, _thresholdError;
  String _filter = 'all';
  int _limit = 6, _request = 0;
  String? _topicId;
  int _groupIndex = 0;
  String _comparisonMethod = 'embedding_centroid';
  @override
  void initState() {
    super.initState();
    _topicId = widget.topics.isEmpty ? null : widget.topics.first.id;
    _load();
  }

  @override
  void didUpdateWidget(covariant PerformanceClusteringPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.contentId != widget.contentId ||
        oldWidget.repository != widget.repository) {
      _topicId = widget.topics.isEmpty ? null : widget.topics.first.id;
      _groupIndex = 0;
      _load();
    }
  }

  @override
  void dispose() {
    _request++;
    _threshold.dispose();
    super.dispose();
  }

  Future<void> _load({int? minimumViews}) async {
    final request = ++_request;
    setState(() {
      _loading = true;
      _error = null;
      _data = null;
    });
    try {
      final result = await widget.repository.getPerformanceComparison(
          widget.contentId,
          minimumViews: widget.topics.isEmpty ? minimumViews : null,
          comparisonMethod: _comparisonMethod,
          topicId: widget.topics.isEmpty ? null : _topicId,
          groupIndex: widget.topics.isEmpty
              ? null
              : widget.topics
                  .firstWhere((topic) => topic.id == _topicId)
                  .groups[_groupIndex]
                  .sourceGroupIndex);
      if (!mounted || request != _request) return;
      setState(() {
        _data = result;
        _threshold.text = '${result.minimumViews}';
        _thresholdError = null;
        _filter = 'all';
        _limit = 6;
      });
    } catch (_) {
      if (mounted && request == _request) {
        setState(() => _error = 'โหลดการเปรียบเทียบกลุ่มผลงานไม่สำเร็จ');
      }
    } finally {
      if (mounted && request == _request) setState(() => _loading = false);
    }
  }

  void _apply() {
    final value = int.tryParse(_threshold.text.trim());
    if (value == null || value < 0 || value > 9007199254740991) {
      setState(() =>
          _thresholdError = 'ระบุจำนวนเต็มตั้งแต่ 0 ถึง 9,007,199,254,740,991');
      return;
    }
    _load(minimumViews: value);
  }

  @override
  Widget build(BuildContext context) {
    final data = _data;
    if (_loading) {
      return const Padding(
          padding: EdgeInsets.symmetric(vertical: 24),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('กำลังเปรียบเทียบกลุ่มผลงาน...'),
            SizedBox(height: 12),
            LinearProgressIndicator(),
          ]));
    }
    if (_error != null) {
      return ErrorStateView(
          message: _error!,
          onRetry: () => _load(minimumViews: int.tryParse(_threshold.text)));
    }
    if (data == null) return const SizedBox.shrink();
    final colors = Theme.of(context).colorScheme;
    final category = switch (data.category) {
      'phone' => 'Phone',
      'camera' => 'Camera',
      'laptop' => 'Laptop',
      _ => 'Unknown'
    };
    final visible = data.videos
        .where((v) => _filter == 'all' || v['performance_level'] == _filter)
        .toList();
    final selectedTopic =
        widget.topics.where((t) => t.id == _topicId).firstOrNull;
    return Column(
        key: const ValueKey('performance-clustering-panel'),
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SectionHeading(
              title: 'วิเคราะห์กลุ่มผลงาน · $category',
              icon: Icons.scatter_plot_outlined),
          Text(
              widget.topics.isEmpty
                  ? 'ข้อมูลอ้างอิงล่าสุด · คำนวณ ${_date(data.raw['as_of'])}'
                  : 'ใช้กลุ่มที่ผ่าน Benchmark ในหลักฐานอ้างอิงเดิม · คำนวณ ${_date(data.raw['as_of'])}',
              style: Theme.of(context).textTheme.bodySmall),
          Padding(
            padding: const EdgeInsets.only(top: 12, bottom: 8),
            child: DropdownButtonFormField<String>(
              key: const ValueKey('performance-comparison-method'),
              initialValue: _comparisonMethod,
              isExpanded: true,
              decoration:
                  const InputDecoration(labelText: 'วิธีเทียบ Transcript'),
              items: const [
                DropdownMenuItem(
                    value: 'embedding_centroid',
                    child: Text('Text Centroid · SentenceTransformer')),
                DropdownMenuItem(value: 'tfidf', child: Text('TF-IDF + Top-K')),
              ],
              onChanged: (method) {
                if (method == null || method == _comparisonMethod) return;
                setState(() => _comparisonMethod = method);
                _load(minimumViews: int.tryParse(_threshold.text));
              },
            ),
          ),
          if (widget.topics.isNotEmpty) ...[
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              key: const ValueKey('performance-topic-selector'),
              isExpanded: true,
              initialValue: _topicId,
              decoration:
                  const InputDecoration(labelText: 'หัวข้อหลักฐานอ้างอิง'),
              items: [
                for (final topic in widget.topics)
                  DropdownMenuItem(
                      value: topic.id,
                      child: Text(topic.title, overflow: TextOverflow.ellipsis))
              ],
              onChanged: (value) {
                if (value == null || value == _topicId) return;
                setState(() {
                  _topicId = value;
                  _groupIndex = 0;
                });
                _load();
              },
            ),
            if (selectedTopic != null && selectedTopic.groups.length > 1) ...[
              const SizedBox(height: 12),
              DropdownButtonFormField<int>(
                key: ValueKey('performance-group-selector-$_topicId'),
                isExpanded: true,
                initialValue: _groupIndex,
                decoration: const InputDecoration(
                    labelText: 'กลุ่มอ้างอิงเดิม (รูปแบบและอายุคลิป)'),
                items: [
                  for (final (index, group) in selectedTopic.groups.indexed)
                    DropdownMenuItem(
                        value: index,
                        child: Text(
                            '${group.formatLabel} · ${group.ageLabel} · ${group.passingCount}/${group.sampleSize} คลิป',
                            overflow: TextOverflow.ellipsis))
                ],
                onChanged: (value) {
                  if (value == null || value == _groupIndex) return;
                  setState(() => _groupIndex = value);
                  _load();
                },
              ),
            ],
            const SizedBox(height: 12),
            Text(
                'ใช้เฉพาะคลิปที่ผ่านเกณฑ์ยอดวิวตามหลักฐานของหัวข้อนี้ ไม่ใช้คลิปทั้งหมวด',
                style: Theme.of(context).textTheme.bodySmall),
          ],
          const SizedBox(height: 16),
          LayoutBuilder(builder: (context, constraints) {
            final columns = constraints.maxWidth >= 600 ? 3 : 1;
            final width = (constraints.maxWidth - (columns - 1) * 12) / columns;
            return Wrap(spacing: 12, runSpacing: 12, children: [
              for (final metric in [
                (
                  widget.topics.isEmpty ? 'คลิปอ้างอิง' : 'คลิปในหัวข้อ',
                  widget.topics.isEmpty
                      ? data.referenceCount
                      : (data.raw['selection']?['topic_sample_size'] ?? 0)
                ),
                (
                  widget.topics.isEmpty ? 'ใช้จัดกลุ่มได้' : 'ผ่าน Benchmark',
                  widget.topics.isEmpty
                      ? data.eligibleCount
                      : (data.raw['selection']?['passing_count'] ?? 0)
                ),
                (
                  widget.topics.isEmpty ? 'ยอดวิวขั้นต่ำ' : 'ใช้จัดกลุ่มจริง',
                  widget.topics.isEmpty ? data.minimumViews : data.eligibleCount
                )
              ])
                SizedBox(
                    width: width,
                    child: Card(
                        margin: EdgeInsets.zero,
                        child: Padding(
                            padding: const EdgeInsets.all(16),
                            child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(metric.$1,
                                      style: Theme.of(context)
                                          .textTheme
                                          .bodySmall),
                                  const SizedBox(height: 6),
                                  Text(_number(metric.$2),
                                      style: Theme.of(context)
                                          .textTheme
                                          .titleLarge),
                                ])))),
            ]);
          }),
          const SizedBox(height: 16),
          if (widget.topics.isEmpty)
            Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Expanded(
                  child: TextField(
                      key: const ValueKey('performance-minimum-views'),
                      controller: _threshold,
                      keyboardType: TextInputType.number,
                      inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                      decoration: InputDecoration(
                          labelText: 'ยอดวิวขั้นต่ำ',
                          suffixText: 'ครั้ง',
                          errorText: _thresholdError),
                      onSubmitted: (_) => _apply())),
              const SizedBox(width: 8),
              IconButton.filled(
                  onPressed: _apply,
                  style:
                      IconButton.styleFrom(foregroundColor: colors.onPrimary),
                  tooltip: 'คำนวณตามยอดวิวขั้นต่ำ',
                  icon: const Icon(Icons.filter_alt_outlined)),
            ]),
          if (widget.topics.isNotEmpty)
            Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                    'เกณฑ์หลักฐานเดิม: ตั้งแต่ ${_number(data.minimumViews)} วิว (ไม่ใช่เกณฑ์แบ่ง Low/High)',
                    style: Theme.of(context).textTheme.bodySmall)),
          if (data.exclusions.isNotEmpty)
            Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Wrap(spacing: 12, runSpacing: 6, children: [
                  for (final e in data.exclusions.entries)
                    Text('${performanceReason(e.key)}: ${e.value}',
                        style: Theme.of(context).textTheme.bodySmall)
                ])),
          const SizedBox(height: 16),
          Text(data.raw['limitation'] as String? ?? '',
              style: Theme.of(context).textTheme.bodySmall),
          if (!data.clusteringReady)
            Padding(
                padding: const EdgeInsets.symmetric(vertical: 24),
                child: Text(performanceReason(data.clustering['reason'])))
          else ...[
            const SizedBox(height: 24),
            Wrap(spacing: 20, children: [
              for (final level in ['low', 'high'])
                StatusBadge(
                    label: '${_level(level)} Performance',
                    icon: Icons.circle,
                    color: _tone(context, level))
            ]),
            const SizedBox(height: 16),
            _Scatter(videos: data.videos),
            const SizedBox(height: 24),
            LayoutBuilder(builder: (context, constraints) {
              final columns = constraints.maxWidth >= 640 ? 2 : 1;
              final width =
                  (constraints.maxWidth - (columns - 1) * 16) / columns;
              return Wrap(spacing: 16, runSpacing: 16, children: [
                for (final cluster in data.clusters)
                  SizedBox(
                      width: width,
                      child: Card(
                          margin: EdgeInsets.zero,
                          child: Padding(
                              padding: const EdgeInsets.all(20),
                              child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                        '${_level(cluster['performance_level'])} Performance',
                                        style: Theme.of(context)
                                            .textTheme
                                            .titleMedium
                                            ?.copyWith(
                                                color: _tone(
                                                    context,
                                                    cluster[
                                                        'performance_level']))),
                                    const SizedBox(height: 8),
                                    Text('${cluster['video_count']} คลิป'),
                                    Text(
                                        'ยอดวิวเฉลี่ย ${_number(cluster['average_views'])}'),
                                    Text(
                                        'ไลก์เฉลี่ย ${_number(cluster['average_likes'])}'),
                                    const SizedBox(height: 8),
                                    Text(
                                        'ค่ามัธยฐาน: ${_number(cluster['median_views'])} วิว · ${_number(cluster['median_likes'])} ไลก์',
                                        style: Theme.of(context)
                                            .textTheme
                                            .bodySmall),
                                  ]))))
              ]);
            }),
            const SizedBox(height: 24),
            const SectionHeading(
                title: 'เนื้อหาคลิปของคุณใกล้เคียงกลุ่มไหน?',
                icon: Icons.compare_arrows),
            if (data.usesTextCentroid)
              const Padding(
                padding: EdgeInsets.only(bottom: 16),
                child: Text(
                    'Cosine Distance ถึง Text Centroid · ค่ายิ่งน้อยยิ่งใกล้'),
              ),
            for (final value in [
              ('low', data.usesTextCentroid ? data.lowDistance : data.lowScore),
              (
                'high',
                data.usesTextCentroid ? data.highDistance : data.highScore
              )
            ])
              Padding(
                  padding: const EdgeInsets.only(bottom: 16),
                  child: Column(children: [
                    Row(children: [
                      Expanded(
                          child: Text(data.usesTextCentroid
                              ? 'ระยะห่างถึงกลุ่ม ${_level(value.$1)}'
                              : 'ความคล้ายกลุ่ม ${_level(value.$1)}')),
                      Text(
                          value.$2 == null
                              ? 'ยังคำนวณไม่ได้'
                              : data.usesTextCentroid
                                  ? value.$2!.toStringAsFixed(4)
                                  : '${(value.$2! * 100).toStringAsFixed(2)}%',
                          key: ValueKey(
                              '${data.usesTextCentroid ? 'distance' : 'similarity'}-${value.$1}'))
                    ]),
                    const SizedBox(height: 8),
                    if (value.$2 != null)
                      LinearProgressIndicator(
                          value:
                              data.usesTextCentroid ? value.$2! / 2 : value.$2,
                          minHeight: 8,
                          color: _tone(context, value.$1),
                          backgroundColor: colors.surfaceContainerHigh),
                  ])),
            Text(
                data.closest == null
                    ? performanceReason(data.similarity['reason'])
                    : 'เนื้อหาใกล้เคียงกลุ่ม ${_level(data.closest!)} มากกว่าในเชิงข้อความ',
                key: const ValueKey('performance-closest-group'),
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            const Text(
                'คะแนนนี้วัดความคล้ายของเนื้อหา ไม่ใช่การคาดการณ์ยอดวิวหรือยอดไลก์'),
            if (data.similarity['method'] ==
                'sentence_embedding_text_centroid_cosine') ...[
              Text(
                  'Text Centroid จากคลิปอ้างอิง ${data.eligibleCount} คลิป · ไม่ใช้ยอดวิวหรือไลก์ของคลิปคุณ',
                  style: Theme.of(context).textTheme.bodySmall),
              if (data.similarity['margin'] is num)
                Text(
                    'ระยะห่างต่างกัน ${(data.similarity['margin'] as num).toStringAsFixed(4)}',
                    style: Theme.of(context).textTheme.bodySmall),
            ] else
              Text(
                  'ใช้คลิปใกล้เคียงกลุ่มละ ${data.similarity['k_used']} คลิป · TF-IDF + Cosine Similarity',
                  style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 24),
            const SectionHeading(
                title: 'ประเด็นจากกลุ่ม High', icon: Icons.lightbulb_outline),
            if (data.closest == null)
              const Text(
                  'ยังไม่เสนอประเด็นเพิ่มจากการเปรียบเทียบนี้ เพราะผลความคล้ายยังสรุปไม่ได้'),
            if (data.closest != null &&
                data.advice.isEmpty &&
                data.sharedKeywords.isEmpty &&
                data.missingKeywords.isEmpty)
              const Text(
                  'ยังไม่มีประเด็นที่มีหลักฐานจากหลายช่องเพียงพอสำหรับแนะนำเพิ่ม'),
            if (data.sharedKeywords.isNotEmpty)
              _Keywords(
                  label: 'คำที่พบร่วมกับกลุ่ม High',
                  words: data.sharedKeywords),
            if (data.missingKeywords.isNotEmpty)
              _Keywords(
                  label: 'คำในกลุ่ม High ที่ยังไม่พบในข้อความของคุณ',
                  words: data.missingKeywords),
            for (final advice in data.advice)
              Padding(
                  padding: const EdgeInsets.only(bottom: 16),
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('${advice['title']}',
                            style: Theme.of(context).textTheme.titleSmall),
                        Text('${advice['message']}'),
                        Text(
                            'พบใน ${advice['support_count']} คลิป จาก ${advice['channel_count']} ช่อง',
                            style: Theme.of(context).textTheme.bodySmall),
                        for (final ref in (advice['references'] as List? ?? [])
                            .whereType<Map>()) ...[
                          const SizedBox(height: 8),
                          Text('“${ref['quote']}”'),
                          for (final video in data.videos.where(
                              (v) => v['dataset_id'] == ref['dataset_id']))
                            TextButton.icon(
                                onPressed: () => _open(context, video),
                                icon: const Icon(Icons.open_in_new, size: 16),
                                label: Text('${video['title']}',
                                    maxLines: 2,
                                    overflow: TextOverflow.ellipsis)),
                        ],
                      ])),
            const Divider(height: 32),
            const SectionHeading(
                title: 'คลิปที่ใช้จัดกลุ่ม',
                icon: Icons.video_library_outlined),
            Wrap(spacing: 8, children: [
              for (final filter in ['all', 'low', 'high'])
                ChoiceChip(
                    key: ValueKey('performance-filter-$filter'),
                    label: Text(filter == 'all' ? 'All' : _level(filter)),
                    selected: _filter == filter,
                    onSelected: (_) => setState(() {
                          _filter = filter;
                          _limit = 6;
                        }))
            ]),
            const SizedBox(height: 12),
            Text('${visible.length} คลิป'),
            for (final video in visible.take(_limit)) _Video(video: video),
            if (visible.length > _limit)
              TextButton.icon(
                  onPressed: () => setState(() => _limit += 6),
                  icon: const Icon(Icons.expand_more),
                  label: const Text('ดูคลิปเพิ่มเติม')),
          ],
          const Divider(height: 40),
        ]);
  }
}

class _Scatter extends StatelessWidget {
  const _Scatter({required this.videos});
  final List<Map<String, dynamic>> videos;
  @override
  Widget build(BuildContext context) {
    final spots = [
      for (final (index, v) in videos.indexed)
        ScatterSpot(
            (v['views'] as num).toDouble(), (v['likes'] as num).toDouble(),
            renderPriority: index,
            dotPainter: FlDotCirclePainter(
                radius: 5,
                color: _tone(context, v['performance_level']),
                strokeWidth: 1,
                strokeColor: Theme.of(context).colorScheme.surface))
    ];
    final maxX = math.max(1.0, spots.map((p) => p.x).reduce(math.max) * 1.12);
    final maxY = math.max(1.0, spots.map((p) => p.y).reduce(math.max) * 1.12);
    String tick(double v) => v >= 1000000
        ? '${(v / 1000000).toStringAsFixed(1)}M'
        : v >= 1000
            ? '${(v / 1000).toStringAsFixed(0)}K'
            : '${v.round()}';
    AxisTitles axis(String title, double max, double reserved) => AxisTitles(
        axisNameWidget: Text(title),
        axisNameSize: 24,
        sideTitles: SideTitles(
            showTitles: true,
            reservedSize: reserved,
            interval: max / 4,
            minIncluded: true,
            maxIncluded: false,
            getTitlesWidget: (v, meta) => SideTitleWidget(
                meta: meta,
                child: Text(tick(v),
                    style: Theme.of(context).textTheme.bodySmall))));
    return Semantics(
        container: true,
        image: true,
        label: 'กราฟกระจายยอดวิวและไลก์ของคลิปอ้างอิง ${videos.length} คลิป',
        child: SizedBox(
            key: const ValueKey('performance-scatter'),
            height: 340,
            child: ScatterChart(
                ScatterChartData(
                  minX: 0,
                  maxX: maxX,
                  minY: 0,
                  maxY: maxY,
                  scatterSpots: spots,
                  titlesData: FlTitlesData(
                      topTitles: const AxisTitles(),
                      rightTitles: const AxisTitles(),
                      bottomTitles: axis('Views · ยอดวิวสะสม', maxX, 30),
                      leftTitles: axis('Likes · ไลก์สะสม', maxY, 42)),
                  borderData: FlBorderData(
                      show: true,
                      border: Border.all(
                          color: Theme.of(context).colorScheme.outlineVariant)),
                  gridData: FlGridData(
                      show: true,
                      horizontalInterval: maxY / 4,
                      verticalInterval: maxX / 4,
                      getDrawingHorizontalLine: (_) => FlLine(
                          color: Theme.of(context).colorScheme.outlineVariant,
                          strokeWidth: 1),
                      getDrawingVerticalLine: (_) => FlLine(
                          color: Theme.of(context).colorScheme.outlineVariant,
                          strokeWidth: 1)),
                  scatterTouchData: ScatterTouchData(
                      touchSpotThreshold: 12,
                      touchTooltipData: ScatterTouchTooltipData(
                          maxContentWidth: 220,
                          fitInsideHorizontally: true,
                          fitInsideVertically: true,
                          getTooltipColor: (_) =>
                              Theme.of(context).colorScheme.inverseSurface,
                          getTooltipItems: (spot) {
                            final index = spot.renderPriority;
                            if (index < 0 || index >= videos.length) {
                              return null;
                            }
                            final v = videos[index];
                            return ScatterTooltipItem(
                                '${v['title']}\n${_level(v['performance_level'])} · ${_number(v['views'])} วิว · ${_number(v['likes'])} ไลก์',
                                textStyle: TextStyle(
                                    fontSize: 12,
                                    color: Theme.of(context)
                                        .colorScheme
                                        .onInverseSurface));
                          })),
                ),
                duration: const Duration(milliseconds: 180))));
  }
}

class _Keywords extends StatelessWidget {
  const _Keywords({required this.label, required this.words});
  final String label;
  final List<String> words;
  @override
  Widget build(BuildContext context) => Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label),
        const SizedBox(height: 8),
        Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [for (final word in words) Chip(label: Text(word))])
      ]));
}

Future<void> _open(BuildContext context, Map<String, dynamic> video) async {
  try {
    final id = video['video_id'] as String;
    if (RegExp(r'^[A-Za-z0-9_-]{11}$').hasMatch(id) &&
        await launchUrl(Uri.https('www.youtube.com', '/watch', {'v': id}),
            mode: LaunchMode.externalApplication)) {
      return;
    }
  } catch (_) {/* Show the same recoverable state for unsupported launchers. */}
  if (context.mounted) {
    ScaffoldMessenger.of(context)
        .showSnackBar(const SnackBar(content: Text('เปิดคลิปต้นทางไม่สำเร็จ')));
  }
}

class _Video extends StatelessWidget {
  const _Video({required this.video});
  final Map<String, dynamic> video;
  @override
  Widget build(BuildContext context) => Padding(
      key: ValueKey('performance-video-${video['dataset_id']}'),
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
              child: Text('${video['title']}',
                  style: Theme.of(context).textTheme.titleSmall)),
          IconButton(
              tooltip: 'เปิดคลิป YouTube',
              onPressed: () => _open(context, video),
              icon: const Icon(Icons.open_in_new))
        ]),
        Text(
            '${video['channel_title']} · เผยแพร่ ${_date(video['published_at'])}',
            style: Theme.of(context).textTheme.bodySmall),
        const SizedBox(height: 8),
        Wrap(spacing: 16, runSpacing: 8, children: [
          StatusBadge(
              label: _level(video['performance_level']),
              icon: Icons.circle,
              color: _tone(context, video['performance_level'])),
          Text('${_number(video['views'])} วิว'),
          Text('${_number(video['likes'])} ไลก์')
        ]),
        Text(
            'เก็บสถิติ ${_date(video['statistics_captured_at'])} (เวลาท้องถิ่น)',
            style: Theme.of(context).textTheme.bodySmall),
        const Divider(),
      ]));
}
