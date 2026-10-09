import 'dart:async';

import 'package:flutter/material.dart';

import '../models/outcome_model_training.dart';
import '../models/outcome_prediction.dart';
import '../repositories/admin_repository.dart';
import 'state_widgets.dart';

class OutcomeTrainingPanel extends StatefulWidget {
  const OutcomeTrainingPanel({super.key, required this.repository});
  final AdminRepository repository;

  @override
  State<OutcomeTrainingPanel> createState() => _OutcomeTrainingPanelState();
}

class _OutcomeTrainingPanelState extends State<OutcomeTrainingPanel> {
  OutcomeTrainingOverview? _data;
  OutcomeTrainingRun? _run;
  Timer? _timer;
  String? _error;
  bool _loading = true;
  bool _busy = false;
  bool _polling = false;

  @override
  void initState() {
    super.initState();
    _load();
    _timer = Timer.periodic(const Duration(seconds: 5), (_) => _poll());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final data = await widget.repository.outcomeTrainingOverview();
      if (!mounted) return;
      setState(() {
        _data = data;
        _run = data.runs.isEmpty ? null : data.runs.first;
        _error = null;
      });
    } catch (error) {
      if (mounted) setState(() => _error = _message(error));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _poll() async {
    final run = _run;
    if (run == null || !run.isRunning || _polling || _busy) return;
    _polling = true;
    try {
      final updated = await widget.repository.outcomeTrainingRun(run.id);
      if (!mounted) return;
      setState(() {
        _run = updated;
        _error = null;
      });
      if (!updated.isRunning) await _load();
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'โหลดสถานะงาน Outcome ไม่สำเร็จ ระบบจะลองใหม่');
      }
    } finally {
      _polling = false;
    }
  }

  Future<void> _start() async {
    final data = _data;
    final manifest = data?.preflight['manifest_sha256']?.toString() ?? '';
    if (data == null ||
        data.preflight['ready'] != true ||
        manifest.length != 64 ||
        _busy ||
        _run?.isRunning == true) {
      return;
    }
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('เริ่มเทรนโมเดลประเมินผลตอบรับ?'),
        content: const Text(
          'ระบบจะใช้ Frozen manifest ที่ผ่าน Preflight และทำงานเบื้องหลัง '
          'Independent Test จะยังไม่ถูกเปิด และโมเดลที่ใช้งานอยู่จะไม่เปลี่ยน',
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('ยกเลิก')),
          FilledButton.icon(
            onPressed: () => Navigator.pop(context, true),
            icon: const Icon(Icons.play_arrow),
            label: const Text('ยืนยันเริ่มเทรน'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final run = await widget.repository.startOutcomeTraining(manifest);
      if (mounted) setState(() => _run = run);
    } catch (error) {
      await _load();
      if (mounted) setState(() => _error = _message(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _activate(OutcomeModelSummary model) async {
    if (_busy || !model.canActivate) return;
    final active = _data?.activeModel;
    final rollback = active != null && model.id < active.id;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(rollback
            ? 'ย้อนกลับไปใช้โมเดล Outcome รุ่นนี้?'
            : 'เปิดใช้โมเดล Outcome รุ่นนี้?'),
        content: Text(
          '${active == null ? 'ยังไม่มีโมเดลที่ใช้งาน' : 'ปัจจุบัน #${active.id} ${active.version}'}\n'
          'เปลี่ยนเป็น #${model.id} ${model.version}\n\n'
          'มีผลเฉพาะงานวิเคราะห์ใหม่ ผลเก่าจะอ่าน Snapshot เดิม',
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('ยกเลิก')),
          FilledButton.icon(
            onPressed: () => Navigator.pop(context, true),
            icon: Icon(rollback ? Icons.history : Icons.check_circle_outline),
            label: Text(rollback ? 'ยืนยันย้อนกลับ' : 'ยืนยันเปิดใช้'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.repository.activateOutcomeModel(model.id, active?.id);
      await _load();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text(rollback
                ? 'ย้อนกลับไปใช้ Outcome model #${model.id} แล้ว'
                : 'เปิดใช้ Outcome model #${model.id} แล้ว')));
      }
    } catch (error) {
      await _load();
      if (mounted) setState(() => _error = _message(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  String _message(Object error) => error
      .toString()
      .replaceFirst(RegExp(r'^(Exception|Bad state|FormatException): '), '');

  @override
  Widget build(BuildContext context) {
    final data = _data;
    if (_loading && data == null) {
      return const Center(child: CircularProgressIndicator());
    }
    if (data == null) {
      return ErrorStateView(
          message: _error ?? 'โหลดข้อมูล Outcome ไม่สำเร็จ', onRetry: _load);
    }
    final preflight = data.preflight;
    final ready = preflight['ready'] == true;
    final reasons = outcomeStrings(preflight['reason_codes']);
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Wrap(
        alignment: WrapAlignment.spaceBetween,
        crossAxisAlignment: WrapCrossAlignment.center,
        spacing: 16,
        runSpacing: 12,
        children: [
          Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('โมเดลประเมินผลตอบรับ',
                style: Theme.of(context).textTheme.titleLarge),
            Text(
              data.activeModel == null
                  ? 'ยังไม่มี Outcome model ที่เปิดใช้งาน'
                  : 'กำลังใช้ #${data.activeModel!.id} ${data.activeModel!.version}',
            ),
          ]),
          IconButton(
            tooltip: 'โหลดสถานะ Outcome ล่าสุด',
            onPressed: _busy ? null : _load,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      const SizedBox(height: 8),
      const Text(
        'โมเดลนี้แยกจากโมเดลจำแนก Phone/Camera/Laptop และประเมินโอกาสเทียบ '
        'ค่ากลางของชุดอ้างอิง ไม่ได้ทำนายจำนวนวิวหรือผลจากการทำตามคำแนะนำ',
      ),
      if (_error != null)
        Padding(
          padding: const EdgeInsets.only(top: 12),
          child: Text(_error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error)),
        ),
      const Divider(height: 36),
      Wrap(
        alignment: WrapAlignment.spaceBetween,
        crossAxisAlignment: WrapCrossAlignment.center,
        spacing: 16,
        runSpacing: 12,
        children: [
          Text('ความพร้อมก่อนเทรน',
              style: Theme.of(context).textTheme.titleMedium),
          FilledButton.icon(
            key: const ValueKey('start-outcome-training'),
            onPressed:
                ready && !_busy && _run?.isRunning != true ? _start : null,
            icon: const Icon(Icons.play_arrow),
            label: const Text('เริ่มเทรน Outcome'),
          ),
        ],
      ),
      const SizedBox(height: 12),
      Text(ready
          ? 'ข้อมูลและสิทธิ์ผ่าน Preflight สำหรับเริ่มงานเบื้องหลัง'
          : 'ยังเริ่มเทรนไม่ได้'),
      for (final reason in reasons.toSet())
        Padding(
          padding: const EdgeInsets.only(top: 6),
          child: Text('• ${outcomeAdminReason(reason)}'),
        ),
      _ReadinessCounts(preflight: preflight),
      const Divider(height: 36),
      Text('รอบเทรน', style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 10),
      if (_run == null)
        const Text('ยังไม่มีรอบเทรน Outcome จากหน้าเว็บ')
      else
        _OutcomeRunSummary(run: _run!),
      if (data.runs.length > 1)
        ExpansionTile(
          tilePadding: EdgeInsets.zero,
          title: const Text('ประวัติรอบก่อนหน้า'),
          children: [
            for (final run in data.runs.where((item) => item.id != _run?.id))
              Padding(
                padding: const EdgeInsets.only(bottom: 18),
                child: _OutcomeRunSummary(run: run),
              ),
          ],
        ),
      const Divider(height: 36),
      Text('โมเดลที่บันทึกไว้ (${data.totalModels})',
          style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 10),
      if (data.models.isEmpty)
        const Text('ยังไม่มี Outcome model จากข้อมูลจริงที่บันทึกไว้')
      else
        for (final model in data.models)
          _OutcomeModelRow(
            model: model,
            activeModelId: data.activeModel?.id,
            busy: _busy,
            onActivate: () => _activate(model),
            onDetails: () => showDialog<void>(
              context: context,
              builder: (context) => _OutcomeModelDetails(
                modelId: model.id,
                repository: widget.repository,
              ),
            ),
          ),
    ]);
  }
}

class _ReadinessCounts extends StatelessWidget {
  const _ReadinessCounts({required this.preflight});
  final Map<String, dynamic> preflight;

  @override
  Widget build(BuildContext context) {
    final counts = outcomeMap(preflight['counts']);
    final latest = outcomeMap(preflight['latest_phase2_report']);
    if (counts.isEmpty && latest.isEmpty) {
      return const Padding(
        padding: EdgeInsets.only(top: 8),
        child: Text('ยังไม่มี Manifest ที่ใช้สรุปจำนวนวิดีโอและช่องต่อชุดได้'),
      );
    }
    if (counts.isEmpty) {
      return Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Text(
          'แถวต้นทาง ${latest['active_source_rows'] ?? '-'} · '
          'แถวผ่านโครงสร้าง ${latest['structurally_eligible_rows'] ?? '-'} · '
          'แถวที่อนุญาตให้ฝึก ${latest['training_allowed_rows'] ?? '-'}\n'
          'จำนวนแถวต้นทางไม่ใช่จำนวนวิดีโออิสระหรือจำนวนช่องที่พร้อมฝึก',
        ),
      );
    }
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: DataTable(
          columns: const [
            DataColumn(label: Text('ชุดข้อมูล')),
            DataColumn(label: Text('วิดีโออิสระ')),
            DataColumn(label: Text('ช่องอิสระ')),
          ],
          rows: [
            for (final role in const [
              'fit',
              'tuning',
              'calibration',
              'independent_test'
            ])
              DataRow(cells: [
                DataCell(Text(outcomeSplitLabel(role))),
                DataCell(Text('${outcomeMap(counts[role])['videos'] ?? '-'}')),
                DataCell(
                    Text('${outcomeMap(counts[role])['channels'] ?? '-'}')),
              ]),
          ],
        ),
      ),
    );
  }
}

class _OutcomeRunSummary extends StatelessWidget {
  const _OutcomeRunSummary({required this.run});
  final OutcomeTrainingRun run;

  @override
  Widget build(BuildContext context) =>
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(outcomeTrainingStatus(run.status)),
        SelectableText('รหัสรอบ: ${run.id}'),
        if (run.isRunning) ...[
          const SizedBox(height: 8),
          LinearProgressIndicator(value: run.progress.clamp(0, 1)),
          const SizedBox(height: 6),
          Text('${outcomeTrainingStatus(run.stage)} · '
              '${(run.progress * 100).clamp(0, 100).toStringAsFixed(0)}%'),
        ],
        if (run.error?.isNotEmpty == true)
          Text(run.error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error)),
        if (run.status == 'completed')
          const Text(
              'บันทึก Candidate แล้ว แต่ยังไม่เปิดใช้จนกว่าจะผ่าน Independent Test และมีการยืนยันแยกต่างหาก'),
      ]);
}

class _OutcomeModelRow extends StatelessWidget {
  const _OutcomeModelRow({
    required this.model,
    required this.activeModelId,
    required this.busy,
    required this.onActivate,
    required this.onDetails,
  });
  final OutcomeModelSummary model;
  final int? activeModelId;
  final bool busy;
  final VoidCallback onActivate;
  final VoidCallback onDetails;

  @override
  Widget build(BuildContext context) {
    final rollback = activeModelId != null && model.id < activeModelId!;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 0, vertical: 6),
        leading: Icon(model.isActive
            ? Icons.check_circle_outline
            : Icons.query_stats_outlined),
        title: Text('#${model.id} ${model.version}',
            maxLines: 2, overflow: TextOverflow.ellipsis),
        subtitle: Text(
          '${outcomeTrainingStatus(model.status)} · '
          '${model.trainingSampleCount} ตัวอย่างฝึก/ปรับค่า\n'
          'Validation: ${model.status == 'validation_passed' || model.status == 'qualified' ? 'มีผล' : 'ยังไม่ผ่าน'} · '
          'Independent Test: ${model.independentTestPassed ? 'ผ่าน' : 'ยังไม่ผ่าน'}',
        ),
        trailing: Row(mainAxisSize: MainAxisSize.min, children: [
          IconButton(
            tooltip: 'ดูผลประเมิน Outcome #${model.id}',
            onPressed: onDetails,
            icon: const Icon(Icons.analytics_outlined),
          ),
          IconButton(
            tooltip: model.canActivate
                ? (rollback
                    ? 'ย้อนกลับไปใช้ Outcome #${model.id}'
                    : 'เปิดใช้ Outcome #${model.id}')
                : 'ยังเปิดใช้ Outcome #${model.id} ไม่ได้',
            onPressed: model.canActivate && !busy ? onActivate : null,
            icon: Icon(rollback ? Icons.history : Icons.play_circle_outline),
          ),
        ]),
      ),
    );
  }
}

class _OutcomeModelDetails extends StatefulWidget {
  const _OutcomeModelDetails({required this.modelId, required this.repository});
  final int modelId;
  final AdminRepository repository;

  @override
  State<_OutcomeModelDetails> createState() => _OutcomeModelDetailsState();
}

class _OutcomeModelDetailsState extends State<_OutcomeModelDetails> {
  late Future<OutcomeModelSummary> _future;

  @override
  void initState() {
    super.initState();
    _future = widget.repository.outcomeModel(widget.modelId);
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text('ผลประเมิน Outcome model #${widget.modelId}'),
        content: SizedBox(
          width: 820,
          child: FutureBuilder<OutcomeModelSummary>(
            future: _future,
            builder: (context, snapshot) {
              if (snapshot.hasError) {
                return ErrorStateView(
                  message: snapshot.error.toString(),
                  onRetry: () => setState(() =>
                      _future = widget.repository.outcomeModel(widget.modelId)),
                );
              }
              if (!snapshot.hasData) {
                return const SizedBox(
                    height: 140,
                    child: Center(child: CircularProgressIndicator()));
              }
              return _OutcomeMetrics(model: snapshot.data!);
            },
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('ปิด')),
        ],
      );
}

class _OutcomeMetrics extends StatelessWidget {
  const _OutcomeMetrics({required this.model});
  final OutcomeModelSummary model;

  Map<String, dynamic> _evaluation(String modelKey, String phase) {
    final tuning = outcomeMap(model.metrics['tuning']);
    final selected = outcomeMap(tuning[modelKey]);
    final stage = outcomeMap(selected[phase]);
    return outcomeMap(outcomeMap(stage['overall'])['channel_balanced']);
  }

  String _score(dynamic value) =>
      value is num ? value.toDouble().toStringAsFixed(4) : 'ไม่มีข้อมูล';

  @override
  Widget build(BuildContext context) {
    final constant = _evaluation('constant_prior', 'after');
    final metadata = _evaluation('metadata_logistic_regression', 'after');
    final candidate =
        _evaluation('metadata_topics_logistic_regression', 'after');
    final calibration = outcomeMap(outcomeMap(outcomeMap(
        outcomeMap(model.metrics['calibration'])[
            'metadata_topics_logistic_regression'])['after'])['calibration']);
    final partitionCounts = outcomeMap(model.metrics['partition_counts']);
    final test = outcomeMap(model.metrics['independent_test']);
    return SingleChildScrollView(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(model.version, style: Theme.of(context).textTheme.titleMedium),
        Text('เป้าหมาย: ${model.targetVersion}'),
        Text('สถานะ: ${outcomeTrainingStatus(model.status)}'),
        if (model.sourceKind != 'real')
          Text('ข้อมูลทดสอบเท่านั้น (${model.sourceKind})',
              style: TextStyle(color: Theme.of(context).colorScheme.error)),
        const Divider(height: 28),
        Text('Validation / Tuning',
            style: Theme.of(context).textTheme.titleSmall),
        const Text('Brier score ยิ่งต่ำยิ่งดี และต้องเทียบกับ Baseline'),
        _MetricLine(
            label: 'Constant baseline', value: _score(constant['brier_score'])),
        _MetricLine(
            label: 'Metadata baseline', value: _score(metadata['brier_score'])),
        _MetricLine(
            label: 'Metadata + topics',
            value: _score(candidate['brier_score'])),
        const SizedBox(height: 12),
        Text('Calibration', style: Theme.of(context).textTheme.titleSmall),
        Text(calibration.isEmpty
            ? 'ยังไม่มีผล Calibration'
            : '${calibration['passed'] == true ? 'ผ่านเกณฑ์ Validation' : 'ยังไม่ผ่าน'} · '
                'ช่องว่างสูงสุด ${_score(calibration['maximum_observed_gap'])} · '
                '${calibration['actual_bins'] ?? '-'} ช่วง'),
        const SizedBox(height: 12),
        Text('Independent Test', style: Theme.of(context).textTheme.titleSmall),
        Text(model.independentTestPassed
            ? 'ผ่าน Independent Test ตามขอบเขตที่บันทึกไว้'
            : test['status'] == 'sealed_until_phase_6_evaluation' ||
                    test.isEmpty
                ? 'ยังไม่เปิดผล Independent Test'
                : 'Independent Test ยังไม่ผ่าน'),
        if (partitionCounts.isNotEmpty) ...[
          const SizedBox(height: 12),
          Text('จำนวนข้อมูลต่อชุด',
              style: Theme.of(context).textTheme.titleSmall),
          for (final role in const [
            'fit',
            'tuning',
            'calibration',
            'independent_test'
          ])
            Text('${outcomeSplitLabel(role)}: '
                '${outcomeMap(partitionCounts[role])['videos'] ?? '-'} วิดีโอ · '
                '${outcomeMap(partitionCounts[role])['channels'] ?? '-'} ช่อง'),
        ],
        if (model.activationReasonCodes.isNotEmpty) ...[
          const Divider(height: 28),
          Text('เหตุผลที่ยังเปิดใช้ไม่ได้',
              style: Theme.of(context).textTheme.titleSmall),
          for (final reason in model.activationReasonCodes.toSet())
            Text('• ${outcomeAdminReason(reason)}'),
        ],
        const Divider(height: 28),
        SelectableText('Protocol: ${model.protocolSha256}'),
        SelectableText('Feature schema: ${model.featureSchemaSha256}'),
        SelectableText('Dataset manifest: ${model.manifestSha256}'),
      ]),
    );
  }
}

class _MetricLine extends StatelessWidget {
  const _MetricLine({required this.label, required this.value});
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: 4),
        child: Row(children: [
          Expanded(child: Text(label)),
          Text(value),
        ]),
      );
}
