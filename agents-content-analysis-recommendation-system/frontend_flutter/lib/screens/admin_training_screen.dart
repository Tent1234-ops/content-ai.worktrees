import 'dart:async';
import 'package:flutter/material.dart';
import '../widgets/classification_readiness_panel.dart';

import '../models/model_training.dart';
import '../repositories/admin_repository.dart';
import '../widgets/app_shell.dart';
import '../widgets/state_widgets.dart';
import '../widgets/training_collection_panel.dart';

class AdminTrainingScreen extends StatefulWidget {
  const AdminTrainingScreen({super.key, this.repository});
  final AdminRepository? repository;
  @override
  State<AdminTrainingScreen> createState() => _AdminTrainingScreenState();
}

class _AdminTrainingScreenState extends State<AdminTrainingScreen>
    with SingleTickerProviderStateMixin {
  late final AdminRepository _repository;
  late final TabController _tabs;
  Timer? _timer;
  TrainingOverview? _data;
  TrainingRun? _run;
  List<TrainedModel> _models = [];
  bool _loading = true, _busy = false, _polling = false, _moreLoading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? AdminRepository();
    _tabs = TabController(length: 2, vsync: this);
    _load();
    _timer = Timer.periodic(const Duration(seconds: 5), (_) => _poll());
  }

  @override
  void dispose() {
    _timer?.cancel();
    _tabs.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final data = await _repository.trainingOverview();
      if (!mounted) return;
      setState(() {
        _data = data;
        _models = data.models;
        _run = data.runs.isEmpty ? null : data.runs.first;
        _error = null;
      });
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _poll() async {
    final current = _run;
    if (_polling || _busy || current == null || !current.isRunning) return;
    _polling = true;
    try {
      final updated = await _repository.trainingRun(current.id);
      if (!mounted) return;
      setState(() {
        _run = updated;
        _error = null;
      });
      if (!updated.isRunning) {
        await _load();
        if (mounted && updated.status == 'completed') _tabs.animateTo(1);
      }
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'โหลดสถานะล่าสุดไม่สำเร็จ ระบบจะตรวจซ้ำ');
      }
    } finally {
      _polling = false;
    }
  }

  Future<void> _train() async {
    final data = _data;
    if (data == null || _busy || _run?.isRunning == true) return;
    final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
              title: const Text('เริ่มเทรนโมเดลรอบใหม่?'),
              content: Text(
                  'ข้อมูลที่ผ่านการตรวจสอบ ${data.dataset['sample_count']} รายการ\nโมเดลที่ใช้งานอยู่จะยังไม่ถูกเปลี่ยน'),
              actions: [
                TextButton(
                    onPressed: () => Navigator.pop(context, false),
                    child: const Text('ยกเลิก')),
                FilledButton.icon(
                    onPressed: () => Navigator.pop(context, true),
                    icon: const Icon(Icons.play_arrow),
                    label: const Text('ยืนยันเริ่มเทรน'))
              ],
            ));
    if (confirmed != true || !mounted) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final run = await _repository
          .startTraining(data.dataset['dataset_fingerprint'] as String);
      if (mounted) setState(() => _run = run);
    } catch (e) {
      await _load();
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _activate(TrainedModel model) async {
    if (_busy) return;
    final activeId = _data?.activeModel?.id;
    final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
              title: const Text('เปลี่ยนโมเดลที่ใช้งาน?'),
              content: Text(
                  'จาก ${activeId == null ? 'ยังไม่มีโมเดล' : '#$activeId'} เป็น #${model.id} ${trainingModelName(model.key)}\nมีผลกับงานวิเคราะห์ใหม่หลังเปิดใช้งาน'),
              actions: [
                TextButton(
                    onPressed: () => Navigator.pop(context, false),
                    child: const Text('ยกเลิก')),
                FilledButton.icon(
                    onPressed: () => Navigator.pop(context, true),
                    icon: const Icon(Icons.check_circle_outline),
                    label: const Text('ยืนยันเปิดใช้'))
              ],
            ));
    if (confirmed != true || !mounted) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await _repository.activateTrainingModel(model.id, activeId);
      await _load();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('เปิดใช้โมเดล #${model.id} แล้ว')));
      }
    } catch (e) {
      await _load();
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _details(TrainedModel model) async {
    await showDialog<void>(
        context: context,
        builder: (context) =>
            _ModelDetails(id: model.id, repository: _repository));
  }

  Future<void> _more() async {
    setState(() => _moreLoading = true);
    try {
      final next = await _repository.trainingModels(offset: _models.length);
      if (mounted) {
        setState(() {
          final ids = _models.map((m) => m.id).toSet();
          _models.addAll(next.items.where((m) => !ids.contains(m.id)));
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _moreLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final data = _data;
    final active = data?.activeModel;
    return AppShell(
      title: 'เทรนโมเดล AI',
      currentRoute: '/admin-training',
      isAdmin: true,
      actions: [
        IconButton(
            tooltip: 'โหลดข้อมูลล่าสุด',
            onPressed: _busy || _loading ? null : _load,
            icon: const Icon(Icons.refresh))
      ],
      child: _loading
          ? const Center(child: CircularProgressIndicator())
          : data == null
              ? ErrorStateView(
                  message: _error ?? 'โหลดข้อมูลไม่สำเร็จ', onRetry: _load)
              : SingleChildScrollView(
                  padding: const EdgeInsets.all(24),
                  child: Center(
                      child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 1280),
                    child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Text('โมเดลที่ใช้งานอยู่',
                              style: Theme.of(context).textTheme.titleMedium),
                          const SizedBox(height: 8),
                          Text(
                              active == null
                                  ? 'ยังไม่มีโมเดลที่เปิดใช้งาน'
                                  : '#${active.id} ${trainingModelName(active.key)}',
                              style: Theme.of(context).textTheme.titleLarge),
                          if (active != null)
                            Text(
                                'รุ่น ${active.version} · เกณฑ์ Unknown ${trainingPercent(active.unknownThreshold)}'),
                          if (active != null)
                            ClassificationReadinessPanel(
                                readiness: active.readiness),
                          const SizedBox(height: 16),
                          if (_error != null)
                            Padding(
                                padding: const EdgeInsets.only(bottom: 16),
                                child: Text(_error!,
                                    style: TextStyle(
                                        color: Theme.of(context)
                                            .colorScheme
                                            .error))),
                          TabBar(
                              controller: _tabs,
                              onTap: (_) => setState(() {}),
                              tabs: const [
                                Tab(text: 'ข้อมูลและรอบเทรน'),
                                Tab(text: 'เปรียบเทียบโมเดล')
                              ]),
                          const SizedBox(height: 24),
                          AnimatedBuilder(
                              animation: _tabs,
                              builder: (context, _) => _tabs.index == 0
                                  ? _dataAndRuns(data)
                                  : _modelList(data)),
                        ]),
                  ))),
    );
  }

  Widget _dataAndRuns(TrainingOverview data) {
    final leaves = trainingRows(data.dataset['by_leaf']);
    final phase = trainingMap(data.dataset['phase22']);
    final out = trainingMap(phase['out_of_scope']);
    final plan = trainingMap(data.dataset['collection_plan']);
    final ready = data.dataset['ready'] == true;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Wrap(
          alignment: WrapAlignment.spaceBetween,
          crossAxisAlignment: WrapCrossAlignment.center,
          spacing: 16,
          runSpacing: 12,
          children: [
            Text('ข้อมูลสำหรับเทรน',
                style: Theme.of(context).textTheme.titleLarge),
            FilledButton.icon(
                key: const Key('start-training'),
                onPressed:
                    ready && !_busy && _run?.isRunning != true ? _train : null,
                icon: const Icon(Icons.play_arrow),
                label:
                    Text(_busy ? 'กำลังส่งคำขอ' : 'เริ่มเทรนและเปรียบเทียบ')),
          ]),
      const SizedBox(height: 16),
      _TableScroll(
          child: DataTable(
              columns: const [
            DataColumn(label: Text('หมวด')),
            DataColumn(label: Text('ฝึก')),
            DataColumn(label: Text('ตรวจสอบ')),
            DataColumn(label: Text('ทดสอบ')),
            DataColumn(label: Text('รวม')),
            DataColumn(label: Text('ช่อง')),
            DataColumn(label: Text('พร้อมเทรน'))
          ],
              rows: leaves.map((row) {
                final counts = trainingMap(row['split_counts']);
                return DataRow(cells: [
                  DataCell(Text(_category(row['leaf_key']))),
                  ...['train', 'validation', 'test']
                      .map((split) => DataCell(Text('${counts[split] ?? 0}'))),
                  DataCell(Text('${row['total']}')),
                  DataCell(Text('${row['unique_channels']}')),
                  DataCell(Text(row['ready'] == true ? 'พร้อม' : 'ยังไม่ครบ'))
                ]);
              }).toList())),
      const SizedBox(height: 12),
      Text(
          'จำนวนช่องทั้งหมด ${data.dataset['unique_channels']} · ช่องซ้ำข้ามชุด ${data.dataset['channel_leakage_count']}'),
      if (!ready) ...[
        const SizedBox(height: 12),
        ...leaves.where((r) => r['ready'] != true).map((row) {
          final counts = trainingMap(row['split_counts']);
          final minimum = trainingMap(row['minimum_split_counts']);
          return Text(
              '${_category(row['leaf_key'])}: ขั้นต่ำ ${row['minimum_required']} รายการ · ฝึก ${counts['train']}/${minimum['train']} · ตรวจสอบ ${counts['validation']}/${minimum['validation']} · ทดสอบ ${counts['test']}/${minimum['test']}');
        }),
        if (data.dataset['channel_leakage_count'] != 0)
          const Text('พบช่องเดียวกันข้ามชุดข้อมูล ต้องแก้ก่อนเทรน'),
      ],
      const Divider(height: 40),
      Text('เกณฑ์เปิดใช้งานโมเดลใหม่',
          style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 8),
      Text(
          'คะแนน Accuracy, Macro F1 และ Recall ต่ำสุดต่อหมวด: ${trainingPercent(data.policy['promotion_threshold'])} ขึ้นไป'),
      Text(
          'Unknown threshold สำหรับรอบใหม่: ${trainingPercent(data.policy['unknown_threshold'])} · Cross-validation ตามช่องสูงสุด ${data.policy['grouped_cv_folds']} รอบ'),
      const SizedBox(height: 8),
      if (plan.isNotEmpty)
        TrainingCollectionPanel(plan: plan, repository: _repository)
      else ...[
        ...trainingRows(phase['by_leaf']).map((r) => Text(
            '${_category(r['leaf_key'])}: ${r['sample_count']}/${r['minimum_sample_count']} รายการ · ${r['unique_channels']}/${r['minimum_unique_channels']} ช่อง')),
        Text(
            'ตัวอย่างนอกขอบเขตสำหรับทดสอบ: ${out['sample_count'] ?? 0}/${out['minimum_sample_count'] ?? 30} รายการ'),
      ],
      if (phase['ready'] != true)
        const Padding(
            padding: EdgeInsets.only(top: 8),
            child: Text('เก็บข้อมูลยังไม่ครบเกณฑ์เปิดใช้โมเดลใหม่')),
      const Divider(height: 40),
      Text('รอบเทรนล่าสุด', style: Theme.of(context).textTheme.titleLarge),
      const SizedBox(height: 12),
      if (_run == null)
        const Text('ยังไม่มีรอบเทรนจากหน้าเว็บ')
      else
        _RunSummary(run: _run!),
      if (data.runs.length > 1)
        ExpansionTile(
            title: const Text('ประวัติรอบก่อนหน้า'),
            children: data.runs
                .where((r) => r.id != _run?.id)
                .map((run) => Padding(
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    child: _RunSummary(run: run)))
                .toList()),
    ]);
  }

  Widget _modelList(TrainingOverview data) =>
      Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text('โมเดลที่บันทึกไว้ (${data.totalModels})',
            style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 16),
        if (_models.isEmpty)
          const Text('ยังไม่มีผลโมเดลที่บันทึกไว้')
        else
          _TableScroll(
              child: DataTable(
                  dataRowMinHeight: 74,
                  dataRowMaxHeight: 90,
                  columnSpacing: 24,
                  columns: const [
                    DataColumn(label: Text('โมเดล / รุ่น')),
                    DataColumn(label: Text('ข้อมูลฝึก')),
                    DataColumn(label: Text('CV ถูก / F1')),
                    DataColumn(label: Text('Test ถูก / F1')),
                    DataColumn(label: Text('สถานะ')),
                    DataColumn(label: Text('จัดการ'))
                  ],
                  rows: _models
                      .map((model) => DataRow(cells: [
                            DataCell(SizedBox(
                                width: 285,
                                child: Column(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                          '#${model.id} ${trainingModelName(model.key)}'),
                                      Text(model.version,
                                          style: Theme.of(context)
                                              .textTheme
                                              .bodySmall,
                                          maxLines: 2,
                                          overflow: TextOverflow.ellipsis)
                                    ]))),
                            DataCell(Text('${model.sampleCount}')),
                            DataCell(_metricsPair(model, 'grouped_cv')),
                            DataCell(_metricsPair(model, 'test')),
                            DataCell(Text(model.isActive
                                ? 'กำลังใช้งาน'
                                : trainingStatus(model.status))),
                            DataCell(
                                Row(mainAxisSize: MainAxisSize.min, children: [
                              IconButton(
                                  tooltip: 'ดูผลประเมิน #${model.id}',
                                  onPressed: () => _details(model),
                                  icon: const Icon(Icons.analytics_outlined)),
                              IconButton(
                                  tooltip: model.canActivate
                                      ? 'เปิดใช้โมเดล #${model.id}'
                                      : 'ยังเปิดใช้ไม่ได้ หรือกำลังใช้งานอยู่',
                                  onPressed: model.canActivate && !_busy
                                      ? () => _activate(model)
                                      : null,
                                  icon: Icon(model.isActive
                                      ? Icons.check_circle
                                      : Icons.play_circle_outline))
                            ])),
                          ]))
                      .toList())),
        if (_models.length < data.totalModels)
          Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                  onPressed: _moreLoading ? null : _more,
                  icon: const Icon(Icons.expand_more),
                  label:
                      Text(_moreLoading ? 'กำลังโหลด' : 'ดูโมเดลเพิ่มเติม'))),
      ]);

  Widget _metricsPair(TrainedModel model, String split) => Text(
      '${trainingPercent(model.metric(split, 'accuracy')?['value'])}\n${trainingPercent(model.metric(split, 'f1_macro')?['value'])}');
}

class _TableScroll extends StatelessWidget {
  const _TableScroll({required this.child});
  final Widget child;
  @override
  Widget build(BuildContext context) =>
      SingleChildScrollView(scrollDirection: Axis.horizontal, child: child);
}

class _RunSummary extends StatelessWidget {
  const _RunSummary({required this.run});
  final TrainingRun run;
  @override
  Widget build(BuildContext context) =>
      Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text('${trainingDate(run.createdAt)} · ${trainingStatus(run.status)}',
            style: Theme.of(context).textTheme.titleMedium),
        SelectableText('รหัสรอบ: ${run.id}'),
        if (run.isRunning) ...[
          const SizedBox(height: 12),
          const LinearProgressIndicator(),
          const SizedBox(height: 8),
          Text(
              '${trainingStatus(run.stage)}${run.modelKey == null ? '' : ' · ${trainingModelName(run.modelKey!)}'}')
        ],
        if (run.error != null)
          Text(run.error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error)),
        if (run.status == 'completed')
          Text(
              'บันทึก ${(run.result['model_ids'] as List? ?? []).length} โมเดล · โมเดลที่ใช้งานอยู่ยังไม่เปลี่ยน'),
        ...trainingRows(run.result['skipped_models']).map((m) => Text(
            '${trainingModelName(m['model_key'].toString())}: ${m['status'] == 'skipped_unavailable' ? 'ไม่ได้เทรน เพราะโมเดลยังไม่พร้อมในเครื่อง' : 'เทรนไม่สำเร็จ'}')),
      ]);
}

class _ModelDetails extends StatefulWidget {
  const _ModelDetails({required this.id, required this.repository});
  final int id;
  final AdminRepository repository;
  @override
  State<_ModelDetails> createState() => _ModelDetailsState();
}

class _ModelDetailsState extends State<_ModelDetails> {
  late Future<TrainedModel> _future;
  @override
  void initState() {
    super.initState();
    _future = widget.repository.trainingModel(widget.id);
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text('ผลประเมินโมเดล #${widget.id}'),
        content: SizedBox(
            width: 850,
            child: FutureBuilder<TrainedModel>(
                future: _future,
                builder: (context, snapshot) {
                  if (snapshot.hasError) {
                    return ErrorStateView(
                        message: snapshot.error.toString(),
                        onRetry: () => setState(() => _future =
                            widget.repository.trainingModel(widget.id)));
                  }
                  if (!snapshot.hasData) {
                    return const SizedBox(
                        height: 120,
                        child: Center(child: CircularProgressIndicator()));
                  }
                  final model = snapshot.data!;
                  final reasons =
                      (model.qualification['blocked_reasons'] as List? ?? [])
                          .map((r) => trainingGateReason(r.toString()))
                          .toList();
                  return SingleChildScrollView(
                      child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                        Text(trainingModelName(model.key),
                            style: Theme.of(context).textTheme.titleLarge),
                        SelectableText(model.version),
                        ClassificationReadinessPanel(
                            readiness: model.readiness),
                        Text(
                            '${trainingStatus(model.status)} · Unknown threshold ${trainingPercent(model.unknownThreshold)}'),
                        if (!model.artifactAvailable)
                          const Text('ไม่พบไฟล์โมเดลในเครื่อง เปิดใช้ไม่ได้'),
                        ...reasons.map((reason) => Padding(
                            padding: const EdgeInsets.only(top: 8),
                            child: Text(reason))),
                        const Divider(height: 32),
                        ...model.metrics.map((metric) => Padding(
                            padding: const EdgeInsets.symmetric(vertical: 4),
                            child: Text(
                                '${_split(metric['split'])} · ${_metric(metric['metric'])}: ${trainingPercent(metric['value'])} (${metric['sample_size']} ตัวอย่าง)'))),
                        const Divider(height: 32),
                        Text('ผลแยกตามหมวด',
                            style: Theme.of(context).textTheme.titleMedium),
                        if (model.perCategory.isEmpty)
                          const Text('ยังไม่มีผลแยกตามหมวด')
                        else
                          _TableScroll(
                              child: DataTable(
                                  columns: const [
                                DataColumn(label: Text('ชุดข้อมูล')),
                                DataColumn(label: Text('หมวด')),
                                DataColumn(label: Text('ตัวชี้วัด')),
                                DataColumn(label: Text('ผล')),
                                DataColumn(label: Text('ตัวอย่าง'))
                              ],
                                  rows: model.perCategory
                                      .map((r) => DataRow(cells: [
                                            DataCell(Text(_split(r['split']))),
                                            DataCell(
                                                Text(_category(r['category']))),
                                            DataCell(
                                                Text(_metric(r['metric']))),
                                            DataCell(Text(
                                                trainingPercent(r['value']))),
                                            DataCell(
                                                Text('${r['sample_size']}'))
                                          ]))
                                      .toList())),
                        ...model.confusionMatrices.map((matrix) {
                          final labels = (matrix['labels'] as List? ?? [])
                              .map((l) => _category(l))
                              .toList();
                          final rows = matrix['matrix'] as List? ?? [];
                          return ExpansionTile(
                              title: Text(
                                  'ทายถูกและสับสน · ${_split(matrix['split'])}'),
                              children: [
                                _TableScroll(
                                    child: DataTable(
                                        columns: [
                                      const DataColumn(
                                          label: Text('หมวดจริง / ทายเป็น')),
                                      ...labels.map(
                                          (l) => DataColumn(label: Text(l)))
                                    ],
                                        rows: List.generate(
                                            rows.length,
                                            (i) => DataRow(cells: [
                                                  DataCell(Text(labels[i])),
                                                  ...(rows[i] as List).map(
                                                      (v) =>
                                                          DataCell(Text('$v')))
                                                ]))))
                              ]);
                        }),
                      ]));
                })),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context), child: const Text('ปิด'))
        ],
      );
}

String _category(dynamic value) => switch (value) {
      'phone' => 'Phone',
      'camera' => 'Camera',
      'laptop' => 'Laptop',
      'unknown' => 'นอกขอบเขต',
      _ => '$value'
    };
String _split(dynamic value) => switch (value) {
      'grouped_cv' => 'ตรวจสอบข้ามช่อง (CV)',
      'validation' => 'ชุดตรวจสอบเดิม',
      'test' => 'ชุดทดสอบ',
      'out_of_scope' => 'นอกขอบเขต',
      _ => '$value'
    };
String _metric(dynamic value) => switch (value) {
      'accuracy' => 'ทายหมวดถูก',
      'f1_macro' => 'F1 เฉลี่ยทุกหมวด',
      'unknown_recall' => 'ตรวจพบนอกขอบเขต',
      'precision' => 'Precision',
      'recall' => 'Recall',
      'f1' => 'F1',
      _ => '$value'
    };
