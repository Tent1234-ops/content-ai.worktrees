import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../models/actionable_recommendations.dart';
import 'recommendation_evidence_panel.dart';

class ActionableAdvicePanel extends StatelessWidget {
  const ActionableAdvicePanel(
      {super.key,
      required this.data,
      required this.bundle,
      this.selectedIds,
      this.onSelectionChanged,
      this.withheld = false});
  final ActionableRecommendations data;
  final Map<String, dynamic> bundle;
  final bool withheld;
  final Set<String>? selectedIds;
  final void Function(String, bool)? onSelectionChanged;

  Future<void> _copy(BuildContext context, String example) async {
    try {
      await Clipboard.setData(ClipboardData(text: example));
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('คัดลอกประโยคตัวอย่างแล้ว')));
      }
    } catch (_) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('คัดลอกไม่สำเร็จ กรุณาลองอีกครั้ง')));
      }
    }
  }

  String get _emptyMessage => switch (data.status) {
        'withheld_unknown' => 'ยังไม่ยืนยันหมวดหมู่ จึงงดคำแนะนำเฉพาะสินค้า',
        'withheld_input_unassessable' =>
          'ข้อความถอดเสียงยังไม่สมบูรณ์ จึงตรวจว่าควรเพิ่มหัวข้อใดไม่ได้',
        'unsupported_category' => 'ยังไม่มีแนวทางที่ตรวจแล้วสำหรับหมวดนี้',
        'insufficient_reference_evidence' =>
          'หลักฐานจากคลิปและช่องอ้างอิงยังไม่เพียงพอสำหรับสร้างข้อเสนอ',
        'insufficient_user_context' =>
          'เนื้อหาที่ตรวจพบยังไม่พอจะเชื่อมเป็นข้อเสนอที่เกี่ยวข้องกับคลิปนี้',
        'all_topics_detected' =>
          'ตรวจพบหัวข้อในชุดแนวทางนี้แล้ว จึงไม่มีข้อเสนอให้เพิ่มซ้ำ ไม่ใช่การรับรองว่าคลิปสมบูรณ์ทุกด้าน',
        _ =>
          'ยังไม่พบหัวข้อเพิ่มเติมที่เกี่ยวข้องและมีหลักฐานเพียงพอ จึงไม่ฝืนสร้างคำแนะนำ',
      };

  Future<void> _evidence(
          BuildContext context, ActionableAdvice item, Map topic) =>
      showDialog<void>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: Text('หลักฐาน: ${item.title}'),
          content: SizedBox(
              width: 820,
              child: SingleChildScrollView(
                  child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  for (final found in item.foundTopics)
                    TranscriptObservation(
                        title: 'สิ่งที่พบ: ${found['title']}',
                        observation: Map<String, dynamic>.from(
                            found['observation'] as Map? ?? const {})),
                  RecommendationEvidencePanel(expandTopics: true, bundle: {
                    ...bundle,
                    'topics': [topic],
                    'recommendations': const [],
                    'canonicalization': 'curated_synonyms',
                    'method_version': data.methodVersion,
                    'synonym_version': data.catalogHash,
                  }),
                  Text('แม่แบบ: ${data.templateVersion}'),
                ],
              ))),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(dialogContext),
                child: const Text('ปิด'))
          ],
        ),
      );

  @override
  Widget build(BuildContext context) {
    if (withheld) {
      return const Padding(
          padding: EdgeInsets.symmetric(vertical: 12),
          child: Text(
              'ยังไม่แสดงข้อเสนอจนกว่าหมวดหมู่และข้อความที่ใช้วิเคราะห์จะผ่านเกณฑ์'));
    }
    if (data.items.isEmpty) {
      return Padding(
          padding: const EdgeInsets.symmetric(vertical: 12),
          child: Text(_emptyMessage));
    }
    final topics = <String, Map>{
      for (final topic
          in (bundle['action_topics'] as List? ?? []).whereType<Map>())
        topic['topic_id'].toString(): topic
    };
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      for (final (index, item) in data.items.indexed) ...[
        if (index > 0) const Divider(height: 32),
        Semantics(
            header: true,
            child: Text('${index + 1}. ${item.title}',
                style: Theme.of(context).textTheme.titleMedium)),
        const SizedBox(height: 16),
        if (selectedIds != null)
          CheckboxListTile(
              key: ValueKey('select-advice-${item.id}'),
              contentPadding: EdgeInsets.zero,
              controlAffinity: ListTileControlAffinity.leading,
              title: const Text('เลือกนำไปปรับ'),
              value: selectedIds!.contains(item.id),
              onChanged: onSelectionChanged == null
                  ? null
                  : (value) => onSelectionChanged!(item.id, value ?? false)),
        _AdviceField(label: 'สิ่งที่พบ', text: item.finding),
        _AdviceField(label: 'สิ่งที่เสนอ', text: item.proposal),
        _AdviceField(label: 'เงื่อนไขก่อนทำ', text: item.condition),
        Text('วิธีเพิ่มเนื้อหา', style: Theme.of(context).textTheme.titleSmall),
        for (final (stepIndex, step) in item.steps.indexed)
          Padding(
              padding: const EdgeInsets.only(top: 6, bottom: 6),
              child: Text('${stepIndex + 1}. $step')),
        _AdviceField(label: 'ตัวอย่างประโยคก่อนทดสอบ', text: item.example),
        Align(
            alignment: Alignment.centerLeft,
            child: IconButton(
                key: ValueKey('copy-advice-${item.id}'),
                tooltip: 'คัดลอกประโยคตัวอย่าง',
                onPressed: item.example.isEmpty
                    ? null
                    : () => _copy(context, item.example),
                icon: const Icon(Icons.content_copy))),
        _AdviceField(
            label: 'เหตุผล', text: '${item.reason}\n${item.relevanceReason}'),
        Align(
            alignment: Alignment.centerLeft,
            child: OutlinedButton.icon(
              key: ValueKey('advice-evidence-${item.id}'),
              onPressed: topics[item.evidenceTopicId] == null
                  ? null
                  : () =>
                      _evidence(context, item, topics[item.evidenceTopicId]!),
              icon: const Icon(Icons.fact_check_outlined),
              label: const Text('ดูข้อความและคลิปอ้างอิง'),
            )),
      ],
      if (data.limitation.isNotEmpty)
        Padding(
            padding: const EdgeInsets.only(top: 20),
            child: Text(data.limitation,
                style: Theme.of(context).textTheme.bodySmall)),
    ]);
  }
}

class _AdviceField extends StatelessWidget {
  const _AdviceField({required this.label, required this.text});
  final String label, text;
  @override
  Widget build(BuildContext context) => Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(label, style: Theme.of(context).textTheme.titleSmall),
          const SizedBox(height: 4),
          SelectableText(text),
        ],
      ));
}
