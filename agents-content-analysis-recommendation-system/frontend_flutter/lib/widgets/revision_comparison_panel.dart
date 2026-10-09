import 'package:flutter/material.dart';
import '../models/outcome_prediction.dart';

class RevisionComparisonPanel extends StatelessWidget {
  const RevisionComparisonPanel(
      {super.key, required this.data, this.onOpenParent});
  final Map<String, dynamic> data;
  final VoidCallback? onOpenParent;

  Map<String, dynamic> _map(dynamic value) =>
      value is Map ? Map<String, dynamic>.from(value) : const {};

  @override
  Widget build(BuildContext context) {
    final parent = _map(data['parent']);
    final child = _map(data['child']);
    final plan = _map(data['plan']);
    final topics =
        (data['topics'] as List? ?? const []).whereType<Map>().toList();
    final limitations = (data['limitations'] as List? ?? const [])
        .map((item) => item.toString());
    final outcome = _map(data['outcome_comparison']);
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
          border: Border.all(color: Theme.of(context).dividerColor),
          borderRadius: BorderRadius.circular(6)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.compare_arrows_outlined),
          const SizedBox(width: 10),
          Expanded(
              child: Text('การเปลี่ยนแปลงเนื้อหา',
                  style: Theme.of(context).textTheme.titleLarge)),
        ]),
        const SizedBox(height: 8),
        const Text(
            'ตรวจจากข้อความถอดเสียงของสองไฟล์ ไม่ใช่คะแนนคุณภาพหรือคำรับประกันผลตอบรับ'),
        const Divider(height: 28),
        Wrap(spacing: 28, runSpacing: 12, children: [
          _VersionSummary(
              label: 'ฉบับต้นฉบับ',
              title: parent['title']?.toString() ?? '-',
              time: parent['created_at']?.toString() ?? '-'),
          _VersionSummary(
              label: 'ฉบับใหม่',
              title: child['title']?.toString() ?? '-',
              time: child['created_at']?.toString() ?? '-'),
        ]),
        const SizedBox(height: 12),
        Text('อ้างอิงแผนฉบับ ${plan['revision'] ?? '-'} · '
            '${plan['saved_at'] ?? 'ไม่พบเวลาบันทึก'}'),
        if (onOpenParent != null)
          Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                  onPressed: onOpenParent,
                  icon: const Icon(Icons.arrow_back),
                  label: const Text('เปิดผลวิเคราะห์ต้นฉบับ'))),
        const Divider(height: 28),
        if (data['status'] == 'no_topics_selected')
          const Text(
              'แผนนี้มีเฉพาะบันทึก จึงวิเคราะห์ฉบับใหม่ตามปกติโดยไม่มีหัวข้อให้เทียบอัตโนมัติ')
        else if (data['status'] == 'withheld_category')
          const Text(
              'งดสรุปการเปลี่ยนแปลง เพราะหมวดของฉบับใดฉบับหนึ่งไม่ผ่านเกณฑ์หรือสองฉบับอยู่คนละหมวด')
        else if (data['status'] == 'method_mismatch')
          const Text(
              'วิธีหรือข้อมูลของผลเก่าไม่พอสำหรับเทียบด้วยกติกาเดียวกัน กรุณาดูข้อความสองฉบับด้วยตนเอง')
        else
          for (final raw in topics) _TopicComparison(data: _map(raw)),
        const Divider(height: 28),
        _OutcomeRevisionComparison(data: outcome),
        if (limitations.isNotEmpty)
          ExpansionTile(
              tilePadding: EdgeInsets.zero,
              title: const Text('ข้อจำกัดที่ต้องทราบ'),
              children: [
                for (final item in limitations)
                  Align(
                      alignment: Alignment.centerLeft,
                      child: Padding(
                          padding: const EdgeInsets.only(bottom: 8),
                          child: Text('• $item'))),
              ]),
      ]),
    );
  }
}

class _VersionSummary extends StatelessWidget {
  const _VersionSummary(
      {required this.label, required this.title, required this.time});
  final String label, title, time;
  @override
  Widget build(BuildContext context) => SizedBox(
      width: 330,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label, style: Theme.of(context).textTheme.labelLarge),
        Text(title, maxLines: 2, overflow: TextOverflow.ellipsis),
        Text(time, style: Theme.of(context).textTheme.bodySmall),
      ]));
}

class _TopicComparison extends StatelessWidget {
  const _TopicComparison({required this.data});
  final Map<String, dynamic> data;
  Map<String, dynamic> _map(dynamic value) =>
      value is Map ? Map<String, dynamic>.from(value) : const {};

  @override
  Widget build(BuildContext context) {
    final before = _map(data['before']);
    final after = _map(data['after']);
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(data['title']?.toString() ?? '-',
            style: Theme.of(context).textTheme.titleMedium),
        Text(data['message']?.toString() ?? 'ข้อมูลยังไม่พอเปรียบเทียบ'),
        const SizedBox(height: 8),
        LayoutBuilder(builder: (context, constraints) {
          final width =
              constraints.maxWidth >= 744 ? 360.0 : constraints.maxWidth;
          return Wrap(spacing: 12, runSpacing: 12, children: [
            _EvidenceSide(label: 'ก่อนปรับ', data: before, width: width),
            _EvidenceSide(label: 'ฉบับใหม่', data: after, width: width),
          ]);
        }),
        const Divider(height: 28),
      ]),
    );
  }
}

class _EvidenceSide extends StatelessWidget {
  const _EvidenceSide(
      {required this.label, required this.data, required this.width});
  final String label;
  final Map<String, dynamic> data;
  final double width;

  String _status(String value) => switch (value) {
        'detected' => 'ตรวจพบหัวข้อ',
        'not_detected' => 'ยังไม่ตรวจพบในข้อความ',
        _ => 'ตรวจไม่ได้',
      };
  String _context(String value) => switch (value) {
        'context_present' => 'พบคำพร้อมบริบทใกล้เคียง',
        'keyword_only' => 'พบเพียงคำ ยังต้องดูคลิปยืนยัน',
        _ => 'บริบทยังไม่ชัดเจน',
      };

  @override
  Widget build(BuildContext context) {
    final contextData = data['context'] is Map
        ? Map<String, dynamic>.from(data['context'] as Map)
        : const <String, dynamic>{};
    final occurrences =
        (data['occurrences'] as List? ?? const []).whereType<Map>().toList();
    return Container(
      width: width,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surfaceContainerLow,
          borderRadius: BorderRadius.circular(6)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label, style: Theme.of(context).textTheme.labelLarge),
        Text(_status(data['status']?.toString() ?? 'unassessable')),
        Text(_context(contextData['status']?.toString() ?? 'unclear'),
            style: Theme.of(context).textTheme.bodySmall),
        for (final raw in occurrences.take(2)) _Quote(data: raw),
      ]),
    );
  }
}

class _OutcomeRevisionComparison extends StatelessWidget {
  const _OutcomeRevisionComparison({required this.data});
  final Map<String, dynamic> data;

  @override
  Widget build(BuildContext context) {
    final status = data['status']?.toString() ?? 'not_comparable';
    final before = (data['probability_before'] as num?)?.toDouble();
    final after = (data['probability_after'] as num?)?.toDouble();
    final delta = (data['delta_percentage_points'] as num?)?.toDouble();
    final comparable = status == 'comparable' &&
        before != null &&
        after != null &&
        delta != null;
    final reasons = outcomeStrings(data['reason_codes']).toSet();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        const Icon(Icons.query_stats_outlined),
        const SizedBox(width: 10),
        Expanded(
          child: Text('การเปลี่ยนแปลงค่าประเมินผลตอบรับ',
              style: Theme.of(context).textTheme.titleMedium),
        ),
      ]),
      const SizedBox(height: 8),
      if (!comparable) ...[
        const Text('เทียบค่าประเมินโดยตรงไม่ได้'),
        if (reasons.isNotEmpty)
          for (final reason in reasons)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text('• ${outcomeReasonMessage(reason)}'),
            ),
      ] else ...[
        Text(
          'ฉบับต้นฉบับ ${(before * 100).toStringAsFixed(1)}% · '
          'ฉบับใหม่ ${(after * 100).toStringAsFixed(1)}%',
        ),
        Text(
          'ส่วนต่างค่าประเมิน ${delta > 0 ? '+' : ''}${delta.toStringAsFixed(1)} จุดเปอร์เซ็นต์',
          key: const ValueKey('revision-outcome-delta'),
        ),
      ],
      const SizedBox(height: 6),
      Text(
        data['limitation']?.toString().isNotEmpty == true
            ? data['limitation'].toString()
            : 'เป็นการเปลี่ยนแปลงค่าประเมิน ไม่ใช่หลักฐานว่ายอดวิวจะเพิ่มหรือลด',
        style: Theme.of(context).textTheme.bodySmall,
      ),
    ]);
  }
}

class _Quote extends StatelessWidget {
  const _Quote({required this.data});
  final Map data;
  @override
  Widget build(BuildContext context) {
    final timestamp =
        data['timestamp'] is Map ? data['timestamp'] as Map : null;
    final start = (timestamp?['start_seconds'] as num?)?.toDouble();
    return Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Text(
            '${start == null ? '' : '${start.toStringAsFixed(1)} วินาที · '}“${data['quote'] ?? data['matched_text'] ?? ''}”',
            style: Theme.of(context).textTheme.bodySmall));
  }
}
