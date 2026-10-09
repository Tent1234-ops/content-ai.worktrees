import 'package:flutter/material.dart';

import '../models/outcome_prediction.dart';
import '../repositories/content_repository.dart';

class OutcomeAssessmentPanel extends StatefulWidget {
  const OutcomeAssessmentPanel({
    super.key,
    required this.assessment,
    required this.repository,
    required this.topicLabels,
    this.contentId,
    this.analysisId,
    this.assessmentFingerprint = '',
  });

  final OutcomeAssessment assessment;
  final ContentRepository repository;
  final Map<String, String> topicLabels;
  final int? contentId;
  final int? analysisId;
  final String assessmentFingerprint;

  @override
  State<OutcomeAssessmentPanel> createState() => _OutcomeAssessmentPanelState();
}

class _OutcomeAssessmentPanelState extends State<OutcomeAssessmentPanel> {
  final Set<String> _selected = {};
  OutcomeScenario? _scenario;
  String? _error;
  bool _loading = false;

  List<String> get _eligibleTopics => widget.assessment.evidenceTopicIds
      .where(widget.topicLabels.containsKey)
      .toList();

  bool get _canSimulate =>
      widget.assessment.isAvailable &&
      widget.contentId != null &&
      widget.analysisId != null &&
      RegExp(r'^[0-9a-f]{64}$').hasMatch(widget.assessmentFingerprint) &&
      _eligibleTopics.isNotEmpty;

  Future<void> _simulate() async {
    if (!_canSimulate || _selected.isEmpty || _loading) return;
    setState(() {
      _loading = true;
      _error = null;
      _scenario = null;
    });
    try {
      final result = await widget.repository.simulateOutcomeScenario(
        contentId: widget.contentId!,
        analysisId: widget.analysisId!,
        assessmentFingerprint: widget.assessmentFingerprint,
        selectedTopicIds: _selected.toList(),
      );
      if (mounted) setState(() => _scenario = result);
    } catch (error) {
      if (mounted) {
        setState(
            () => _error = 'จำลองสถานการณ์ไม่สำเร็จ: ${_readableError(error)}');
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  String _readableError(Object error) => error
      .toString()
      .replaceFirst(RegExp(r'^(Exception|Bad state|FormatException): '), '');

  @override
  Widget build(BuildContext context) {
    final assessment = widget.assessment;
    final probability = assessment.probability;
    final benchmark = outcomeMap(assessment.supportSummary['benchmark']);
    final contextData = assessment.context;
    final scenario = _scenario;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Text('ทำไมประเด็นนี้จึงน่าลองเพิ่ม',
          style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 8),
      if (!assessment.isAvailable) ...[
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(Icons.info_outline,
              color: Theme.of(context).colorScheme.onSurfaceVariant),
          const SizedBox(width: 10),
          Expanded(child: Text(outcomeStatusMessage(assessment.status))),
        ]),
        if (assessment.reasonCodes.isNotEmpty)
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            title: const Text('เหตุผลที่ยังประเมินไม่ได้'),
            children: [
              for (final reason in assessment.reasonCodes.toSet())
                Align(
                  alignment: Alignment.centerLeft,
                  child: Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Text('• ${outcomeReasonMessage(reason)}'),
                  ),
                ),
            ],
          ),
      ] else ...[
        if (assessment.fixtureOnly)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Text(
              'ข้อมูลทดสอบระบบเท่านั้น ไม่ใช่ผลจากโมเดลที่เปิดใช้จริง',
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ),
        Text(
          'โอกาสอยู่ในกลุ่มยอดวิวสูงกว่าค่ากลางของชุดอ้างอิง '
          '${(probability! * 100).toStringAsFixed(1)}%',
          key: const ValueKey('outcome-probability'),
          style: Theme.of(context).textTheme.titleLarge,
        ),
        const SizedBox(height: 8),
        Text(
          '${_categoryLabel(contextData['accepted_category']?.toString() ?? '')} · '
          '${outcomeFormatLabel(contextData['confirmed_format']?.toString() ?? '')} · '
          '${outcomeAgeLabel(contextData['frozen_age_context']?.toString() ?? '')}',
        ),
        if (_supportText(benchmark).isNotEmpty)
          Text(_supportText(benchmark),
              style: Theme.of(context).textTheme.bodySmall),
        const SizedBox(height: 8),
        const Text(
          'ค่านี้เปรียบเทียบกับกลุ่มอ้างอิงที่ระบุ ไม่ใช่เปอร์เซ็นต์ยอดวิวที่จะเพิ่ม '
          'และไม่รับประกันว่าการทำตามคำแนะนำจะทำให้คลิปดังขึ้น',
        ),
      ],
      if (assessment.limitations.isNotEmpty)
        ExpansionTile(
          tilePadding: EdgeInsets.zero,
          title: const Text('วิธีประเมินและข้อจำกัด'),
          children: [
            for (final limitation in assessment.limitations)
              Align(
                alignment: Alignment.centerLeft,
                child: Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Text('• $limitation'),
                ),
              ),
            if (assessment.modelVersion.isNotEmpty)
              Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  'โมเดล ${assessment.modelVersion} · '
                  'เป้าหมาย ${assessment.targetVersion}',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
          ],
        ),
      const Divider(height: 28),
      Text('ลองจำลองหัวข้อที่เลือก',
          style: Theme.of(context).textTheme.titleSmall),
      const SizedBox(height: 4),
      const Text(
        'สถานการณ์สมมุติจะเปลี่ยนเฉพาะหัวข้อในสำเนาข้อมูล '
        'ไม่ได้แก้ Transcript และไม่ถือว่าผู้ใช้เพิ่มเนื้อหาแล้ว',
      ),
      const SizedBox(height: 8),
      if (!_canSimulate)
        Text(_scenarioUnavailableMessage(assessment))
      else ...[
        for (final topicId in _eligibleTopics)
          CheckboxListTile(
            key: ValueKey('outcome-topic-$topicId'),
            contentPadding: EdgeInsets.zero,
            controlAffinity: ListTileControlAffinity.leading,
            value: _selected.contains(topicId),
            title: Text(widget.topicLabels[topicId]!),
            onChanged: _loading
                ? null
                : (selected) {
                    setState(() {
                      _scenario = null;
                      if (selected == true && _selected.length < 3) {
                        _selected.add(topicId);
                      } else if (selected != true) {
                        _selected.remove(topicId);
                      }
                    });
                  },
          ),
        Align(
          alignment: Alignment.centerLeft,
          child: OutlinedButton.icon(
            key: const ValueKey('simulate-outcome'),
            onPressed: _selected.isEmpty || _loading ? null : _simulate,
            icon: _loading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.science_outlined),
            label: Text(_loading
                ? 'กำลังประเมินสถานการณ์...'
                : 'ประเมินสถานการณ์สมมุติ'),
          ),
        ),
      ],
      if (_error != null)
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text(_error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error)),
        ),
      if (scenario != null)
        Padding(
          padding: const EdgeInsets.only(top: 12),
          child: scenario.isAvailable
              ? _ScenarioResult(data: scenario)
              : Text(outcomeStatusMessage(scenario.status)),
        ),
    ]);
  }

  String _scenarioUnavailableMessage(OutcomeAssessment assessment) {
    if (!assessment.isAvailable) {
      return 'ยังจำลองไม่ได้ เพราะผลนี้ไม่มีค่าประเมินที่ผ่านเกณฑ์';
    }
    if (widget.contentId == null || widget.analysisId == null) {
      return 'บันทึกผลวิเคราะห์ก่อนจึงจะจำลองจาก Snapshot เดิมได้';
    }
    if (_eligibleTopics.isEmpty) {
      return 'ยังไม่มีหัวข้อที่มีหลักฐานทั้งกลุ่มพูดถึงและไม่พูดถึงเพียงพอ';
    }
    return 'โหลดผลที่บันทึกอีกครั้งเพื่อยืนยันรุ่นของค่าประเมิน';
  }

  String _supportText(Map<String, dynamic> benchmark) {
    final videos = _firstInt(benchmark, const [
      'independent_videos',
      'video_count',
      'sample_count',
      'fit_video_count'
    ]);
    final channels = _firstInt(
        benchmark, const ['channels', 'channel_count', 'fit_channel_count']);
    if (videos == null && channels == null) return '';
    return [
      if (videos != null) '$videos คลิปอิสระ',
      if (channels != null) '$channels ช่อง',
    ].join(' · ');
  }

  int? _firstInt(Map<String, dynamic> data, List<String> keys) {
    for (final key in keys) {
      final value = data[key];
      if (value is num) return value.toInt();
    }
    return null;
  }

  String _categoryLabel(String value) => switch (value) {
        'phone' => 'โทรศัพท์',
        'camera' => 'กล้อง',
        'laptop' => 'แล็ปท็อป',
        _ => value.isEmpty ? 'ไม่ระบุหมวด' : value,
      };
}

class _ScenarioResult extends StatelessWidget {
  const _ScenarioResult({required this.data});
  final OutcomeScenario data;

  @override
  Widget build(BuildContext context) {
    final delta = data.deltaPercentagePoints!;
    final signed =
        delta > 0 ? '+${delta.toStringAsFixed(1)}' : delta.toStringAsFixed(1);
    return Semantics(
      container: true,
      explicitChildNodes: true,
      label: 'ผลสถานการณ์สมมุติ',
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('สถานการณ์สมมุติ', style: Theme.of(context).textTheme.labelLarge),
        Text(
          'ค่าประเมินก่อน ${(data.probabilityBefore! * 100).toStringAsFixed(1)}% · '
          'หลังจำลอง ${(data.probabilityAfter! * 100).toStringAsFixed(1)}%',
        ),
        Text('ส่วนต่างค่าประเมิน $signed จุดเปอร์เซ็นต์',
            key: const ValueKey('outcome-scenario-delta')),
        Text(
          data.limitation.isEmpty
              ? 'ไม่ใช่เปอร์เซ็นต์ยอดวิวเพิ่มหรือหลักฐานเชิงเหตุและผล'
              : data.limitation,
          style: Theme.of(context).textTheme.bodySmall,
        ),
      ]),
    );
  }
}
