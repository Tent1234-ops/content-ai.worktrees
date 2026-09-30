import 'dart:async';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/current_trend_ideas.dart';

String trendIdeaTime(DateTime? date) {
  if (date == null) return 'ไม่พบเวลา';
  final value = date.toLocal();
  String two(int n) => n.toString().padLeft(2, '0');
  return '${two(value.day)}/${two(value.month)}/${value.year} ${two(value.hour)}:${two(value.minute)}';
}

class CurrentTrendIdeasPanel extends StatefulWidget {
  const CurrentTrendIdeasPanel({super.key, required this.data, this.now});
  final CurrentTrendIdeas data;
  final DateTime Function()? now;
  @override
  State<CurrentTrendIdeasPanel> createState() => _CurrentTrendIdeasPanelState();
}

class _CurrentTrendIdeasPanelState extends State<CurrentTrendIdeasPanel> {
  Timer? _timer;
  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 30), (_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final data = widget.data;
    final visible = data.validAt(widget.now?.call() ?? DateTime.now());
    final expired = data.items.isNotEmpty && visible.isEmpty;
    final message = expired
        ? 'ข้อมูลกระแสที่บันทึกไว้หมดอายุแล้ว จึงไม่แสดงเป็นไอเดียล่าสุด'
        : switch (data.status) {
            'not_evaluated' =>
              'ผลวิเคราะห์นี้ยังไม่ได้ตรวจไอเดียจากกระแสล่าสุด',
            'no_recent_sources' =>
              'ยังไม่มีข้อมูลเทรนด์ที่ใหม่พอและมีวันที่ยืนยัน',
            'insufficient_user_evidence' =>
              'เนื้อหาในคลิปยังไม่เพียงพอสำหรับเชื่อมกับกระแส',
            'unsupported_category' =>
              'ยังไม่มีไอเดียกระแสที่ยืนยันได้สำหรับหมวดนี้',
            'unavailable' =>
              'ข้อมูลเทรนด์ไม่พร้อมใช้งาน คำแนะนำจากคลิปอ้างอิงยังใช้ได้',
            _ => 'ยังไม่พบกระแสล่าสุดที่เกี่ยวข้องกับเนื้อหาในคลิปนี้',
          };
    return Semantics(
        container: true,
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            const Icon(Icons.trending_up, color: Color(0xFF15816E)),
            const SizedBox(width: 8),
            Expanded(
                child: Semantics(
                    header: true,
                    child: Text(
                        expired
                            ? 'ไอเดียกระแสที่บันทึกไว้'
                            : 'ไอเดียจากกระแสล่าสุด',
                        style: Theme.of(context).textTheme.titleMedium))),
          ]),
          const SizedBox(height: 8),
          if (data.generatedAt != null)
            Text('ตรวจข้อมูลเมื่อ ${trendIdeaTime(data.generatedAt)}',
                style: Theme.of(context).textTheme.bodySmall),
          if (visible.isEmpty)
            Padding(
                padding: const EdgeInsets.symmetric(vertical: 12),
                child: Text(message)),
          if (visible.isNotEmpty) ...[
            const Padding(
                padding: EdgeInsets.symmetric(vertical: 8),
                child: Text(
                    'พบในชื่อคลิป คำอธิบาย หรือคำค้น ไม่ใช่หลักฐานคำพูดใน Transcript และไม่รับประกันผลตอบรับ')),
            for (final idea in visible)
              Card(
                margin: const EdgeInsets.only(bottom: 12),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8),
                    side: const BorderSide(color: Color(0xFFDDE5E3))),
                child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(idea.topic,
                            style: Theme.of(context).textTheme.titleMedium),
                        const SizedBox(height: 6),
                        Text(idea.suggestion),
                        if (idea.userEvidence.isNotEmpty)
                          Padding(
                              padding: const EdgeInsets.only(top: 8),
                              child: Text(
                                  'เชื่อมกับสิ่งที่คุณพูด: ${idea.userEvidence.join(', ')}',
                                  style:
                                      Theme.of(context).textTheme.bodySmall)),
                        const SizedBox(height: 8),
                        Text('แหล่งสนับสนุน ${idea.supportCount} รายการ',
                            style: Theme.of(context).textTheme.labelMedium),
                        for (final source in idea.sources.take(3))
                          _SourceRow(source: source),
                        if (idea.sources.length > 3)
                          ExpansionTile(
                            title: Text(
                                'แหล่งเพิ่มเติม ${idea.sources.length - 3} รายการ'),
                            tilePadding: EdgeInsets.zero,
                            children: [
                              for (final source in idea.sources.skip(3))
                                _SourceRow(source: source)
                            ],
                          ),
                      ],
                    )),
              ),
          ],
        ]));
  }
}

class _SourceRow extends StatelessWidget {
  const _SourceRow({required this.source});
  final CurrentTrendSource source;

  Future<void> _open(BuildContext context) async {
    final uri = Uri.tryParse(source.url);
    final safe = uri != null &&
        uri.scheme == 'https' &&
        const {
          'www.youtube.com',
          'youtube.com',
          'youtu.be',
          'trends.google.com',
          'www.google.com',
          'google.com'
        }.contains(uri.host);
    var opened = false;
    if (safe) {
      try {
        opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
      } catch (_) {
        opened = false;
      }
    }
    if (!opened && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('เปิดแหล่งข้อมูลไม่สำเร็จ')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final label = switch (source.field) {
      'query' => 'คำค้น Google',
      'description' => 'คำอธิบาย YouTube',
      _ => 'ชื่อคลิป YouTube'
    };
    return Padding(
        padding: const EdgeInsets.only(top: 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Divider(height: 1),
            const SizedBox(height: 10),
            Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              if (source.platform == 'youtube' &&
                  source.thumbnailUrl.startsWith('https://')) ...[
                SizedBox(
                    width: 96,
                    height: 54,
                    child: ClipRRect(
                        borderRadius: BorderRadius.circular(4),
                        child: Image.network(source.thumbnailUrl,
                            fit: BoxFit.cover,
                            errorBuilder: (_, __, ___) =>
                                const Icon(Icons.ondemand_video_outlined)))),
                const SizedBox(width: 12),
              ],
              Expanded(
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                    Text(source.title,
                        maxLines: 3, overflow: TextOverflow.ellipsis),
                    Text(label, style: Theme.of(context).textTheme.labelSmall),
                  ])),
              IconButton(
                  onPressed: () => _open(context),
                  icon: const Icon(Icons.open_in_new),
                  tooltip: 'เปิดต้นทาง'),
            ]),
            const SizedBox(height: 6),
            Text('พบเมื่อ ${trendIdeaTime(source.observedAt)}',
                style: Theme.of(context).textTheme.bodySmall),
            Text(
                '${source.platform == 'youtube' ? 'เผยแพร่' : 'เวลาที่คำค้นเริ่มปรากฏในแหล่งข้อมูล'} ${trendIdeaTime(source.publishedAt)}',
                style: Theme.of(context).textTheme.bodySmall),
            Text(source.quote,
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.bodySmall),
            Text('รอบ #${source.runId} / รายการ #${source.itemId}',
                style: Theme.of(context).textTheme.labelSmall),
          ],
        ));
  }
}
