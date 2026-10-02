import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import '../models/clip_revision_plan.dart';
import '../models/recommendation_result.dart';
import '../repositories/content_repository.dart';
import 'actionable_advice_panel.dart';

class ClipRevisionPlanner extends StatefulWidget {
  const ClipRevisionPlanner(
      {super.key,
      required this.data,
      required this.repository,
      this.onDirtyChanged,
      this.withheld = false});
  final AnalysisResultViewData data;
  final ContentRepository repository;
  final ValueChanged<bool>? onDirtyChanged;
  final bool withheld;
  @override
  State<ClipRevisionPlanner> createState() => _ClipRevisionPlannerState();
}

class _ClipRevisionPlannerState extends State<ClipRevisionPlanner> {
  final _notes = TextEditingController();
  ClipRevisionPlan? _plan;
  Set<String> _selected = {};
  bool _loading = true, _saving = false;
  String? _loadError, _saveError;
  bool get _dirty =>
      _plan != null &&
      (!setEquals(_selected, _plan!.selectedIds.toSet()) ||
          _notes.text != _plan!.notes);

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _notes.dispose();
    super.dispose();
  }

  void _changed() {
    setState(() => _saveError = null);
    widget.onDirtyChanged?.call(_dirty);
  }

  Future<void> _load() async {
    if (_dirty) {
      final discard = await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
                  title: const Text('โหลดแผนที่บันทึกไว้แทนฉบับที่กำลังแก้?'),
                  content:
                      const Text('การเปลี่ยนแปลงที่ยังไม่บันทึกจะถูกยกเลิก'),
                  actions: [
                    TextButton(
                        onPressed: () => Navigator.pop(context, false),
                        child: const Text('แก้ต่อ')),
                    TextButton(
                        onPressed: () => Navigator.pop(context, true),
                        child: const Text('โหลดแผนที่บันทึก'))
                  ]));
      if (discard != true || !mounted) return;
    }
    setState(() {
      _loading = true;
      _loadError = null;
    });
    try {
      final plan =
          await widget.repository.getRevisionPlan(widget.data.contentId!);
      if (plan.contentId != widget.data.contentId ||
          plan.analysisId != widget.data.raw['analysis_id'] ||
          plan.fingerprint != widget.data.raw['recommendation_fingerprint']) {
        throw StateError('ผลวิเคราะห์ไม่ตรงกับแผน กรุณาโหลดผลวิเคราะห์ใหม่');
      }
      if (!mounted) return;
      setState(() {
        _plan = plan;
        _selected = plan.selectedIds.toSet();
        _notes.text = plan.notes;
        _saveError = null;
      });
      widget.onDirtyChanged?.call(false);
    } catch (error) {
      if (mounted) {
        setState(() => _loadError = 'โหลดแผนไม่สำเร็จ: ${_message(error)}');
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  String _message(Object error) => error
      .toString()
      .replaceFirst(RegExp(r'^(Exception|Bad state|FormatException): '), '');

  Future<void> _save() async {
    final original = _plan;
    if (original == null || _saving || !_dirty) return;
    setState(() {
      _saving = true;
      _saveError = null;
    });
    try {
      final saved = await widget.repository.saveRevisionPlan(
          widget.data.contentId!, original.request(_selected, _notes.text));
      if (!mounted) return;
      if (saved.contentId != original.contentId ||
          saved.analysisId != original.analysisId ||
          saved.fingerprint != original.fingerprint ||
          saved.revision != original.revision + 1 ||
          saved.savedAt == null ||
          !setEquals(saved.selectedIds.toSet(), _selected) ||
          saved.notes != _notes.text) {
        throw StateError(
            'ข้อมูลตอบกลับไม่ยืนยันแผนฉบับนี้ กรุณาโหลดแผนที่บันทึกเพื่อตรวจสอบ');
      }
      if (!mounted) return;
      setState(() => _plan = saved);
      widget.onDirtyChanged?.call(false);
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('บันทึกแผนปรับคลิปแล้ว')));
    } catch (error) {
      if (mounted) {
        setState(
            () => _saveError = 'ยังยืนยันการบันทึกไม่ได้: ${_message(error)}');
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _openRevisionUpload() async {
    final plan = _plan;
    if (plan == null || plan.revision <= 0) return;
    if (_dirty) {
      final useSaved = await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
                  title: const Text('แผนฉบับร่างยังไม่ถูกบันทึก'),
                  content: const Text(
                      'บันทึกฉบับร่างก่อน หรือยืนยันว่าจะใช้แผนฉบับที่บันทึกไว้ในการเทียบครั้งนี้'),
                  actions: [
                    TextButton(
                        onPressed: () => Navigator.pop(context, false),
                        child: const Text('กลับไปบันทึก')),
                    FilledButton(
                        onPressed: () => Navigator.pop(context, true),
                        child: const Text('ใช้แผนที่บันทึกไว้')),
                  ]));
      if (useSaved != true || !mounted) return;
    }
    final actions =
        widget.data.recommendation.actionableRecommendations?.items ?? [];
    final titles = actions
        .where((item) => plan.selectedIds.contains(item.id))
        .map((item) => item.title)
        .toList();
    Navigator.pushNamed(context, '/upload', arguments: {
      'revisionContext': {
        'parent_content_id': plan.contentId,
        'parent_analysis_id': plan.analysisId,
        'parent_recommendation_fingerprint': plan.fingerprint,
        'expected_plan_revision': plan.revision,
        'parent_title': widget.data.title,
        'plan_saved_at': plan.savedAt?.toIso8601String(),
        'selected_topics': titles,
        'notes_only': plan.selectedIds.isEmpty,
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final actions = widget.data.recommendation.actionableRecommendations;
    final enabled =
        !_loading && !_saving && _loadError == null && _plan != null;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      if (_loading) const LinearProgressIndicator(),
      if (_loadError != null)
        Text(_loadError!,
            style: TextStyle(color: Theme.of(context).colorScheme.error)),
      if (_loadError != null)
        Align(
            alignment: Alignment.centerLeft,
            child: OutlinedButton.icon(
                onPressed: _loading ? null : _load,
                icon: const Icon(Icons.refresh),
                label: const Text('โหลดแผนอีกครั้ง'))),
      if (actions != null)
        ActionableAdvicePanel(
            data: actions,
            bundle: widget.data.recommendation.evidenceBundle,
            withheld: widget.withheld,
            selectedIds: _selected,
            onSelectionChanged: enabled
                ? (id, selected) {
                    selected ? _selected.add(id) : _selected.remove(id);
                    _changed();
                  }
                : null)
      else
        const Padding(
          padding: EdgeInsets.symmetric(vertical: 12),
          child: Text(
            'ผลวิเคราะห์นี้ยังไม่มีคำแนะนำแบบลงมือทำ จึงไม่มีหัวข้อให้เลือกเพิ่มในแผน',
          ),
        ),
      const Divider(height: 32),
      Text('แผนปรับคลิปของฉัน', style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 8),
      Text(
          'เลือก ${_selected.length} ข้อเพื่อนำไปปรับ · ยังไม่ได้ยืนยันว่าปรับคลิปเสร็จ'),
      if (_plan != null)
        Text(
            _dirty
                ? 'มีการเปลี่ยนแปลงที่ยังไม่บันทึก'
                : _plan!.revision == 0
                    ? 'ยังไม่มีแผนที่บันทึก'
                    : 'แผนที่บันทึกแล้ว · ฉบับ ${_plan!.revision} · ${_plan!.savedAt!.toLocal().toString().split('.').first}',
            style: Theme.of(context).textTheme.bodySmall),
      const SizedBox(height: 16),
      TextField(
          key: const ValueKey('revision-plan-notes'),
          controller: _notes,
          enabled: enabled,
          minLines: 3,
          maxLines: 8,
          maxLength: 4000,
          decoration: const InputDecoration(
              labelText: 'รายละเอียดแผนปรับคลิป',
              alignLabelWithHint: true,
              border: OutlineInputBorder()),
          onChanged: (_) => _changed()),
      if (_saveError != null)
        Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Text(_saveError!,
                style: TextStyle(color: Theme.of(context).colorScheme.error))),
      Wrap(spacing: 12, runSpacing: 8, children: [
        FilledButton.icon(
            key: const ValueKey('save-revision-plan'),
            onPressed: enabled && _dirty ? _save : null,
            icon: _saving
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.save_outlined),
            label: Text(_saving ? 'กำลังบันทึก...' : 'บันทึกแผนปรับคลิป')),
        OutlinedButton.icon(
            onPressed: _loading || _saving ? null : _load,
            icon: const Icon(Icons.refresh),
            label: const Text('โหลดแผนที่บันทึก')),
        FilledButton.tonalIcon(
            key: const ValueKey('upload-revision'),
            onPressed:
                enabled && _plan!.revision > 0 ? _openRevisionUpload : null,
            icon: const Icon(Icons.upload_file_outlined),
            label: const Text('อัปโหลดฉบับแก้ไข')),
      ]),
      if (_plan != null && _plan!.revision > 0 && _plan!.selectedIds.isEmpty)
        const Padding(
            padding: EdgeInsets.only(top: 8),
            child: Text(
                'แผนนี้มีเฉพาะบันทึก: ระบบจะวิเคราะห์คลิปใหม่ตามปกติ แต่ไม่มีหัวข้อสำหรับเทียบอัตโนมัติ')),
    ]);
  }
}
