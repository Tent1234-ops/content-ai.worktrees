import 'package:flutter/material.dart';
import 'workspace_widgets.dart';

class AnalysisProgress extends StatelessWidget {
  const AnalysisProgress({
    super.key,
    required this.stage,
    required this.observedStages,
    required this.message,
    this.revision = false,
  });
  final String stage;
  final Set<String> observedStages;
  final String message;
  final bool revision;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final steps = <String, String>{
      'uploading': 'ส่งไฟล์',
      'queued': 'รอคิว',
      'extracting_audio': 'แยกเสียง',
      if (!revision) 'transcribing': 'ถอดเสียง',
      if (!revision) 'normalizing_transcript': 'ปรับศัพท์',
      if (!revision) 'classifying': 'จำแนกหมวด',
      if (!revision) 'recommending': 'คำแนะนำ',
      'saving': 'บันทึกผล',
      'completed': 'เสร็จสิ้น',
    };
    return Semantics(
      liveRegion: true,
      label: message,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(message, style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(height: 12),
        const LinearProgressIndicator(),
        const SizedBox(height: 16),
        Wrap(spacing: 8, runSpacing: 8, children: [
          for (final step in steps.entries)
            StatusBadge(
              key: ValueKey('job-step-${step.key}'),
              label: step.value,
              icon: stage == step.key
                  ? Icons.radio_button_checked
                  : observedStages.contains(step.key)
                      ? Icons.check_circle_outline
                      : Icons.radio_button_unchecked,
              color:
                  stage == step.key ? colors.primary : colors.onSurfaceVariant,
            ),
        ]),
      ]),
    );
  }
}
