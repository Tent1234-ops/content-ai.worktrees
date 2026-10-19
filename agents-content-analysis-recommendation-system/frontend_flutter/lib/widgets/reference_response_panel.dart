import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/actionable_recommendations.dart';
import '../models/reference_response.dart';

String _number(int? value) => value == null
    ? 'ไม่มีข้อมูล'
    : value.toString().replaceAllMapped(
        RegExp(r'(\d)(?=(\d{3})+(?!\d))'), (match) => '${match[1]},');

String _date(DateTime? value, {bool time = false}) {
  if (value == null) return 'ไม่มีข้อมูล';
  final local = value.toLocal();
  final date = '${local.day}/${local.month}/${local.year}';
  return time
      ? '$date ${local.hour.toString().padLeft(2, '0')}:${local.minute.toString().padLeft(2, '0')} (เวลาท้องถิ่น)'
      : date;
}

class ReferenceResponsePanel extends StatelessWidget {
  const ReferenceResponsePanel({
    super.key,
    required this.bundle,
    required this.recommendedTopics,
    this.adviceByTopic = const {},
    this.withheld = false,
  });
  final Map<String, dynamic> bundle;
  final Map<String, String> recommendedTopics;
  final Map<String, ActionableAdvice> adviceByTopic;
  final bool withheld;

  @override
  Widget build(BuildContext context) {
    if (withheld) {
      return const Text(
          'ยังไม่แสดงคลิปอ้างอิง เพราะหมวดหรือข้อความถอดเสียงยังไม่พร้อม');
    }
    final topics =
        referenceResponses(bundle, recommendedTopics: recommendedTopics);
    if (topics.isEmpty) {
      return const Text(
          'ยังไม่มีหลักฐานผลตอบรับที่บันทึกไว้สำหรับประเด็นที่แนะนำ');
    }
    return Column(
      key: const ValueKey('reference-response-panel'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final (index, topic) in topics.indexed) ...[
          if (index > 0) const SizedBox(height: 24),
          Text(topic.title, style: Theme.of(context).textTheme.titleMedium),
          if (topic.groups.isEmpty)
            const Padding(
              padding: EdgeInsets.only(top: 8, bottom: 8),
              child: Text('ยังไม่มีสรุปสัดส่วนที่ตรวจสอบได้ในผลนี้ '
                  'ข้อมูลรูปแบบ อายุคลิป หรือกลุ่มอ้างอิงอาจไม่ครบ'),
            ),
          for (final group in topic.groups)
            _GroupResponse(
              group: group,
              topicTitle: topic.title,
              advice: adviceByTopic[topic.id],
            ),
          const SizedBox(height: 4),
          if (topic.groups.isNotEmpty) ...[
            Text('คลิปต้นแบบประกอบคำแนะนำ',
                style: Theme.of(context).textTheme.titleSmall),
            Text('เป็นอีกชุดข้อมูล ไม่ใช่ตัวหารของสัดส่วนด้านบน',
                style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 8),
          ],
          Text('หลักฐานที่เปิดดูได้ ${topic.clips.length} คลิป · '
              'ยืนยันช่องได้ ${topic.knownChannelCount} ช่อง'),
          if (topic.clips.isEmpty)
            const Padding(
              padding: EdgeInsets.only(top: 12),
              child: Text(
                  'ผลนี้ยังไม่มีหลักฐานต้นทางที่ตรวจสอบได้สำหรับประเด็นนี้'),
            ),
          for (final clip in topic.clips.take(2)) _ReferenceClip(clip: clip),
          if (topic.clips.length > 2)
            ExpansionTile(
              key: ValueKey('more-reference-responses-${topic.id}'),
              tilePadding: EdgeInsets.zero,
              title: Text('ดูคลิปอ้างอิงอีก ${topic.clips.length - 2} คลิป'),
              children: [
                for (final clip in topic.clips.skip(2))
                  _ReferenceClip(clip: clip),
              ],
            ),
        ],
      ],
    );
  }
}

Future<void> _openSource(BuildContext context, Uri url) async {
  try {
    if (await launchUrl(url, mode: LaunchMode.externalApplication)) return;
  } catch (_) {
    // Unsupported launchers and failed navigation share the same retry state.
  }
  if (context.mounted) {
    ScaffoldMessenger.of(context)
        .showSnackBar(const SnackBar(content: Text('เปิดคลิปต้นทางไม่สำเร็จ')));
  }
}

class _GroupResponse extends StatelessWidget {
  const _GroupResponse({
    required this.group,
    required this.topicTitle,
    this.advice,
  });
  final ReferenceResponseGroup group;
  final String topicTitle;
  final ActionableAdvice? advice;

  String get _summary {
    final proposal = advice?.proposal.trim() ?? '';
    final condition = advice?.condition.trim() ?? '';
    final suggestion = proposal.isEmpty
        ? 'หากเกี่ยวข้องกับสิ่งที่ทดสอบจริง ลองเพิ่มประเด็นนี้พร้อมตัวอย่างการใช้งาน'
        : 'ระบบเสนอให้ลอง$proposal';
    return 'ในกลุ่มคลิปอ้างอิงหมวด ${group.categoryLabel} '
        'ที่กล่าวถึง “$topicTitle” มีคลิปที่มียอดวิวสะสมมากกว่า '
        '${_number(group.thresholdViews)} ครั้ง ณ วันที่เก็บสถิติ '
        'จำนวน ${group.passingCount} จาก ${group.sampleSize} คลิป '
        'คิดเป็น ${group.percentage}% จากทั้งหมด ${group.channelCount} ช่อง '
        'สำหรับคลิปของคุณ $suggestion '
        '${condition.isEmpty ? '' : 'ทั้งนี้ $condition '}'
        'แล้วติดตามผลตอบรับหลังเผยแพร่';
  }

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 12),
        child: Text(
          _summary,
          style: Theme.of(context).textTheme.bodyLarge?.copyWith(height: 1.6),
        ),
      );
}

class _ReferenceClip extends StatelessWidget {
  const _ReferenceClip({required this.clip});
  final ReferenceResponseClip clip;

  Future<void> _open(BuildContext context) async {
    await _openSource(context, clip.sourceUrl);
  }

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Divider(height: 1),
            const SizedBox(height: 12),
            Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Expanded(
                child: Text(
                  clip.title.isEmpty ? 'คลิป ${clip.videoId}' : clip.title,
                  style: Theme.of(context).textTheme.titleSmall,
                ),
              ),
              IconButton(
                tooltip:
                    'เปิดคลิปต้นทาง ${clip.title.isEmpty ? clip.videoId : clip.title}',
                onPressed: () => _open(context),
                icon: const Icon(Icons.open_in_new),
              ),
            ]),
            Text(
                '${clip.channelTitle.isEmpty ? 'ไม่ทราบชื่อช่อง' : clip.channelTitle} · '
                'เผยแพร่ ${_date(clip.publishedAt)}'),
            const SizedBox(height: 12),
            Wrap(spacing: 24, runSpacing: 12, children: [
              _Metric(
                  label: 'ยอดวิว',
                  value: clip.views,
                  icon: Icons.visibility_outlined),
              _Metric(
                  label: 'ไลก์',
                  value: clip.likes,
                  icon: Icons.thumb_up_outlined),
              _Metric(
                  label: 'คอมเมนต์',
                  value: clip.comments,
                  icon: Icons.chat_bubble_outline),
            ]),
            const SizedBox(height: 10),
            Text(clip.capturedAt == null
                ? 'ยังไม่มีเวลาเก็บสถิติที่ยืนยันได้ จึงไม่แสดงตัวเลข'
                : 'สถิติสะสมที่บันทึกเมื่อ ${_date(clip.capturedAt, time: true)}'),
            if (clip.capturedAt != null && !clip.hasStatistics)
              const Text('ผลนี้ไม่ได้บันทึกตัวเลขสถิติที่ใช้ได้'),
            ExpansionTile(
              tilePadding: EdgeInsets.zero,
              title: const Text('ข้อความที่พบในคลิปอ้างอิง'),
              children: [
                Align(
                  alignment: Alignment.centerLeft,
                  child: Text(clip.quote),
                ),
                const SizedBox(height: 8),
                Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                      'Dataset #${clip.datasetId} · Video ID ${clip.videoId}',
                      style: Theme.of(context).textTheme.bodySmall),
                ),
                const SizedBox(height: 12),
              ],
            ),
          ],
        ),
      );
}

class _Metric extends StatelessWidget {
  const _Metric({required this.label, required this.value, required this.icon});
  final String label;
  final int? value;
  final IconData icon;

  @override
  Widget build(BuildContext context) =>
      Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(icon, size: 18, color: Theme.of(context).colorScheme.primary),
        const SizedBox(width: 8),
        Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(label, style: Theme.of(context).textTheme.bodySmall),
          Text(_number(value), style: Theme.of(context).textTheme.titleMedium),
        ]),
      ]);
}
