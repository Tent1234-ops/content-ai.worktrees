import 'package:flutter/material.dart';
import '../widgets/reference_statistics_panel.dart';

import '../models/dataset_item.dart';
import '../models/dataset_review.dart';
import '../repositories/admin_repository.dart';
import '../widgets/app_shell.dart';
import '../widgets/state_widgets.dart';
import '../widgets/dataset_readiness_panel.dart';

class AdminDatasetsScreen extends StatefulWidget {
  const AdminDatasetsScreen({super.key, this.repository});

  final AdminRepository? repository;

  @override
  State<AdminDatasetsScreen> createState() => _AdminDatasetsScreenState();
}

class _AdminDatasetsScreenState extends State<AdminDatasetsScreen> {
  late final AdminRepository _repository;
  List<DatasetItem> _items = [];
  List<String> _categories = ['all'];
  List<DatasetReviewTaxonomyLeaf> _taxonomyLeaves = [];
  String _category = 'all';
  String? _error;
  bool _loading = false;
  bool _deleting = false;
  bool _creating = false;
  int _offset = 0;
  final int _limit = 12;
  int _total = 0;
  int _tab = 0;
  int _request = 0;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? AdminRepository();
    _load();
  }

  Future<void> _load() async {
    final request = ++_request;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final taxonomyLeaves = _taxonomyLeaves.isEmpty
          ? await _repository.listTaxonomyLeaves()
          : _taxonomyLeaves;
      final response = await _repository.listDatasets(
        limit: _limit,
        offset: _offset,
        category: _category,
        trashed: _tab == 3,
      );
      if (!mounted || request != _request) return;
      if (response.items.isEmpty && _offset > 0) {
        _offset =
            response.total == 0 ? 0 : ((response.total - 1) ~/ _limit) * _limit;
        await _load();
        return;
      }
      final discoveredCategories = <String>{
        'all',
        _category,
        ...taxonomyLeaves.map((item) => item.leafKey),
      };
      for (final item in response.items) {
        final category = item.taxonomyLeafKey.isNotEmpty
            ? item.taxonomyLeafKey
            : item.category;
        if (category.isNotEmpty) discoveredCategories.add(category);
      }
      setState(() {
        _items = response.items;
        _total = response.total;
        _taxonomyLeaves = taxonomyLeaves;
        _categories = discoveredCategories.toList()..sort();
      });
    } catch (error) {
      if (!mounted || request != _request) return;
      setState(() => _error = error.toString());
    } finally {
      if (mounted && request == _request) setState(() => _loading = false);
    }
  }

  void _applyFilters() {
    setState(() => _offset = 0);
    _load();
  }

  String _categoryLabel(String leafKey) {
    if (leafKey == 'all') return 'ทั้งหมด';
    for (final leaf in _taxonomyLeaves) {
      if (leaf.leafKey == leafKey) return leaf.path;
    }
    return leafKey;
  }

  Future<void> _openEditor(DatasetItem item) async {
    final saved = await showDialog<String>(
      context: context,
      builder: (context) => _DatasetEditorDialog(
        item: item,
        repository: _repository,
        taxonomyLeaves: _taxonomyLeaves,
      ),
    );
    if (saved != null) {
      await _load();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            saved == 'training'
                ? 'บันทึกแล้ว ต้องฝึกและเปิดใช้โมเดลใหม่เพื่อให้การแก้ไขมีผลต่อการจำแนกหมวด'
                : 'บันทึกข้อมูลแล้ว',
          ),
        ),
      );
    }
  }

  Future<void> _openCreator() async {
    final created = await showDialog<DatasetItem>(
      context: context,
      builder: (context) => _DatasetCreateDialog(
        repository: _repository,
        taxonomyLeaves: _taxonomyLeaves,
      ),
    );
    if (created == null || !mounted) return;
    setState(() {
      _creating = true;
      _tab = 0;
      _offset = 0;
      _category = 'all';
    });
    try {
      await _load();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'เพิ่ม Dataset #${created.datasetId} เป็นรายการรอตรวจแล้ว '
            '(ยังไม่ใช้ฝึกโมเดลหรือสร้างคำแนะนำ)',
          ),
        ),
      );
    } finally {
      if (mounted) setState(() => _creating = false);
    }
  }

  Future<void> _delete(DatasetItem item) async {
    final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
              title: const Text('ลบ Dataset ออกจากการใช้งาน?'),
              content: SizedBox(
                  width: 520,
                  child: Text('#${item.datasetId} ${item.title}\n\n'
                      'จะไม่นำรายการนี้ไปฝึกหรือแนะนำในงานใหม่ แต่เก็บหลักฐานของผลเก่าไว้ '
                      'โมเดลที่ใช้งานอยู่ต้องฝึกใหม่จึงจะตัดข้อมูลนี้ออกจากสิ่งที่เรียนรู้แล้ว')),
              actions: [
                TextButton(
                    onPressed: () => Navigator.pop(context, false),
                    child: const Text('ยกเลิก')),
                FilledButton.icon(
                    onPressed: () => Navigator.pop(context, true),
                    icon: const Icon(Icons.delete_outline),
                    label: const Text('ยืนยันลบ Dataset')),
              ],
            ));
    if (confirmed != true || !mounted) return;
    setState(() => _deleting = true);
    try {
      await _repository.deleteDataset(item.datasetId);
      if (!mounted) return;
      await _load();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('ลบ Dataset ออกจากการใช้งานแล้ว')));
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('ลบไม่สำเร็จ: $error')));
      }
    } finally {
      if (mounted) setState(() => _deleting = false);
    }
  }

  Future<void> _restore(DatasetItem item) async {
    final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
                title: const Text('กู้คืน Dataset?'),
                content: SizedBox(
                    width: 520,
                    child: Text('#${item.datasetId} ${item.title}\n\n'
                        'รักษา Transcript หมวดหมู่ และชุดข้อมูลเดิม หากไม่มีประวัติสิทธิ์ก่อนลบ '
                        'จะไม่เปิดสิทธิ์ฝึกหรือแนะนำให้อัตโนมัติ โมเดลที่ฝึกแล้วจะไม่เปลี่ยนแปลง')),
                actions: [
                  TextButton(
                      onPressed: () => Navigator.pop(context, false),
                      child: const Text('ยกเลิก')),
                  FilledButton.icon(
                      onPressed: () => Navigator.pop(context, true),
                      icon: const Icon(Icons.restore),
                      label: const Text('ยืนยันกู้คืน'))
                ]));
    if (confirmed != true || !mounted) return;
    setState(() => _deleting = true);
    try {
      final restored = await _repository.restoreDataset(item.datasetId);
      if (!mounted) return;
      await _load();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text(restored.isTrainingEligible
                ? 'กู้คืนข้อมูลและสิทธิ์เดิมแล้ว'
                : 'กู้คืนข้อมูลแล้ว รายการนี้ยังไม่เปิดสิทธิ์ใช้ฝึกโมเดล')));
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('กู้คืนไม่สำเร็จ: $error')));
      }
    } finally {
      if (mounted) setState(() => _deleting = false);
    }
  }

  static const _viewTitles = {
    0: 'รายการข้อมูล',
    1: 'คุณภาพและแผนเก็บข้อมูล',
    2: 'สถิติและการเติบโต',
    3: 'ถังขยะ',
  };

  void _selectView(int index) {
    setState(() {
      _tab = index;
      _offset = 0;
    });
    if (index == 0 || index == 3) _load();
  }

  @override
  Widget build(BuildContext context) {
    return AppShell(
      title: 'จัดการ Dataset',
      currentRoute: '/admin-datasets',
      isAdmin: true,
      actions: [
        PopupMenuButton<int>(
          tooltip: 'เครื่องมือ Dataset เพิ่มเติม',
          enabled: !_loading && !_deleting && !_creating,
          icon: const Icon(Icons.more_vert),
          onSelected: _selectView,
          itemBuilder: (_) => [
            for (final entry in _viewTitles.entries)
              if (entry.key != _tab)
                PopupMenuItem(value: entry.key, child: Text(entry.value)),
          ],
        ),
        IconButton(
          key: const ValueKey('dataset-create'),
          onPressed: _loading || _deleting || _creating || _tab != 0
              ? null
              : _openCreator,
          icon: const Icon(Icons.add),
          tooltip: 'เพิ่ม Dataset สำหรับตรวจสอบ',
        ),
        IconButton(
          onPressed: _loading || _deleting || _creating ? null : _load,
          icon: const Icon(Icons.refresh),
          tooltip: 'โหลดข้อมูลใหม่',
        ),
      ],
      child: Column(
        children: [
          if (_tab != 0)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: Row(children: [
                IconButton(
                  tooltip: 'กลับรายการข้อมูล',
                  onPressed:
                      _loading || _deleting ? null : () => _selectView(0),
                  icon: const Icon(Icons.arrow_back),
                ),
                const SizedBox(width: 8),
                Expanded(
                    child: Text(_viewTitles[_tab]!,
                        style: Theme.of(context).textTheme.titleMedium)),
              ]),
            ),
          if (_tab == 1)
            Expanded(child: DatasetReadinessPanel(repository: _repository))
          else if (_tab == 2)
            Expanded(child: ReferenceStatisticsPanel(repository: _repository))
          else ...[
            Padding(
              padding: const EdgeInsets.all(16),
              child: DropdownButtonFormField<String>(
                key: const ValueKey('dataset-category-filter'),
                isExpanded: true,
                initialValue: _category,
                decoration: const InputDecoration(labelText: 'หมวดหมู่'),
                items: _categories
                    .map(
                      (value) => DropdownMenuItem(
                        value: value,
                        child: Text(
                          _categoryLabel(value),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    )
                    .toList(),
                onChanged: _loading || _deleting
                    ? null
                    : (value) {
                        if (value == null) return;
                        setState(() => _category = value);
                        _applyFilters();
                      },
              ),
            ),
            if (_loading) const LinearProgressIndicator(),
            Expanded(
              child: _error != null
                  ? ErrorStateView(message: _error!, onRetry: _load)
                  : _loading
                      ? const Center(child: CircularProgressIndicator())
                      : _items.isEmpty
                          ? EmptyStateView(
                              title: _tab == 3 ? 'ถังขยะว่าง' : 'ไม่พบข้อมูล',
                              message: 'ไม่มีรายการที่ตรงกับหมวดหมู่ที่เลือก',
                              icon: Icons.storage_outlined,
                            )
                          : RefreshIndicator(
                              onRefresh: _load,
                              child: ListView.builder(
                                padding:
                                    const EdgeInsets.symmetric(horizontal: 16),
                                itemCount: _items.length + 1,
                                itemBuilder: (context, index) {
                                  if (index == _items.length) {
                                    return PaginationBar(
                                      offset: _offset,
                                      limit: _limit,
                                      total: _total,
                                      onPrevious: _offset <= 0
                                          ? null
                                          : () {
                                              setState(() => _offset =
                                                  (_offset - _limit)
                                                      .clamp(0, _offset));
                                              _load();
                                            },
                                      onNext: _offset + _limit >= _total
                                          ? null
                                          : () {
                                              setState(() => _offset += _limit);
                                              _load();
                                            },
                                    );
                                  }
                                  final item = _items[index];
                                  final categoryLabel =
                                      item.taxonomyPath.isNotEmpty
                                          ? item.taxonomyPath
                                          : item.category;
                                  return Card(
                                    child: ListTile(
                                      leading:
                                          const Icon(Icons.dataset_outlined),
                                      title: Text(item.title),
                                      subtitle: Padding(
                                          padding:
                                              const EdgeInsets.only(top: 8),
                                          child: Column(
                                              crossAxisAlignment:
                                                  CrossAxisAlignment.start,
                                              children: [
                                                Text(
                                                    '#${item.datasetId} · ${item.sourcePlatform} · $categoryLabel'),
                                                Text(
                                                    'ชุดข้อมูล: ${item.dataSplit.isEmpty ? "ยังไม่กำหนด" : item.dataSplit} · '
                                                    'ความยาว ${item.durationSeconds == null ? "ยังไม่มีข้อมูล" : "${item.durationSeconds} วินาที"}'),
                                                const SizedBox(height: 6),
                                                Text(
                                                    _tab == 3
                                                        ? 'อยู่ในถังขยะ ไม่ใช้ในงานใหม่'
                                                        : item.quality[
                                                                    'status'] ==
                                                                'complete'
                                                            ? 'ข้อมูลประกอบครบตามรายการตรวจ'
                                                            : item.quality
                                                                    .isEmpty
                                                                ? 'ยังไม่ได้ตรวจคุณภาพข้อมูล'
                                                                : 'ต้องตรวจ: ${(item.quality['issues'] as List? ?? []).join(" · ")}',
                                                    style: TextStyle(
                                                        color: item.quality[
                                                                    'status'] ==
                                                                'complete'
                                                            ? Theme.of(context)
                                                                .colorScheme
                                                                .secondary
                                                            : Theme.of(context)
                                                                .colorScheme
                                                                .onSurfaceVariant)),
                                              ])),
                                      trailing: IconButton(
                                          tooltip:
                                              '${_tab == 3 ? "กู้คืน" : "ลบ"} Dataset #${item.datasetId}',
                                          onPressed: _deleting || _loading
                                              ? null
                                              : () => _tab == 3
                                                  ? _restore(item)
                                                  : _delete(item),
                                          icon: Icon(_tab == 3
                                              ? Icons
                                                  .restore_from_trash_outlined
                                              : Icons.delete_outline)),
                                      onTap: _deleting || _tab == 3
                                          ? null
                                          : () => _openEditor(item),
                                    ),
                                  );
                                },
                              ),
                            ),
            ),
          ],
        ],
      ),
    );
  }
}

class _DatasetCreateDialog extends StatefulWidget {
  const _DatasetCreateDialog({
    required this.repository,
    required this.taxonomyLeaves,
  });

  final AdminRepository repository;
  final List<DatasetReviewTaxonomyLeaf> taxonomyLeaves;

  @override
  State<_DatasetCreateDialog> createState() => _DatasetCreateDialogState();
}

class _DatasetCreateDialogState extends State<_DatasetCreateDialog> {
  final _title = TextEditingController();
  final _url = TextEditingController();
  final _transcript = TextEditingController();
  String _taxonomyLeafKey = '';
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _title.dispose();
    _url.dispose();
    _transcript.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final title = _title.text.trim();
    final transcript = _transcript.text.trim();
    if (title.isEmpty) {
      setState(() => _error = 'กรุณาระบุชื่อรายการ');
      return;
    }
    if (_taxonomyLeafKey.isEmpty) {
      setState(() => _error = 'กรุณาเลือกหมวดหมู่มาตรฐาน');
      return;
    }
    if (transcript.isEmpty) {
      setState(() => _error = 'กรุณาระบุ Transcript ที่ต้องการตรวจสอบ');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final created = await widget.repository.createDataset({
        'title': title,
        'video_url': _url.text.trim().isEmpty ? null : _url.text.trim(),
        'transcript': transcript,
        'taxonomy_leaf_key': _taxonomyLeafKey,
        'source_platform': 'admin_manual',
        'dataset_source': 'admin',
        'dataset_version': 'manual-v1',
        'language': 'th',
        'verification_status': 'unverified',
        'label_source': 'admin',
        'data_split': 'unassigned',
        'is_training_eligible': false,
        'is_active': true,
      });
      if (created.datasetId <= 0 ||
          created.dataSplit != 'unassigned' ||
          created.isTrainingEligible ||
          created.transcriptSha256.length != 64 ||
          created.taxonomyLeafKey != _taxonomyLeafKey) {
        throw StateError('ระบบยังไม่ยืนยันข้อมูลแถวรอตรวจอย่างครบถ้วน');
      }
      if (!mounted) return;
      Navigator.pop(context, created);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('เพิ่ม Dataset สำหรับตรวจสอบ'),
      content: SizedBox(
        width: 640,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'รายการนี้จะถูกบันทึกเป็น unassigned และยังไม่ใช้ฝึกโมเดลหรือสร้างคำแนะนำ '
                'จนกว่าจะผ่านขั้นตอนตรวจสอบแยกต่างหาก',
              ),
              if (_error != null) ...[
                const SizedBox(height: 12),
                Text(
                  _error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ],
              const SizedBox(height: 12),
              TextField(
                key: const ValueKey('dataset-create-title'),
                controller: _title,
                enabled: !_saving,
                decoration: const InputDecoration(labelText: 'ชื่อรายการ'),
              ),
              const SizedBox(height: 10),
              DropdownButtonFormField<String>(
                key: const ValueKey('dataset-create-taxonomy-leaf'),
                initialValue: null,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'หมวดหมู่มาตรฐาน'),
                items: widget.taxonomyLeaves
                    .map(
                      (leaf) => DropdownMenuItem(
                        value: leaf.leafKey,
                        child: Text(
                          leaf.path,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    )
                    .toList(),
                onChanged: _saving
                    ? null
                    : (value) => setState(() => _taxonomyLeafKey = value ?? ''),
              ),
              const SizedBox(height: 10),
              TextField(
                key: const ValueKey('dataset-create-url'),
                controller: _url,
                enabled: !_saving,
                decoration: const InputDecoration(
                  labelText: 'URL ต้นทาง (ถ้ามี)',
                ),
              ),
              const SizedBox(height: 10),
              TextField(
                key: const ValueKey('dataset-create-transcript'),
                controller: _transcript,
                enabled: !_saving,
                minLines: 6,
                maxLines: 12,
                decoration: const InputDecoration(
                  labelText: 'Transcript',
                  helperText:
                      'ระบบจะจัดช่องว่างและสร้าง Transcript hash ให้อัตโนมัติ',
                ),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: _saving ? null : () => Navigator.pop(context),
          child: const Text('ยกเลิก'),
        ),
        FilledButton.icon(
          key: const ValueKey('dataset-create-save'),
          onPressed: _saving ? null : _save,
          icon: _saving
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.save_outlined),
          label: Text(_saving ? 'กำลังบันทึก...' : 'บันทึกเป็นรายการรอตรวจ'),
        ),
      ],
    );
  }
}

class _DatasetEditorDialog extends StatefulWidget {
  const _DatasetEditorDialog({
    required this.item,
    required this.repository,
    required this.taxonomyLeaves,
  });

  final DatasetItem item;
  final AdminRepository repository;
  final List<DatasetReviewTaxonomyLeaf> taxonomyLeaves;

  @override
  State<_DatasetEditorDialog> createState() => _DatasetEditorDialogState();
}

class _DatasetEditorDialogState extends State<_DatasetEditorDialog> {
  late final TextEditingController _title;
  late final TextEditingController _url;
  late final TextEditingController _transcript;
  late final TextEditingController _views;
  late final TextEditingController _likes;
  late final TextEditingController _comments;
  late final TextEditingController _score;
  late final TextEditingController _duration;
  late String _taxonomyLeafKey;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    final item = widget.item;
    _title = TextEditingController(text: item.title);
    _url = TextEditingController(text: item.videoUrl);
    _transcript = TextEditingController(text: item.transcript);
    final currentLeaf =
        item.taxonomyLeafKey.isNotEmpty ? item.taxonomyLeafKey : item.category;
    _taxonomyLeafKey = widget.taxonomyLeaves.any(
      (leaf) => leaf.leafKey == currentLeaf,
    )
        ? currentLeaf
        : '';
    _views = TextEditingController(text: '${item.views}');
    _likes = TextEditingController(text: '${item.likes}');
    _comments = TextEditingController(text: '${item.comments}');
    _score = TextEditingController(text: '${item.trendScore}');
    _duration = TextEditingController(text: '${item.durationSeconds ?? ''}');
  }

  @override
  void dispose() {
    _title.dispose();
    _url.dispose();
    _transcript.dispose();
    _views.dispose();
    _likes.dispose();
    _comments.dispose();
    _score.dispose();
    _duration.dispose();
    super.dispose();
  }

  Map<String, dynamic> _payload() {
    final durationText = _duration.text.trim();
    return {
      'title': _title.text.trim(),
      'video_url': _url.text.trim().isEmpty ? null : _url.text.trim(),
      'transcript':
          _transcript.text.trim().isEmpty ? null : _transcript.text.trim(),
      'taxonomy_leaf_key': _taxonomyLeafKey,
      'views': int.tryParse(_views.text.trim()) ?? 0,
      'likes': int.tryParse(_likes.text.trim()) ?? 0,
      'comments': int.tryParse(_comments.text.trim()) ?? 0,
      'trend_score': double.tryParse(_score.text.trim()) ?? 0,
      'duration_seconds':
          durationText.isEmpty ? null : int.tryParse(durationText),
    };
  }

  Future<void> _save() async {
    for (final field in [_views, _likes, _comments, _duration]) {
      if (field == _duration && field.text.trim().isEmpty) continue;
      final value = int.tryParse(field.text.trim());
      if (value == null || value < 0) {
        setState(() =>
            _error = 'ยอดสถิติและความยาวต้องเป็นจำนวนเต็มตั้งแต่ 0 ขึ้นไป');
        return;
      }
    }
    final score = double.tryParse(_score.text.trim());
    if (score == null || !score.isFinite || score < 0) {
      setState(() => _error = 'คะแนนต้องเป็นตัวเลขตั้งแต่ 0 ขึ้นไป');
      return;
    }
    if (_title.text.trim().isEmpty) {
      setState(() => _error = 'Title is required');
      return;
    }
    if (_taxonomyLeafKey.isEmpty) {
      setState(() => _error = 'A model taxonomy category is required');
      return;
    }
    if (widget.item.isTrainingEligible && _transcript.text.trim().length < 80) {
      setState(
        () => _error =
            'A training transcript must contain at least 80 characters',
      );
      return;
    }
    final originalTranscript =
        widget.item.transcript.replaceAll(RegExp(r'\s+'), ' ').trim();
    final editedTranscript =
        _transcript.text.replaceAll(RegExp(r'\s+'), ' ').trim();
    final trainingContentChanged =
        _taxonomyLeafKey != widget.item.taxonomyLeafKey ||
            editedTranscript != originalTranscript;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.repository.updateDataset(widget.item.datasetId, _payload());
      if (!mounted) return;
      Navigator.pop(context, trainingContentChanged ? 'training' : 'metadata');
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('แก้ไขข้อมูล Dataset'),
      content: SizedBox(
        width: 640,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Text(_error!,
                      style: TextStyle(
                          color: Theme.of(context).colorScheme.error)),
                ),
              TextField(
                key: const ValueKey('dataset-title'),
                controller: _title,
                decoration: const InputDecoration(labelText: 'ชื่อรายการ'),
              ),
              const SizedBox(height: 10),
              Row(
                children: [
                  Expanded(
                    child: InputDecorator(
                      decoration:
                          const InputDecoration(labelText: 'แพลตฟอร์มต้นทาง'),
                      child: Text(widget.item.sourcePlatform),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: DropdownButtonFormField<String>(
                      key: const ValueKey('dataset-taxonomy-leaf'),
                      initialValue:
                          _taxonomyLeafKey.isEmpty ? null : _taxonomyLeafKey,
                      isExpanded: true,
                      decoration:
                          const InputDecoration(labelText: 'หมวดหมู่ของโมเดล'),
                      items: widget.taxonomyLeaves
                          .map(
                            (leaf) => DropdownMenuItem(
                              value: leaf.leafKey,
                              child: Text(
                                leaf.path,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          )
                          .toList(),
                      onChanged: _saving
                          ? null
                          : (value) {
                              if (value == null) return;
                              setState(() => _taxonomyLeafKey = value);
                            },
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              TextField(
                  controller: _url,
                  decoration: const InputDecoration(labelText: 'URL วิดีโอ')),
              const SizedBox(height: 10),
              TextField(
                key: const ValueKey('dataset-transcript'),
                controller: _transcript,
                decoration: const InputDecoration(
                  labelText: 'Transcript สำหรับฝึกโมเดล',
                  helperText: 'ระบบจะคำนวณรหัสตรวจสอบ Transcript ใหม่อัตโนมัติ',
                ),
                minLines: 6,
                maxLines: 12,
              ),
              const SizedBox(height: 8),
              const Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  'การแก้ Transcript หรือหมวดหมู่จะมีผลเมื่อเทรนและเปิดใช้โมเดลรุ่นใหม่',
                ),
              ),
              const SizedBox(height: 10),
              Row(
                children: [
                  Expanded(
                      child: TextField(
                          controller: _views,
                          keyboardType: TextInputType.number,
                          decoration:
                              const InputDecoration(labelText: 'ยอดวิว'))),
                  const SizedBox(width: 10),
                  Expanded(
                      child: TextField(
                          controller: _likes,
                          keyboardType: TextInputType.number,
                          decoration:
                              const InputDecoration(labelText: 'ยอดไลก์'))),
                  const SizedBox(width: 10),
                  Expanded(
                      child: TextField(
                          controller: _comments,
                          keyboardType: TextInputType.number,
                          decoration:
                              const InputDecoration(labelText: 'ความคิดเห็น'))),
                ],
              ),
              const SizedBox(height: 10),
              Row(
                children: [
                  Expanded(
                      child: TextField(
                          controller: _score,
                          keyboardType: TextInputType.number,
                          decoration:
                              const InputDecoration(labelText: 'คะแนนเทรนด์'))),
                  const SizedBox(width: 10),
                  Expanded(
                      child: TextField(
                          controller: _duration,
                          keyboardType: TextInputType.number,
                          decoration: const InputDecoration(
                              labelText: 'ความยาว (วินาที)'))),
                ],
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
            onPressed: _saving ? null : () => Navigator.pop(context),
            child: const Text('ยกเลิก')),
        FilledButton.icon(
          key: const ValueKey('dataset-save'),
          onPressed: _saving ? null : _save,
          icon: _saving
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.save_outlined),
          label: Text(_saving ? 'กำลังบันทึก...' : 'บันทึก'),
        ),
      ],
    );
  }
}
