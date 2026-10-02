import 'dart:convert';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../models/dataset_review.dart';
import '../repositories/admin_repository.dart';
import '../utils/notebooklm_markdown_parser.dart';
import '../widgets/app_shell.dart';
import '../widgets/state_widgets.dart';

enum _TranscriptInputMode { files, manual }

enum _MarkdownImportStatus {
  ready,
  importing,
  imported,
  alreadyPresent,
  failed,
}

class _MarkdownImportItem {
  _MarkdownImportItem({
    required this.fileName,
    required this.document,
  });

  final String fileName;
  final NotebookLmMarkdownDocument document;
  _MarkdownImportStatus status = _MarkdownImportStatus.ready;
  NotebookLMImportResult? result;
  String? error;
}

class AdminTranscriptImportScreen extends StatefulWidget {
  const AdminTranscriptImportScreen({super.key, this.repository});

  final AdminRepository? repository;

  @override
  State<AdminTranscriptImportScreen> createState() =>
      _AdminTranscriptImportScreenState();
}

class _AdminTranscriptImportScreenState
    extends State<AdminTranscriptImportScreen> {
  final _formKey = GlobalKey<FormState>();
  final _videoUrlController = TextEditingController();
  final _transcriptController = TextEditingController();
  late final AdminRepository _repository;

  List<DatasetReviewTaxonomyLeaf> _taxonomy = const [];
  String? _leafKey;
  String _language = 'th';
  String _captionType = 'unspecified';
  String _strategy = 'classification_diverse';
  _TranscriptInputMode _inputMode = _TranscriptInputMode.files;
  int? _batchRunId;
  NotebookLMImportResult? _lastResult;
  String? _error;
  final List<_MarkdownImportItem> _markdownFiles = [];
  bool _loadingTaxonomy = true;
  bool _submitting = false;
  bool _readingMarkdown = false;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? AdminRepository();
    _loadTaxonomy();
  }

  @override
  void dispose() {
    _videoUrlController.dispose();
    _transcriptController.dispose();
    super.dispose();
  }

  Future<void> _loadTaxonomy() async {
    try {
      final queue = await _repository.listDatasetReviewQueue(
        limit: 1,
        offset: 0,
        status: 'all',
      );
      if (!mounted) return;
      setState(() {
        _taxonomy = queue.taxonomy;
        if (_leafKey != null &&
            !queue.taxonomy.any((leaf) => leaf.leafKey == _leafKey)) {
          _leafKey = null;
        }
      });
    } catch (error) {
      if (mounted) {
        setState(
          () => _error = _friendlyImportMessage(_importErrorMessage(error)),
        );
      }
    } finally {
      if (mounted) setState(() => _loadingTaxonomy = false);
    }
  }

  Future<void> _submit() async {
    if (_leafKey == null) {
      setState(() => _error = 'กรุณาเลือกหมวดหมู่ให้ถูกต้องก่อนนำเข้า');
      return;
    }
    if (_inputMode == _TranscriptInputMode.files) {
      final confirmed = await _confirmFileImportCategory();
      if (!confirmed || !mounted) return;
      await _submitMarkdownFiles();
      return;
    }
    if (!_formKey.currentState!.validate()) return;
    await _submitManualTranscript();
  }

  Future<void> _submitManualTranscript() async {
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      final result = await _repository.createNotebookLMCandidate(
        videoUrl: _videoUrlController.text,
        transcript: _transcriptController.text,
        proposedLeafKey: _leafKey!,
        transcriptLanguage: _language,
        captionType: _captionType,
        collectionStrategy: _strategy,
        collectionRunId: _batchRunId,
      );
      if (!mounted) return;
      setState(() {
        _batchRunId = result.collectionRunId;
        _lastResult = result;
        _videoUrlController.clear();
        _transcriptController.clear();
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
            content: Text('ตรวจข้อมูลเบื้องต้นแล้วและเพิ่มเข้าคิวตรวจสอบ')),
      );
    } catch (error) {
      if (mounted) {
        setState(
          () => _error = _friendlyImportMessage(_importErrorMessage(error)),
        );
      }
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  Future<void> _submitMarkdownFiles() async {
    final importable = _markdownFiles
        .where(
          (item) =>
              item.status == _MarkdownImportStatus.ready ||
              item.status == _MarkdownImportStatus.failed,
        )
        .toList();
    if (importable.isEmpty) {
      setState(() {
        _error = _markdownFiles.isEmpty
            ? 'กรุณาเลือกไฟล์ Markdown อย่างน้อยหนึ่งไฟล์'
            : 'ไฟล์ที่เลือกทั้งหมดถูกประมวลผลแล้ว';
      });
      return;
    }

    setState(() {
      _submitting = true;
      _error = null;
    });
    var imported = 0;
    var alreadyPresent = 0;
    var failed = 0;
    for (final item in importable) {
      if (!mounted) break;
      setState(() {
        item.status = _MarkdownImportStatus.importing;
        item.error = null;
      });
      try {
        final result = await _repository.createNotebookLMCandidate(
          videoUrl: item.document.sourceUrl!,
          transcript: item.document.transcript,
          proposedLeafKey: _leafKey!,
          transcriptLanguage: _language,
          captionType: _captionType,
          collectionStrategy: _strategy,
          collectionRunId: _batchRunId,
        );
        if (!mounted) break;
        setState(() {
          _batchRunId = result.collectionRunId;
          _lastResult = result;
          item.result = result;
          item.status = _MarkdownImportStatus.imported;
        });
        imported++;
      } catch (error) {
        if (!mounted) break;
        final message = _importErrorMessage(error);
        final exists = _isAlreadyPresent(message);
        setState(() {
          item.status = exists
              ? _MarkdownImportStatus.alreadyPresent
              : _MarkdownImportStatus.failed;
          item.error = _friendlyImportMessage(message);
        });
        if (exists) {
          alreadyPresent++;
        } else {
          failed++;
        }
      }
    }
    if (!mounted) return;
    setState(() {
      _submitting = false;
      _error = failed == 0
          ? null
          : 'นำเข้าไม่สำเร็จ $failed ไฟล์ กรุณาตรวจแต่ละไฟล์แล้วลองเฉพาะรายการที่ล้มเหลวอีกครั้ง';
    });
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          'Imported $imported file${imported == 1 ? '' : 's'}'
          '${alreadyPresent == 0 ? '' : ' · มีในระบบแล้ว $alreadyPresent ไฟล์'}'
          '${failed == 0 ? '' : ' · ล้มเหลว $failed ไฟล์'}',
        ),
      ),
    );
  }

  String _sourceIdentity(String rawUrl) {
    final normalizedUrl = rawUrl.trim();
    final uri = Uri.tryParse(normalizedUrl);
    if (uri != null) {
      final host = uri.host.toLowerCase().replaceFirst('www.', '');
      String? videoId;
      if (host == 'youtu.be' && uri.pathSegments.isNotEmpty) {
        videoId = uri.pathSegments.first;
      } else if (host == 'youtube.com' || host == 'm.youtube.com') {
        videoId = uri.queryParameters['v'];
        if (videoId == null && uri.pathSegments.length >= 2) {
          final route = uri.pathSegments.first.toLowerCase();
          if (route == 'shorts' || route == 'embed') {
            videoId = uri.pathSegments[1];
          }
        }
      }
      if (videoId != null && RegExp(r'^[A-Za-z0-9_-]{11}$').hasMatch(videoId)) {
        return 'youtube:${videoId.toLowerCase()}';
      }
    }
    return normalizedUrl.toLowerCase();
  }

  String _normalizedDuplicateText(String value) {
    return value.replaceAll(RegExp(r'\s+'), ' ').trim().toLowerCase();
  }

  String _importErrorMessage(Object error) {
    return error.toString().replaceFirst(RegExp(r'^Exception:\s*'), '').trim();
  }

  bool _isAlreadyPresent(String message) {
    final normalized = message.toLowerCase();
    return normalized.contains('already exists') ||
        normalized.contains('transcript duplicates') ||
        normalized.contains('duplicates an existing');
  }

  String _friendlyImportMessage(String message) {
    final normalized = message.toLowerCase();
    if (normalized.contains('transcript') && normalized.contains('duplicate')) {
      return 'มีข้อมูลนี้ในระบบแล้ว: พบ Transcript ที่มีเนื้อหาเหมือนกัน';
    }
    if (normalized.contains('already exists')) {
      return message;
    }
    return message;
  }

  Future<bool> _confirmFileImportCategory() async {
    final leafKey = _leafKey;
    if (leafKey == null) return false;
    DatasetReviewTaxonomyLeaf? leaf;
    for (final item in _taxonomy) {
      if (item.leafKey == leafKey) {
        leaf = item;
        break;
      }
    }
    final fileCount = _markdownFiles
        .where(
          (item) =>
              item.status == _MarkdownImportStatus.ready ||
              item.status == _MarkdownImportStatus.failed,
        )
        .length;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('ยืนยันหมวดหมู่ที่นำเข้า'),
        content: Text(
          'นำเข้า Transcript $fileCount ไฟล์เป็นหมวด '
          '${leaf?.path ?? leafKey} ใช่หรือไม่\n\n'
          'ระบบจะใช้หมวดหมู่นี้กับทุกไฟล์ในชุดนี้',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('ยกเลิก'),
          ),
          FilledButton.icon(
            onPressed: () => Navigator.pop(context, true),
            icon: const Icon(Icons.file_upload_outlined),
            label: const Text('นำเข้าไฟล์'),
          ),
        ],
      ),
    );
    return confirmed == true;
  }

  Future<void> _pickMarkdownTranscript() async {
    setState(() {
      _readingMarkdown = true;
      _error = null;
    });
    try {
      final result = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowedExtensions: const ['md'],
        allowMultiple: true,
        withData: true,
      );
      if (result == null) return;

      final existingUrls = _markdownFiles
          .map((item) => _sourceIdentity(item.document.sourceUrl!))
          .toSet();
      final existingFileNames = _markdownFiles
          .map((item) => _normalizedDuplicateText(item.fileName))
          .toSet();
      final existingTranscripts = _markdownFiles
          .map((item) => _normalizedDuplicateText(item.document.transcript))
          .toSet();
      final parsedFiles = <_MarkdownImportItem>[];
      final errors = <String>[];
      final duplicateSkips = <String>[];
      for (final file in result.files) {
        final fileNameIdentity = _normalizedDuplicateText(file.name);
        if (existingFileNames.contains(fileNameIdentity)) {
          duplicateSkips.add('${file.name}: duplicate file name');
          continue;
        }
        try {
          final bytes = file.bytes;
          if (bytes == null) {
            throw const FormatException('The file could not be read.');
          }
          if (bytes.length > 4 * 1024 * 1024) {
            throw const FormatException('The file must be 4 MB or smaller.');
          }
          final markdown = utf8.decode(bytes, allowMalformed: false);
          final document = NotebookLmMarkdownParser.parse(markdown);
          final sourceUrl = document.sourceUrl?.trim();
          if (sourceUrl == null || sourceUrl.isEmpty) {
            throw const FormatException(
              'A source YouTube URL is required in the file metadata.',
            );
          }
          final sourceIdentity = _sourceIdentity(sourceUrl);
          final transcriptIdentity =
              _normalizedDuplicateText(document.transcript);
          String? duplicateReason;
          if (existingUrls.contains(sourceIdentity)) {
            duplicateReason = 'same YouTube video';
          } else if (existingTranscripts.contains(transcriptIdentity)) {
            duplicateReason = 'identical transcript content';
          }
          if (duplicateReason != null) {
            duplicateSkips.add('${file.name}: $duplicateReason');
            continue;
          }
          existingFileNames.add(fileNameIdentity);
          existingUrls.add(sourceIdentity);
          existingTranscripts.add(transcriptIdentity);
          parsedFiles.add(
            _MarkdownImportItem(fileName: file.name, document: document),
          );
        } on FormatException catch (error) {
          errors.add('${file.name}: ${error.message}');
        } catch (error) {
          errors.add('${file.name}: $error');
        }
      }
      if (!mounted) return;
      setState(() {
        _inputMode = _TranscriptInputMode.files;
        _markdownFiles.addAll(parsedFiles);
        _error = errors.isEmpty ? null : errors.join('\n');
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'อ่านไฟล์แล้ว ${parsedFiles.length} ไฟล์'
            '${duplicateSkips.isEmpty ? '' : '; ${duplicateSkips.length} duplicates ignored'}'
            '${errors.isEmpty ? '' : '; ${errors.length} invalid'}',
          ),
        ),
      );
    } on FormatException catch (error) {
      if (mounted) setState(() => _error = error.message.toString());
    } catch (error) {
      if (mounted) {
        setState(() => _error = 'อ่านไฟล์ Markdown ไม่สำเร็จ: $error');
      }
    } finally {
      if (mounted) setState(() => _readingMarkdown = false);
    }
  }

  void _removeMarkdownFile(_MarkdownImportItem item) {
    setState(() {
      _markdownFiles.remove(item);
      _error = null;
    });
  }

  Future<void> _startNewBatch() async {
    final hasUnsavedInput = _markdownFiles.any(
          (item) =>
              item.status != _MarkdownImportStatus.imported &&
              item.status != _MarkdownImportStatus.alreadyPresent,
        ) ||
        _videoUrlController.text.trim().isNotEmpty ||
        _transcriptController.text.trim().isNotEmpty;
    if (hasUnsavedInput) {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('เริ่มชุดนำเข้าใหม่หรือไม่'),
          content: const Text(
            'ไฟล์ที่ยังไม่ส่งและข้อความ Transcript ที่วางไว้จะถูกล้าง',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('ยกเลิก'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('เริ่มชุดใหม่'),
            ),
          ],
        ),
      );
      if (confirmed != true || !mounted) return;
    }
    setState(() {
      _batchRunId = null;
      _lastResult = null;
      _leafKey = null;
      _error = null;
      _markdownFiles.clear();
      _videoUrlController.clear();
      _transcriptController.clear();
    });
  }

  @override
  Widget build(BuildContext context) {
    final importableFileCount = _markdownFiles
        .where(
          (item) =>
              item.status == _MarkdownImportStatus.ready ||
              item.status == _MarkdownImportStatus.failed,
        )
        .length;
    final alreadyPresentFileCount = _markdownFiles
        .where((item) => item.status == _MarkdownImportStatus.alreadyPresent)
        .length;
    return AppShell(
      title: 'นำเข้า Transcript',
      currentRoute: '/admin-transcript-import',
      isAdmin: true,
      actions: [
        IconButton(
          onPressed: _submitting ? null : _startNewBatch,
          icon: const Icon(Icons.create_new_folder_outlined),
          tooltip: 'เริ่มชุดนำเข้าใหม่',
        ),
        IconButton(
          onPressed: () => Navigator.pushNamed(
            context,
            '/admin-dataset-review',
          ),
          icon: const Icon(Icons.fact_check_outlined),
          tooltip: 'เปิดคิวตรวจสอบ Dataset',
        ),
      ],
      child: _loadingTaxonomy
          ? const Center(child: CircularProgressIndicator())
          : _taxonomy.isEmpty
              ? ErrorStateView(
                  message: 'ไม่พบหมวดหมู่ Taxonomy ที่เปิดใช้งาน',
                  onRetry: _loadTaxonomy,
                )
              : ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    Center(
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 1000),
                        child: Form(
                          key: _formKey,
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              _BatchBand(
                                runId: _batchRunId,
                                candidateCount:
                                    _lastResult?.candidateCount ?? 0,
                              ),
                              if (_error != null) ...[
                                const SizedBox(height: 12),
                                MaterialBanner(
                                  content: Text(_error!),
                                  actions: [
                                    TextButton(
                                      onPressed: () =>
                                          setState(() => _error = null),
                                      child: const Text('ปิด'),
                                    ),
                                  ],
                                ),
                              ],
                              const SizedBox(height: 16),
                              SegmentedButton<_TranscriptInputMode>(
                                segments: const [
                                  ButtonSegment(
                                    value: _TranscriptInputMode.files,
                                    icon: Icon(Icons.file_upload_outlined),
                                    label: Text('ไฟล์ Markdown'),
                                  ),
                                  ButtonSegment(
                                    value: _TranscriptInputMode.manual,
                                    icon: Icon(Icons.edit_note_outlined),
                                    label: Text('วางข้อความเอง'),
                                  ),
                                ],
                                selected: {_inputMode},
                                onSelectionChanged: _submitting
                                    ? null
                                    : (values) => setState(
                                          () => _inputMode = values.first,
                                        ),
                              ),
                              const SizedBox(height: 12),
                              if (_inputMode ==
                                  _TranscriptInputMode.manual) ...[
                                TextFormField(
                                  controller: _videoUrlController,
                                  decoration: const InputDecoration(
                                    labelText: 'URL ต้นทาง YouTube',
                                    prefixIcon: Icon(Icons.link),
                                  ),
                                  keyboardType: TextInputType.url,
                                  validator: (value) {
                                    final raw = value?.trim() ?? '';
                                    if (raw.isEmpty) {
                                      return 'กรุณากรอก URL ของ YouTube';
                                    }
                                    final uri = Uri.tryParse(raw);
                                    if (uri == null || !uri.hasScheme) {
                                      return 'กรุณากรอก URL ของ YouTube ให้ถูกต้อง';
                                    }
                                    return null;
                                  },
                                ),
                                const SizedBox(height: 12),
                              ],
                              LayoutBuilder(
                                builder: (context, constraints) {
                                  final width = constraints.maxWidth < 720
                                      ? constraints.maxWidth
                                      : (constraints.maxWidth - 24) / 3;
                                  return Wrap(
                                    spacing: 12,
                                    runSpacing: 12,
                                    children: [
                                      SizedBox(
                                        width: width,
                                        child: DropdownButtonFormField<String>(
                                          key: ValueKey(
                                            'category-${_leafKey ?? 'none'}',
                                          ),
                                          initialValue: _leafKey,
                                          isExpanded: true,
                                          decoration: const InputDecoration(
                                            labelText: 'หมวดหมู่ที่เสนอ',
                                            hintText: 'เลือกหมวดหมู่',
                                          ),
                                          items: _taxonomy
                                              .map(
                                                (leaf) => DropdownMenuItem(
                                                  value: leaf.leafKey,
                                                  child: Text(
                                                    leaf.path,
                                                    overflow:
                                                        TextOverflow.ellipsis,
                                                  ),
                                                ),
                                              )
                                              .toList(),
                                          onChanged: _submitting
                                              ? null
                                              : (value) => setState(() {
                                                    _leafKey = value;
                                                    _error = null;
                                                  }),
                                        ),
                                      ),
                                      SizedBox(
                                        width: width,
                                        child: DropdownButtonFormField<String>(
                                          initialValue: _language,
                                          decoration: const InputDecoration(
                                            labelText: 'ภาษา Transcript',
                                          ),
                                          items: const [
                                            DropdownMenuItem(
                                              value: 'th',
                                              child: Text('ภาษาไทย'),
                                            ),
                                            DropdownMenuItem(
                                              value: 'en',
                                              child: Text('ภาษาอังกฤษ'),
                                            ),
                                          ],
                                          onChanged: (value) {
                                            if (value != null) {
                                              setState(() => _language = value);
                                            }
                                          },
                                        ),
                                      ),
                                      SizedBox(
                                        width: width,
                                        child: DropdownButtonFormField<String>(
                                          initialValue: _captionType,
                                          isExpanded: true,
                                          decoration: const InputDecoration(
                                            labelText: 'ประเภทคำบรรยาย',
                                          ),
                                          items: const [
                                            DropdownMenuItem(
                                              value: 'unspecified',
                                              child: Text('ไม่ระบุ'),
                                            ),
                                            DropdownMenuItem(
                                              value: 'manual',
                                              child: Text('คำบรรยายที่ทำเอง'),
                                            ),
                                            DropdownMenuItem(
                                              value: 'auto_generated',
                                              child: Text('สร้างอัตโนมัติ'),
                                            ),
                                          ],
                                          onChanged: (value) {
                                            if (value != null) {
                                              setState(
                                                () => _captionType = value,
                                              );
                                            }
                                          },
                                        ),
                                      ),
                                    ],
                                  );
                                },
                              ),
                              const SizedBox(height: 12),
                              SegmentedButton<String>(
                                segments: const [
                                  ButtonSegment(
                                    value: 'classification_diverse',
                                    icon: Icon(Icons.category_outlined),
                                    label: Text('ข้อมูลจำแนกหมวด'),
                                  ),
                                  ButtonSegment(
                                    value: 'recommendation_high_performance',
                                    icon: Icon(Icons.trending_up),
                                    label: Text('คลิปผลตอบรับสูง'),
                                  ),
                                ],
                                selected: {_strategy},
                                onSelectionChanged: (values) =>
                                    setState(() => _strategy = values.first),
                              ),
                              const SizedBox(height: 12),
                              if (_inputMode == _TranscriptInputMode.files)
                                _MarkdownFileQueue(
                                  items: _markdownFiles,
                                  reading: _readingMarkdown,
                                  submitting: _submitting,
                                  onPickFiles: _pickMarkdownTranscript,
                                  onRemove: _removeMarkdownFile,
                                )
                              else
                                TextFormField(
                                  controller: _transcriptController,
                                  minLines: 12,
                                  maxLines: 24,
                                  decoration: const InputDecoration(
                                    labelText: 'Transcript ต้นทางฉบับเต็ม',
                                    alignLabelWithHint: true,
                                  ),
                                  validator: (value) {
                                    final raw = value?.trim() ?? '';
                                    if (raw.length < 80) {
                                      return 'Paste the complete transcript (at least 80 characters)';
                                    }
                                    return null;
                                  },
                                ),
                              const SizedBox(height: 16),
                              FilledButton.icon(
                                onPressed: _submitting ||
                                        _leafKey == null ||
                                        (_inputMode ==
                                                _TranscriptInputMode.files &&
                                            importableFileCount == 0)
                                    ? null
                                    : _submit,
                                icon: _submitting
                                    ? const SizedBox.square(
                                        dimension: 18,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                        ),
                                      )
                                    : const Icon(Icons.playlist_add_check),
                                label: Text(
                                  _submitting
                                      ? 'กำลังนำเข้าข้อมูล'
                                      : _leafKey == null
                                          ? 'เลือกหมวดหมู่ก่อน'
                                          : _inputMode ==
                                                  _TranscriptInputMode.files
                                              ? importableFileCount == 0
                                                  ? _markdownFiles.isEmpty
                                                      ? 'เลือกไฟล์ที่จะนำเข้า'
                                                      : alreadyPresentFileCount >
                                                              0
                                                          ? 'นำเข้าเสร็จแล้ว (มีในระบบเดิม $alreadyPresentFileCount ไฟล์)'
                                                          : 'นำเข้าไฟล์ที่เลือกครบแล้ว'
                                                  : 'ตรวจและนำเข้า $importableFileCount ไฟล์'
                                              : 'ตรวจและเพิ่มเข้าคิวตรวจสอบ',
                                ),
                              ),
                              if (_inputMode == _TranscriptInputMode.manual &&
                                  _lastResult != null) ...[
                                const SizedBox(height: 16),
                                _ValidatedCandidateBand(
                                  result: _lastResult!,
                                  onReview: () => Navigator.pushNamed(
                                    context,
                                    '/admin-dataset-review',
                                  ),
                                ),
                              ],
                            ],
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
    );
  }
}

class _MarkdownFileQueue extends StatelessWidget {
  const _MarkdownFileQueue({
    required this.items,
    required this.reading,
    required this.submitting,
    required this.onPickFiles,
    required this.onRemove,
  });

  final List<_MarkdownImportItem> items;
  final bool reading;
  final bool submitting;
  final VoidCallback onPickFiles;
  final ValueChanged<_MarkdownImportItem> onRemove;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            OutlinedButton.icon(
              onPressed: reading || submitting ? null : onPickFiles,
              icon: reading
                  ? const SizedBox.square(
                      dimension: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.file_upload_outlined),
              label: Text(reading ? 'กำลังอ่านไฟล์' : 'เลือกไฟล์ .md'),
            ),
            if (items.isNotEmpty) ...[
              const Spacer(),
              Text(
                '${items.length} selected',
                style: theme.textTheme.bodySmall,
              ),
            ],
          ],
        ),
        const SizedBox(height: 8),
        Container(
          decoration: BoxDecoration(
            border: Border.all(color: theme.colorScheme.outlineVariant),
            borderRadius: BorderRadius.circular(6),
          ),
          child: items.isEmpty
              ? Padding(
                  padding: const EdgeInsets.all(20),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        Icons.description_outlined,
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                      const SizedBox(width: 8),
                      Text(
                        'ยังไม่ได้เลือกไฟล์ Markdown',
                        style: TextStyle(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                )
              : Column(
                  children: [
                    for (var index = 0; index < items.length; index++) ...[
                      _MarkdownFileRow(
                        item: items[index],
                        submitting: submitting,
                        onRemove: () => onRemove(items[index]),
                      ),
                      if (index < items.length - 1)
                        Divider(
                          height: 1,
                          color: theme.colorScheme.outlineVariant,
                        ),
                    ],
                  ],
                ),
        ),
      ],
    );
  }
}

class _MarkdownFileRow extends StatelessWidget {
  const _MarkdownFileRow({
    required this.item,
    required this.submitting,
    required this.onRemove,
  });

  final _MarkdownImportItem item;
  final bool submitting;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final statusLabel = switch (item.status) {
      _MarkdownImportStatus.ready => 'พร้อมนำเข้า',
      _MarkdownImportStatus.importing => 'กำลังนำเข้า',
      _MarkdownImportStatus.imported => 'นำเข้าแล้ว',
      _MarkdownImportStatus.alreadyPresent => 'มีในระบบแล้ว',
      _MarkdownImportStatus.failed => 'ล้มเหลว',
    };
    final statusColor = switch (item.status) {
      _MarkdownImportStatus.ready => theme.colorScheme.onSurfaceVariant,
      _MarkdownImportStatus.importing => theme.colorScheme.primary,
      _MarkdownImportStatus.imported => Colors.green.shade700,
      _MarkdownImportStatus.alreadyPresent => Colors.blue.shade700,
      _MarkdownImportStatus.failed => theme.colorScheme.error,
    };
    final title = item.document.sourceTitle?.trim();

    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 10, 6, 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: item.status == _MarkdownImportStatus.importing
                ? const SizedBox.square(
                    dimension: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : Icon(Icons.description_outlined, color: statusColor),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title == null || title.isEmpty ? item.fileName : title,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  item.fileName,
                  style: theme.textTheme.bodySmall,
                ),
                const SizedBox(height: 4),
                Wrap(
                  spacing: 8,
                  runSpacing: 4,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    Text(
                      statusLabel,
                      style: theme.textTheme.labelMedium?.copyWith(
                        color: statusColor,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    Text(
                      '${item.document.transcript.length} characters',
                      style: theme.textTheme.bodySmall,
                    ),
                  ],
                ),
                const SizedBox(height: 2),
                Text(
                  item.document.sourceUrl ?? '',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
                if (item.error != null) ...[
                  const SizedBox(height: 4),
                  Text(
                    item.error!,
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: item.status == _MarkdownImportStatus.alreadyPresent
                          ? Colors.blue.shade700
                          : theme.colorScheme.error,
                    ),
                  ),
                ],
              ],
            ),
          ),
          IconButton(
            onPressed: submitting ? null : onRemove,
            icon: const Icon(Icons.close),
            tooltip: 'นำออกจากรายการ',
          ),
        ],
      ),
    );
  }
}

class _BatchBand extends StatelessWidget {
  const _BatchBand({required this.runId, required this.candidateCount});

  final int? runId;
  final int candidateCount;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        border: Border.all(color: Theme.of(context).dividerColor),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          const Icon(Icons.inventory_2_outlined),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              runId == null ? 'ชุดนำเข้า NotebookLM ใหม่' : 'ชุดนำเข้า $runId',
              style: Theme.of(context).textTheme.titleSmall,
            ),
          ),
          if (runId != null) Text('$candidateCount รายการ'),
        ],
      ),
    );
  }
}

class _ValidatedCandidateBand extends StatelessWidget {
  const _ValidatedCandidateBand({required this.result, required this.onReview});

  final NotebookLMImportResult result;
  final VoidCallback onReview;

  String _duration(int seconds) {
    final hours = seconds ~/ 3600;
    final minutes = (seconds % 3600) ~/ 60;
    final remaining = seconds % 60;
    if (hours > 0) return '${hours}h ${minutes}m ${remaining}s';
    return '${minutes}m ${remaining}s';
  }

  @override
  Widget build(BuildContext context) {
    final candidate = result.candidate;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        border: Border.all(color: Colors.green.shade700),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.verified_outlined, color: Colors.green.shade700),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  candidate.title,
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            '${candidate.channelTitle} | '
            '${_duration(candidate.durationSeconds)}',
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              Chip(label: Text(candidate.proposedLeafKey)),
              Chip(label: Text(candidate.transcriptLanguage.toUpperCase())),
              const Chip(label: Text('Transcript ทั้งคลิป')),
              Chip(label: Text(candidate.licenseName)),
              const Chip(label: Text('ใช้เพื่อการศึกษาเท่านั้น')),
            ],
          ),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: onReview,
            icon: const Icon(Icons.fact_check_outlined),
            label: const Text('เปิดคิวตรวจสอบ'),
          ),
        ],
      ),
    );
  }
}
