import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../repositories/admin_repository.dart';
import 'state_widgets.dart';

class DatasetReadinessPanel extends StatefulWidget {
  const DatasetReadinessPanel({super.key, required this.repository});
  final AdminRepository repository;
  @override
  State<DatasetReadinessPanel> createState() => _DatasetReadinessPanelState();
}

class _DatasetReadinessPanelState extends State<DatasetReadinessPanel> {
  Map<String, dynamic>? _data;
  String _category = 'all', _role = 'all';
  int _offset = 0, _request = 0;
  bool _loading = true;
  String? _error;
  static const _roles = {
    'all': 'ทุกบทบาท',
    'classification': 'ฝึกจำแนกหมวด',
    'evaluation': 'กันไว้ประเมิน',
    'reference': 'ใช้เป็นคลิปอ้างอิงได้',
    'current_trend': 'พบในเทรนด์ล่าสุด',
    'trend_archive': 'ข้อมูลเทรนด์ที่เก็บไว้',
    'needs_attention': 'มีข้อมูลต้องตรวจ',
  };
  static const _categories = {
    'phone': 'มือถือ',
    'camera': 'กล้อง',
    'laptop': 'โน้ตบุ๊ก'
  };
  Map<String, dynamic> _map(dynamic value) =>
      value is Map ? Map<String, dynamic>.from(value) : {};
  List<Map<String, dynamic>> _rows(dynamic value) =>
      value is List ? value.map(_map).toList() : [];
  String _time(dynamic value) {
    final time =
        DateTime.tryParse('$value')?.toUtc().add(const Duration(hours: 7));
    if (time == null) return 'ไม่มีข้อมูล';
    return '${time.day}/${time.month}/${time.year} ${time.hour.toString().padLeft(2, '0')}:${time.minute.toString().padLeft(2, '0')}';
  }

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final request = ++_request;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await widget.repository
          .datasetReadiness(category: _category, role: _role, offset: _offset);
      if (mounted && request == _request) setState(() => _data = data);
    } catch (_) {
      if (mounted && request == _request) {
        setState(() => _error = 'ตรวจคุณภาพข้อมูลไม่สำเร็จ');
      }
    } finally {
      if (mounted && request == _request) setState(() => _loading = false);
    }
  }

  Widget _heading(String title) => Padding(
      padding: const EdgeInsets.only(top: 24, bottom: 12),
      child: Text(title, style: Theme.of(context).textTheme.titleMedium));

  Widget _plan(Map<String, dynamic> plan) {
    final splits = _map(plan['split_counts']);
    final comparison = _map(plan['topic_comparison']);
    final comparisonTopics = _rows(comparison['topics']);
    final comparisonGaps = _map(comparison['metadata_or_statistics_gaps']);
    final category = '${plan['category']}';
    return ExpansionTile(
      key: PageStorageKey('plan-$category'),
      tilePadding: EdgeInsets.zero,
      title: Text(_categories[category] ?? category),
      subtitle: Text(
          'ผ่านเกณฑ์จำแนก ${plan['classification_count']} คลิป · ${plan['channels']} ช่อง · '
          'ฝึก ${splits['train'] ?? 0} / Validation ${splits['validation'] ?? 0} / Test ${splits['test'] ?? 0}'),
      children: [
        Align(
            alignment: Alignment.centerLeft,
            child: Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                        'กลุ่มคะแนนบน ${plan['upper_pool_count']} · คลิปเปรียบเทียบทั่วไป ${plan['comparison_pool_count']} · '
                        'หลักฐานความยาว ${plan['duration_count']}'),
                    Text(
                        'สัดส่วนช่องที่มีข้อมูลมากที่สุด ${((plan['largest_channel_share'] as num? ?? 0) * 100).toStringAsFixed(1)}%'),
                    if (comparison.isNotEmpty) ...[
                      const SizedBox(height: 12),
                      Text(
                          'ความพร้อมเปรียบเทียบหัวข้อ: ${comparison['eligible_video_count'] ?? 0} คลิป · '
                          '${comparison['channels'] ?? 0} ช่อง',
                          style: const TextStyle(fontWeight: FontWeight.w600)),
                      Text(
                          '${comparison['representativeness_limitation'] ?? ''}'),
                      if (comparisonGaps.isNotEmpty)
                        Text(
                            'ข้อมูลที่ยังขาด: ${comparisonGaps.entries.map((entry) => '${entry.key} ${entry.value}').join(' · ')}'),
                      for (final topic in comparisonTopics)
                        Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: Text(
                              '${topic['title']}: พบ ${topic['detected_count']} / ยังไม่พบ ${topic['not_detected_count']} คลิป · '
                              'ช่องคู่เทียบ ${topic['paired_channel_count']} · ${_comparisonStatus(topic['views_status'])}'),
                        ),
                    ],
                    const SizedBox(height: 8),
                    for (final action in plan['actions'] as List? ?? [])
                      Padding(
                          padding: const EdgeInsets.symmetric(vertical: 4),
                          child: Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Icon(Icons.arrow_right, size: 20),
                                const SizedBox(width: 4),
                                Expanded(child: Text('$action')),
                              ])),
                  ]),
            )),
      ],
    );
  }

  String _comparisonStatus(dynamic value) => switch (value) {
        'comparison_supported' => 'เปรียบเทียบพร้อมและมีทิศทางในตัวอย่าง',
        'comparison_uncertain' => 'เปรียบเทียบได้แต่ทิศทางยังไม่แน่ชัด',
        'comparison_descriptive' =>
          'แสดงค่ากลางได้ ยังประเมินความไม่แน่นอนไม่พอ',
        'reference_only' => 'ใช้ได้เพียงยืนยันว่าพบในคลิปอ้างอิง',
        _ => 'ยังไม่มีกลุ่มที่เปรียบเทียบกันได้',
      };

  Widget _item(Map<String, dynamic> item) {
    final roles = item['roles'] as List? ?? [];
    final blockers = item['reference_blockers'] as List? ?? [];
    final url = Uri.tryParse('${item['video_url'] ?? ''}');
    return ExpansionTile(
      key: PageStorageKey('audit-${item['dataset_id']}'),
      tilePadding: EdgeInsets.zero,
      title: Text('#${item['dataset_id']} ${item['title']}'),
      subtitle: Text(
          '${roles.isEmpty ? 'ยังไม่ผ่านเกณฑ์ใช้งาน' : roles.map((r) => _roles[r] ?? r).join(' · ')}\n'
          '${item['data_split']} · ${item['channel'] ?? 'ไม่มีข้อมูลช่อง'} · '
          '${item['reference_selected'] == true ? 'อยู่ในกลุ่มคลิปต้นแบบที่เลือก' : 'ไม่ได้อยู่ในกลุ่มคลิปต้นแบบที่เลือก'}'),
      children: [
        Align(
            alignment: Alignment.centerLeft,
            child: Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Wrap(spacing: 24, runSpacing: 8, children: [
                      Text('เผยแพร่ ${_time(item['published_at'])}'),
                      Text(
                          'เก็บสถิติ ${_time(item['statistics_captured_at'])}'),
                      Text('ความยาว ${item['duration_seconds'] ?? '-'} วินาที'),
                      Text('ภาษา ${item['language'] ?? '-'}'),
                    ]),
                    Text('Channel ID: ${item['source_channel_id'] ?? '-'}'),
                    if (url != null && ['http', 'https'].contains(url.scheme))
                      TextButton.icon(
                          onPressed: () async {
                            if (!await launchUrl(url,
                                    mode: LaunchMode.externalApplication) &&
                                mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(
                                      content: Text('เปิดต้นทางไม่สำเร็จ')));
                            }
                          },
                          icon: const Icon(Icons.open_in_new),
                          label: const Text('ดูต้นทาง')),
                    const SizedBox(height: 8),
                    for (final check in _rows(item['checks']))
                      Padding(
                          padding: const EdgeInsets.symmetric(vertical: 3),
                          child: Row(children: [
                            Icon(
                                check['ok'] == true
                                    ? Icons.check_circle_outline
                                    : Icons.error_outline,
                                color: check['ok'] == true
                                    ? Colors.green.shade700
                                    : Theme.of(context).colorScheme.error,
                                size: 18),
                            const SizedBox(width: 8),
                            Expanded(child: Text('${check['label']}')),
                          ])),
                    if (blockers.isNotEmpty) ...[
                      const SizedBox(height: 12),
                      const Text('เหตุผลที่ยังไม่ใช้เป็นคลิปอ้างอิง',
                          style: TextStyle(fontWeight: FontWeight.w600)),
                      for (final blocker in blockers) Text('$blocker'),
                    ],
                    for (final evidence in _rows(item['trend_evidence']))
                      Text(
                          'เทรนด์ ${evidence['scope']} #${evidence['rank']} · ${_time(evidence['observed_at'])} · Snapshot #${evidence['run_id']}'),
                  ]),
            )),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_error != null) return ErrorStateView(message: _error!, onRetry: _load);
    if (_data == null) return const Center(child: CircularProgressIndicator());
    final data = _data!;
    final summary = _map(data['summary']);
    final plans = _rows(data['plans']);
    final feeds = _rows(_map(data['current_trends'])['feeds']);
    final globalFeeds = feeds.where((f) => f['scope'] == 'global');
    return SingleChildScrollView(
        child: Center(
            child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 1200),
      child: Padding(
          padding: const EdgeInsets.all(24),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Row(children: [
              Expanded(
                  child: Text('บทบาทและความพร้อมของข้อมูล',
                      style: Theme.of(context).textTheme.titleLarge)),
              IconButton(
                  onPressed: _loading ? null : _load,
                  tooltip: 'ตรวจข้อมูลล่าสุด',
                  icon: const Icon(Icons.refresh))
            ]),
            Text('ตรวจล่าสุด ${_time(data['generated_at'])} · เวลาไทย'),
            if (_loading) const LinearProgressIndicator(),
            const SizedBox(height: 20),
            Wrap(spacing: 24, runSpacing: 16, children: [
              for (final entry in const {
                'classification': 'ใช้ฝึกจำแนก',
                'evaluation': 'กันไว้ประเมิน',
                'reference': 'ผ่านเกณฑ์อ้างอิง',
                'reference_selected': 'คลิปต้นแบบที่เลือก',
                'needs_attention': 'มีข้อมูลต้องตรวจ'
              }.entries)
                SizedBox(
                    width: 176,
                    child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('${summary[entry.key] ?? 0}',
                              style: Theme.of(context).textTheme.headlineSmall),
                          Text(entry.value),
                        ])),
            ]),
            const SizedBox(height: 16),
            const Text(
                'ชุดอ้างอิง: Train เท่านั้น · กัน Validation/Test และช่องที่ซ้ำออก · บทบาทข้อมูลอาจซ้อนกัน'),
            _heading('กระแสปัจจุบัน'),
            if (globalFeeds.isEmpty)
              const Text('ยังไม่มี Snapshot จริงสำหรับตรวจเทรนด์'),
            for (final feed in globalFeeds)
              Text(
                  '${feed['platform']} · ${feed['count']} รายการ · ${_time(feed['observed_at'])} · '
                  '${feed['fresh'] == true ? 'ข้อมูลไม่เกิน 24 ชั่วโมง' : 'ข้อมูลเก่า ไม่ใช่กระแสปัจจุบัน'}'),
            Text(
                'คลิปใน Dataset ที่พบในอันดับล่าสุด ${summary['current_trend'] ?? 0} รายการ'),
            _heading('แผนเก็บข้อมูลรายหมวด'),
            const Text(
                'เป้าหมายเริ่มต้น 80–100 คลิป/หมวด จากอย่างน้อย 10 ช่อง ไม่ใช่เกณฑ์รับรองความแม่นยำ'),
            const Text(
                'กลุ่มคะแนนบนและกลุ่มเปรียบเทียบเป็นการแบ่งภายในข้อมูลหมวดเดียวกัน ไม่พิสูจน์ว่าพูดคำใดแล้วทำให้ยอดเพิ่ม'),
            for (final plan in plans
                .where((p) => _category == 'all' || p['category'] == _category))
              _plan(plan),
            _heading('ตรวจรายรายการ'),
            Wrap(spacing: 16, runSpacing: 12, children: [
              SizedBox(
                  width: 260,
                  child: DropdownButtonFormField<String>(
                    key: const ValueKey('audit-category'),
                    isExpanded: true,
                    initialValue: _category,
                    decoration: const InputDecoration(labelText: 'หมวดหมู่'),
                    items: [
                      const DropdownMenuItem(
                          value: 'all', child: Text('ทุกหมวด')),
                      for (final plan in plans)
                        DropdownMenuItem(
                            value: '${plan['category']}',
                            child: Text(_categories[plan['category']] ??
                                '${plan['category']}'))
                    ],
                    onChanged: _loading
                        ? null
                        : (value) {
                            if (value != null) {
                              setState(() {
                                _category = value;
                                _offset = 0;
                              });
                              _load();
                            }
                          },
                  )),
              SizedBox(
                  width: 300,
                  child: DropdownButtonFormField<String>(
                    key: const ValueKey('audit-role'),
                    isExpanded: true,
                    initialValue: _role,
                    decoration:
                        const InputDecoration(labelText: 'บทบาทหรือสถานะ'),
                    items: _roles.entries
                        .map((e) => DropdownMenuItem(
                            value: e.key, child: Text(e.value)))
                        .toList(),
                    onChanged: _loading
                        ? null
                        : (value) {
                            if (value != null) {
                              setState(() {
                                _role = value;
                                _offset = 0;
                              });
                              _load();
                            }
                          },
                  )),
            ]),
            const SizedBox(height: 16),
            Text('พบ ${data['total']} รายการ'),
            if (_rows(data['items']).isEmpty)
              const Padding(
                  padding: EdgeInsets.all(24),
                  child: Text('ไม่มีรายการที่ตรงกับตัวกรอง')),
            for (final item in _rows(data['items'])) _item(item),
            PaginationBar(
                offset: _offset,
                limit: 20,
                total: (data['total'] as num).toInt(),
                onPrevious: _loading || _offset == 0
                    ? null
                    : () {
                        setState(() => _offset -= 20);
                        _load();
                      },
                onNext: _loading || _offset + 20 >= (data['total'] as num)
                    ? null
                    : () {
                        setState(() => _offset += 20);
                        _load();
                      }),
          ])),
    )));
  }
}
