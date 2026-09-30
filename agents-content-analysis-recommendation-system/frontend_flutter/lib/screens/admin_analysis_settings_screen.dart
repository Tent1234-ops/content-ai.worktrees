import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/analysis_settings.dart';
import '../repositories/admin_repository.dart';
import '../widgets/app_shell.dart';
import '../widgets/state_widgets.dart';
import '../widgets/trend_settings_panel.dart';

class AdminAnalysisSettingsScreen extends StatefulWidget {
  const AdminAnalysisSettingsScreen({super.key, this.repository});
  final AdminRepository? repository;
  @override
  State<AdminAnalysisSettingsScreen> createState() =>
      _AdminAnalysisSettingsScreenState();
}

class _AdminAnalysisSettingsScreenState
    extends State<AdminAnalysisSettingsScreen> {
  final _form = GlobalKey<FormState>();
  final _maximum = TextEditingController();
  final _hook = TextEditingController();
  late final AdminRepository _repository;
  AnalysisSettings? _settings;
  String? _asr;
  String? _error;
  bool _loading = true;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? AdminRepository();
    _load();
  }

  @override
  void dispose() {
    _maximum.dispose();
    _hook.dispose();
    super.dispose();
  }

  void _apply(AnalysisSettings settings) {
    _settings = settings;
    _maximum.text = '${settings.uploadMaxDurationSeconds}';
    _hook.text = '${settings.hookDurationSeconds}';
    _asr = settings.asrModel;
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final settings = await _repository.getAnalysisSettings();
      if (mounted) setState(() => _apply(settings));
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _save() async {
    if (!_form.currentState!.validate()) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final settings = await _repository.saveAnalysisSettings(
        uploadMaxDurationSeconds: int.parse(_maximum.text),
        asrModel: _asr!,
        hookDurationSeconds: int.parse(_hook.text),
      );
      if (!mounted) return;
      setState(() => _apply(settings));
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('บันทึกการตั้งค่าแล้ว')));
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Widget _numberField(TextEditingController controller, String label,
          int minimum, int maximum) =>
      TextFormField(
        controller: controller,
        enabled: !_saving,
        keyboardType: TextInputType.number,
        inputFormatters: [FilteringTextInputFormatter.digitsOnly],
        decoration: InputDecoration(
            labelText: label,
            suffixText: 'วินาที',
            border: const OutlineInputBorder()),
        validator: (text) {
          final value = int.tryParse(text ?? '');
          if (value == null || value < minimum || value > maximum) {
            return 'ระบุค่าระหว่าง $minimum ถึง $maximum วินาที';
          }
          if (controller == _hook &&
              value > (int.tryParse(_maximum.text) ?? 0)) {
            return 'ช่วงเปิดคลิปต้องไม่ยาวกว่าขีดจำกัดอัปโหลด';
          }
          return null;
        },
      );

  @override
  Widget build(BuildContext context) {
    final settings = _settings;
    return AppShell(
      title: 'ตั้งค่าการวิเคราะห์',
      currentRoute: '/admin-analysis-settings',
      isAdmin: true,
      actions: [
        IconButton(
            onPressed: _saving || _loading ? null : _load,
            tooltip: 'โหลดค่าล่าสุด',
            icon: const Icon(Icons.refresh))
      ],
      child: DefaultTabController(
          length: 2,
          child: Column(children: [
            const TabBar(
                tabs: [Tab(text: 'วิเคราะห์คลิป'), Tab(text: 'อัปเดตเทรนด์')]),
            Expanded(
                child: TabBarView(children: [
              _loading
                  ? const Center(child: CircularProgressIndicator())
                  : settings == null
                      ? ErrorStateView(
                          message: _error ?? 'โหลดการตั้งค่าไม่สำเร็จ',
                          onRetry: _load)
                      : SingleChildScrollView(
                          padding: const EdgeInsets.all(24),
                          child: Center(
                              child: ConstrainedBox(
                            constraints: const BoxConstraints(maxWidth: 1100),
                            child: Column(
                                crossAxisAlignment: CrossAxisAlignment.stretch,
                                children: [
                                  if (_error != null)
                                    Padding(
                                        padding:
                                            const EdgeInsets.only(bottom: 16),
                                        child: Text(_error!,
                                            style: TextStyle(
                                                color: Theme.of(context)
                                                    .colorScheme
                                                    .error))),
                                  LayoutBuilder(
                                      builder: (context, constraints) {
                                    final width = constraints.maxWidth >= 900
                                        ? (constraints.maxWidth - 48) / 2
                                        : constraints.maxWidth;
                                    return Wrap(
                                        spacing: 48,
                                        runSpacing: 32,
                                        children: [
                                          SizedBox(
                                              width: width,
                                              child: Form(
                                                  key: _form,
                                                  child: Column(
                                                    crossAxisAlignment:
                                                        CrossAxisAlignment
                                                            .stretch,
                                                    children: [
                                                      Text(
                                                          'วิดีโอและการถอดเสียง',
                                                          style:
                                                              Theme.of(context)
                                                                  .textTheme
                                                                  .titleLarge),
                                                      const SizedBox(
                                                          height: 24),
                                                      _numberField(
                                                          _maximum,
                                                          'ความยาวอัปโหลดสูงสุด',
                                                          30,
                                                          1800),
                                                      const SizedBox(
                                                          height: 24),
                                                      DropdownButtonFormField<
                                                          String>(
                                                        key: ValueKey(settings),
                                                        initialValue: _asr,
                                                        isExpanded: true,
                                                        decoration: const InputDecoration(
                                                            labelText:
                                                                'โมเดลถอดเสียง Whisper',
                                                            border:
                                                                OutlineInputBorder()),
                                                        items: settings
                                                            .whisperModels
                                                            .map((model) =>
                                                                DropdownMenuItem(
                                                                  value: model
                                                                      .name,
                                                                  enabled: model
                                                                      .ready,
                                                                  child: Text(
                                                                      model.ready
                                                                          ? model
                                                                              .name
                                                                          : '${model.name} (ยังไม่พร้อม)',
                                                                      style: model
                                                                              .ready
                                                                          ? null
                                                                          : TextStyle(
                                                                              color: Theme.of(context).disabledColor)),
                                                                ))
                                                            .toList(),
                                                        onChanged: _saving
                                                            ? null
                                                            : (value) =>
                                                                setState(() =>
                                                                    _asr =
                                                                        value),
                                                        validator: (value) => settings
                                                                .whisperModels
                                                                .any((m) =>
                                                                    m.name ==
                                                                        value &&
                                                                    m.ready)
                                                            ? null
                                                            : 'เลือกโมเดลที่พร้อมใช้งาน',
                                                      ),
                                                      const SizedBox(
                                                          height: 24),
                                                      _numberField(
                                                          _hook,
                                                          'ช่วงเปิดคลิป (Hook)',
                                                          5,
                                                          300),
                                                      const SizedBox(
                                                          height: 24),
                                                      Align(
                                                          alignment: Alignment
                                                              .centerLeft,
                                                          child:
                                                              FilledButton.icon(
                                                            onPressed: _saving
                                                                ? null
                                                                : _save,
                                                            icon: _saving
                                                                ? const SizedBox(
                                                                    width: 18,
                                                                    height: 18,
                                                                    child: CircularProgressIndicator(
                                                                        strokeWidth:
                                                                            2))
                                                                : const Icon(Icons
                                                                    .save_outlined),
                                                            label: Text(_saving
                                                                ? 'กำลังตรวจสอบและบันทึก'
                                                                : 'บันทึกการตั้งค่า'),
                                                          )),
                                                      const SizedBox(
                                                          height: 16),
                                                      Text(
                                                          'อัปเดตล่าสุด: ${_localTime(settings.updatedAt)}',
                                                          style:
                                                              Theme.of(context)
                                                                  .textTheme
                                                                  .bodySmall),
                                                    ],
                                                  ))),
                                          SizedBox(
                                              width: width,
                                              child: _ClassifierSummary(
                                                  model: settings
                                                      .classificationModel)),
                                        ]);
                                  }),
                                ]),
                          ))),
              SingleChildScrollView(
                  child: TrendSettingsPanel(repository: _repository)),
            ])),
          ])),
    );
  }
}

class _ClassifierSummary extends StatelessWidget {
  const _ClassifierSummary({required this.model});
  final Map<String, dynamic> model;
  @override
  Widget build(BuildContext context) {
    final metrics = (model['evaluation_metrics'] as List? ?? []).cast<Map>();
    final threshold = model['unknown_threshold'] as num?;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Text('โมเดลจำแนกหมวดที่ใช้งานอยู่',
          style: Theme.of(context).textTheme.titleLarge),
      const SizedBox(height: 16),
      if (model['model_id'] == null)
        const Text('ยังไม่มีโมเดลที่ผ่านเกณฑ์และเปิดใช้งาน')
      else ...[
        SelectableText('${model['model_key']}\n${model['model_version']}',
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 12),
        Text('รหัสโมเดล: ${model['model_id']}'),
        Text('ชนิด: ${model['model_type']}'),
        Text('จำนวนข้อมูลฝึก: ${model['training_sample_count']}'),
        Text(threshold == null
            ? 'อ่านเกณฑ์ Unknown จากไฟล์โมเดลไม่ได้'
            : 'เกณฑ์ Unknown จากโมเดล: ${(threshold * 100).toStringAsFixed(1)}%'),
        if (model['status'] != 'qualified')
          const Text('ไฟล์โมเดลยังไม่พร้อมใช้งาน'),
        const Divider(height: 32),
        Text('ผลประเมินที่บันทึกไว้',
            style: Theme.of(context).textTheme.titleMedium),
        if (metrics.isEmpty)
          const Text('ไม่มีผลประเมินในฐานข้อมูล')
        else
          ...metrics.map((metric) => Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Text(
                    '${_splitName(metric['split'])} · ${_metricName(metric['metric'])}: '
                    '${((metric['value'] as num) * 100).toStringAsFixed(1)}% '
                    '(${metric['sample_size']} ตัวอย่าง)'),
              )),
      ],
    ]);
  }
}

String _splitName(dynamic split) => switch (split) {
      'validation' => 'ชุดตรวจสอบ',
      'test' => 'ชุดทดสอบ',
      'out_of_scope' => 'นอกขอบเขต',
      _ => split.toString(),
    };
String _metricName(dynamic metric) => switch (metric) {
      'accuracy' => 'ทายหมวดถูก',
      'f1_macro' => 'คะแนน F1 เฉลี่ยทุกหมวด',
      'unknown_recall' => 'ตรวจพบนอกขอบเขต',
      'promotion_gate' => 'เกณฑ์เปิดใช้งาน',
      _ => metric.toString(),
    };
String _localTime(String value) {
  final date =
      DateTime.tryParse(value.endsWith('Z') ? value : '${value}Z')?.toLocal();
  return date == null
      ? '-'
      : '${date.day}/${date.month}/${date.year} '
          '${date.hour.toString().padLeft(2, '0')}:${date.minute.toString().padLeft(2, '0')}';
}
