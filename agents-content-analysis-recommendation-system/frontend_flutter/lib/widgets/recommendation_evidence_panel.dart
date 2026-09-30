import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

Map<String, dynamic> _map(dynamic value) =>
    value is Map ? Map<String, dynamic>.from(value) : const {};
List<Map<String, dynamic>> _rows(dynamic value) =>
    value is List ? value.whereType<Map>().map(_map).toList() : const [];

String _status(dynamic value) => switch (value) {
      'detected' => 'ตรวจพบแล้ว',
      'not_detected' => 'ยังไม่ตรวจพบในข้อความที่วิเคราะห์',
      _ => 'ตรวจไม่ได้จากข้อมูลที่มี',
    };
String _date(dynamic value) {
  final parsed = DateTime.tryParse(value?.toString() ?? '');
  return parsed == null
      ? 'ไม่มีข้อมูลเวลา'
      : '${parsed.toLocal().toString().split('.').first} (เวลาท้องถิ่น)';
}

String _number(dynamic value) {
  if (value is! num) return 'ไม่มีข้อมูล';
  final number = value.toDouble();
  return number == number.roundToDouble()
      ? number.toInt().toString()
      : number.toStringAsFixed(2);
}

class RecommendationEvidencePanel extends StatelessWidget {
  const RecommendationEvidencePanel(
      {super.key, required this.bundle, this.expandTopics = false});
  final Map<String, dynamic> bundle;
  final bool expandTopics;

  @override
  Widget build(BuildContext context) {
    final documents = <dynamic, Map<String, dynamic>>{
      for (final doc in _rows(bundle['reference_documents']))
        doc['dataset_id']: doc,
    };
    final topics = _rows(bundle['topics']);
    final recommendations = _rows(bundle['recommendations']);
    final comparisons = <String, Map<String, dynamic>>{
      for (final row in _rows(_map(bundle['topic_comparisons'])['items']))
        '${row['evidence_topic_id']}': row,
    };
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      if (bundle['origin'] == 'recomputed_legacy_not_original')
        const Padding(
            padding: EdgeInsets.symmetric(vertical: 12),
            child: Text(
                'ผลเก่าไม่มีคำแนะนำบันทึกไว้ ส่วนนี้คำนวณใหม่จากข้อมูลปัจจุบัน ไม่ใช่หลักฐานที่เก็บในวันวิเคราะห์เดิม')),
      if (topics.isEmpty) const Text('ยังไม่มีหลักฐานรายหัวข้อในผลนี้'),
      for (final topic in topics)
        ExpansionTile(
          key: ValueKey('evidence-${topic['canonical_topic']}'),
          initiallyExpanded: expandTopics,
          tilePadding: EdgeInsets.zero,
          title: Text(
              (topic['title_th'] ?? topic['canonical_topic'])?.toString() ??
                  ''),
          subtitle: Text('${_status(_map(topic['user'])['status'])} · '
              'หลักฐาน ${topic['support_count'] ?? 0} คลิป / ${topic['channel_count'] ?? 0} ช่อง'),
          children: [
            Align(
                alignment: Alignment.centerLeft,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                        'คำที่ใช้ตรวจ: ${(topic['synonyms'] as List? ?? []).join(', ')}'),
                    const SizedBox(height: 8),
                    TranscriptObservation(
                        title: 'ทั้งคลิป', observation: _map(topic['user'])),
                    TranscriptObservation(
                        title: 'ช่วงเปิดคลิป',
                        observation: _map(topic['user_hook'])),
                    if (recommendations.any((row) =>
                        row['topic_id'] == topic['topic_id'] &&
                        row['kind'] == 'opening_suggestion'))
                      const Text(
                          'ข้อเสนอสำหรับช่วงเปิดมาจากหัวข้อที่ยังไม่ตรวจพบทั้งคลิป ไม่ใช่หลักฐานว่าคลิปต้นแบบใช้คำนี้ในช่วงเปิด'),
                    for (final reference in _rows(topic['references']))
                      _Reference(
                          document:
                              documents[reference['dataset_id']] ?? const {},
                          support: reference),
                    if (comparisons.containsKey('${topic['topic_id']}'))
                      _TopicComparison(
                          comparison: comparisons['${topic['topic_id']}']!,
                          asOf: _map(bundle['topic_comparisons'])['as_of']),
                    const SizedBox(height: 12),
                  ],
                )),
          ],
        ),
      ExpansionTile(
        tilePadding: EdgeInsets.zero,
        title: const Text('เวอร์ชันและเวลาของหลักฐาน'),
        children: [
          Align(
              alignment: Alignment.centerLeft,
              child: SelectableText(
                'จัดทำเมื่อ ${_date(bundle['generated_at'])}\n'
                'วิธีวิเคราะห์: ${bundle['method_version']}\n'
                'ชุดคำพ้อง: ${bundle['synonym_version']}\n'
                'รหัสข้อมูล: ${bundle['data_fingerprint']}\n'
                'การรวมคำ: ${bundle['canonicalization'] == 'curated_synonyms' ? 'รวมคำพ้องที่ตรวจแล้ว' : 'คำจากข้อความ ยังไม่มีชุดคำพ้องสำหรับหมวดนี้'}',
              ))
        ],
      ),
    ]);
  }
}

class _TopicComparison extends StatelessWidget {
  const _TopicComparison({required this.comparison, required this.asOf});
  final Map<String, dynamic> comparison;
  final dynamic asOf;

  static const _metricLabels = {
    'views': 'ยอดวิวสะสม ณ เวลาเก็บข้อมูล',
    'likes_per_1000_views': 'ไลก์ต่อ 1,000 วิว',
    'comments_per_1000_views': 'ความคิดเห็นต่อ 1,000 วิว',
    'views_per_hour': 'ยอดวิวเพิ่มเฉลี่ยต่อชั่วโมงจริง',
  };

  String _statusText(String status) => switch (status) {
        'comparison_supported' =>
          'พบความแตกต่างในตัวอย่างนี้ โดยมีช่วงความไม่แน่นอนไม่คร่อมศูนย์',
        'comparison_uncertain' =>
          'ยังสรุปทิศทางความแตกต่างไม่ได้ เพราะช่วงความไม่แน่นอนคร่อมศูนย์',
        'comparison_descriptive' =>
          'แสดงค่ากลางได้ แต่จำนวนช่องยังไม่พอประเมินช่วงความไม่แน่นอน',
        'reference_only' =>
          'พบในคลิปอ้างอิง แต่กลุ่มเปรียบเทียบยังเล็กเกินกว่าจะสรุป',
        _ => 'ยังไม่มีกลุ่มตรวจพบและยังไม่ตรวจพบที่เปรียบเทียบกันได้',
      };

  @override
  Widget build(BuildContext context) {
    final cohort = _map(comparison['cohort']);
    final metrics = _map(comparison['metrics']);
    return ExpansionTile(
      key: ValueKey('topic-comparison-${comparison['evidence_topic_id']}'),
      tilePadding: EdgeInsets.zero,
      title: const Text('เปรียบเทียบผลตอบรับของคลิปอ้างอิง'),
      subtitle: Text(
          'ตรวจพบ ${cohort['detected_count'] ?? 0} · ยังไม่ตรวจพบ ${cohort['not_detected_count'] ?? 0} คลิป'),
      children: [
        Align(
          alignment: Alignment.centerLeft,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('อ้างอิงสถิติล่าสุดไม่เกิน ${_date(asOf)}'),
              Text(
                  'กลุ่มคลิปผลตอบรับสูง ${cohort['support_cohort_video_count'] ?? 0} · '
                  'คลิปอ้างอิงอื่น ${cohort['comparison_pool_video_count'] ?? 0}'),
              const SizedBox(height: 8),
              for (final entry in metrics.entries)
                _ComparisonMetric(
                    title: _metricLabels[entry.key] ?? entry.key,
                    metric: _map(entry.value),
                    statusText: _statusText),
              const SizedBox(height: 8),
              Text('${comparison['limitation'] ?? ''}',
                  style: Theme.of(context).textTheme.bodySmall),
            ],
          ),
        ),
      ],
    );
  }
}

class _ComparisonMetric extends StatelessWidget {
  const _ComparisonMetric(
      {required this.title, required this.metric, required this.statusText});
  final String title;
  final Map<String, dynamic> metric;
  final String Function(String) statusText;

  @override
  Widget build(BuildContext context) {
    final detected = _map(metric['detected']);
    final absent = _map(metric['not_detected']);
    final uncertainty = _map(metric['uncertainty']);
    final interval = uncertainty['status'] == 'available'
        ? 'ช่วงความไม่แน่นอน 95% ${_number(uncertainty['low'])} ถึง ${_number(uncertainty['high'])}'
        : 'ยังไม่มีช่วงความไม่แน่นอน (${uncertainty['reason'] ?? 'ข้อมูลไม่พอ'})';
    return ExpansionTile(
      tilePadding: EdgeInsets.zero,
      title: Text(title),
      subtitle: Text(statusText('${metric['status']}')),
      children: [
        Align(
          alignment: Alignment.centerLeft,
          child: Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text('กลุ่มตรวจพบ: ${_summaryArm(detected)}'),
                Text('กลุ่มยังไม่ตรวจพบ: ${_summaryArm(absent)}'),
                Text(
                    'ช่องที่มีทั้งสองกลุ่ม ${metric['paired_channel_count'] ?? 0} ช่อง · '
                    'ผลต่างค่ากลางภายในช่อง ${_number(metric['within_channel_median_difference'])}'),
                Text(interval),
                const Text(
                    'ค่าบวกหมายถึงกลุ่มตรวจพบสูงกว่าในตัวอย่างนี้ ค่าลบหมายถึงต่ำกว่า ไม่ใช่ผลเชิงสาเหตุ'),
              ],
            ),
          ),
        ),
      ],
    );
  }

  String _summaryArm(Map<String, dynamic> arm) =>
      '${arm['count'] ?? 0} คลิป · ค่ากลาง ${_number(arm['median'])} · '
      'P25–P75 ${_number(arm['p25'])}–${_number(arm['p75'])}';
}

class TranscriptObservation extends StatelessWidget {
  const TranscriptObservation(
      {super.key, required this.title, required this.observation});
  final String title;
  final Map<String, dynamic> observation;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child:
            Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text('$title: ${_status(observation['status'])}',
              style: Theme.of(context).textTheme.titleSmall),
          if (observation['source_field'] == 'cleaned_transcript')
            const Text('ข้อความหลังปรับศัพท์ ไม่มีเวลาอ้างอิงที่ยืนยันได้'),
          for (final quote in _rows(observation['occurrences']))
            _Quote(quote: quote),
        ]),
      );
}

class _Quote extends StatelessWidget {
  const _Quote({required this.quote});
  final Map<String, dynamic> quote;
  @override
  Widget build(BuildContext context) {
    final timestamp = _map(quote['timestamp']);
    return Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SelectableText('"${quote['quote']}"'),
            Text(
                timestamp.isEmpty
                    ? 'ไม่มี Timestamp จากต้นทาง'
                    : 'ช่วงเสียง ${timestamp['start_seconds']} ถึง ${timestamp['end_seconds']} วินาที (ระดับช่วงเสียง ไม่ใช่เวลารายคำ)',
                style: Theme.of(context).textTheme.bodySmall),
          ],
        ));
  }
}

class _Reference extends StatelessWidget {
  const _Reference({required this.document, required this.support});
  final Map<String, dynamic> document, support;

  Future<void> _open(BuildContext context) async {
    final uri = Uri.tryParse(document['url']?.toString() ?? '');
    try {
      if (uri != null &&
          ['https', 'http'].contains(uri.scheme) &&
          await launchUrl(uri, mode: LaunchMode.externalApplication)) {
        return;
      }
    } catch (_) {
      /* Show the same failure state for unsupported or failed URLs. */
    }
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('เปิดคลิปต้นทางไม่สำเร็จ')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final stats = _map(document['statistics']);
    return ExpansionTile(
      title: Text(
          document['title']?.toString() ?? 'Dataset #${support['dataset_id']}'),
      subtitle: Text(
          'Dataset #${support['dataset_id']} · พบ ${support['frequency']} ครั้ง · '
          '${document['channel_title'] ?? 'ไม่ทราบชื่อช่อง'}'),
      children: [
        Padding(
            padding: const EdgeInsets.only(bottom: 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                for (final quote in _rows(support['occurrences']))
                  _Quote(quote: quote),
                Text(
                    'ยอดวิว ${stats['views'] ?? 'ไม่มีข้อมูล'} · ไลก์ ${stats['likes'] ?? 'ไม่มีข้อมูล'} · ความคิดเห็น ${stats['comments'] ?? 'ไม่มีข้อมูล'}'),
                Text('เผยแพร่ ${_date(document['published_at'])}'),
                Text('เก็บสถิติ ${_date(document['statistics_captured_at'])}'),
                Text(
                    'เวอร์ชัน Dataset: ${document['dataset_version'] ?? 'ไม่มีข้อมูล'}'),
                Text('รหัสวิดีโอ: ${document['video_id'] ?? 'ไม่มีข้อมูล'}'),
                if (document['url'] != null)
                  Align(
                      alignment: Alignment.centerLeft,
                      child: TextButton.icon(
                          onPressed: () => _open(context),
                          icon: const Icon(Icons.open_in_new),
                          label: const Text('เปิดคลิปต้นทาง'))),
              ],
            ))
      ],
    );
  }
}
