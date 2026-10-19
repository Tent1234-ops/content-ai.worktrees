import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'dart:math';

import '../models/recommendation_result.dart';
import '../models/analysis_settings.dart';
import '../repositories/analysis_repository.dart';
import '../services/video_metadata_reader.dart';
import '../state/auth_scope.dart';
import '../widgets/app_shell.dart';
import '../widgets/state_widgets.dart';
import '../widgets/workspace_widgets.dart';
import '../widgets/analysis_progress.dart';
import 'result_screen.dart';

class UploadScreen extends StatefulWidget {
  const UploadScreen({super.key, this.repository});
  final AnalysisRepository? repository;

  @override
  State<UploadScreen> createState() => _UploadScreenState();
}

class _UploadScreenState extends State<UploadScreen> {
  late final AnalysisRepository _repository;
  AnalysisSettings? _settings;
  String? _settingsError;
  bool _settingsLoading = true;
  String? _error;
  bool _loading = false;
  String? _selectedFileName;
  String? _selectedFilePath;
  Uint8List? _selectedFileBytes;
  Stream<List<int>>? _selectedFileStream;
  int? _selectedFileSize;
  Duration? _selectedDuration;
  String _statusMessage = '';
  String _jobStage = '';
  final Set<String> _observedStages = {};
  String? _suggestedTopic;
  bool _hasReadRouteArgs = false;
  Map<String, dynamic>? _revisionContext;
  String? _revisionClientRequestId;
  String? _revisionJobId;
  bool _revisionCanRetry = false;
  String _confirmedFormat = '';
  String _referenceAgeContext = '';

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? AnalysisRepository();
    _loadSettings();
  }

  Future<bool> _loadSettings() async {
    setState(() {
      _settingsLoading = true;
      _settingsError = null;
    });
    try {
      final settings = await _repository.getSettings();
      if (!mounted) return false;
      setState(() {
        _settings = settings;
        if (!settings.asrReady) {
          _settingsError = 'โมเดลถอดเสียงยังไม่พร้อม กรุณาติดต่อผู้ดูแลระบบ';
        }
      });
      return settings.asrReady;
    } catch (error) {
      if (mounted) {
        setState(() {
          _settings = null;
          _settingsError = 'โหลดการตั้งค่าการวิเคราะห์ไม่สำเร็จ: $error';
        });
      }
      return false;
    } finally {
      if (mounted) setState(() => _settingsLoading = false);
    }
  }

  Future<void> _pickFile() async {
    try {
      if (!await _loadSettings()) return;
      final file = await FilePicker.platform.pickFiles(
        type: FileType.video,
        allowMultiple: false,
        withData: true,
      );

      if (file == null) {
        return;
      }

      final selectedFile = file.files.single;
      final selectedBytes = selectedFile.bytes;
      final selectedStream = selectedFile.readStream;
      String? selectedPath;
      if (!kIsWeb) {
        try {
          selectedPath = selectedFile.path;
        } catch (_) {
          selectedPath = null;
        }
      }

      if (selectedPath == null &&
          selectedBytes == null &&
          selectedStream == null) {
        setState(() {
          _error = 'ไม่สามารถอ่านไฟล์ที่เลือกได้ กรุณาลองใช้ไฟล์อื่น';
        });
        return;
      }

      Duration? selectedDuration;
      try {
        selectedDuration = await readVideoDuration(
          fileName: selectedFile.name,
          filePath: selectedPath,
          fileBytes: selectedBytes,
        );
      } catch (_) {
        selectedDuration = null;
      }

      if (!mounted) return;
      if (selectedDuration == null) {
        await _showMetadataErrorDialog();
        return;
      }
      if (!_settings!.acceptsDuration(selectedDuration)) {
        await _showVideoTooLongDialog(selectedDuration);
        return;
      }

      final fileSizeMB = (selectedFile.size / (1024 * 1024)).toStringAsFixed(1);

      setState(() {
        _selectedFileName = selectedFile.name;
        _selectedFilePath = selectedPath;
        _selectedFileBytes = selectedBytes;
        _selectedFileStream = selectedStream;
        _selectedFileSize = selectedFile.size;
        _selectedDuration = selectedDuration;
        _error = null;
        _statusMessage =
            'ไฟล์พร้อมวิเคราะห์ ($fileSizeMB MB · ${_formatDuration(selectedDuration!)})';
      });

      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('เลือกไฟล์ ${selectedFile.name} แล้ว'),
          duration: const Duration(seconds: 2),
        ),
      );
    } catch (e) {
      if (mounted) {
        setState(() => _error = 'เลือกไฟล์ไม่สำเร็จ: ${e.toString()}');
      }
    }
  }

  Future<void> _uploadAndAnalyze() async {
    if (_selectedFileName == null ||
        (_selectedFilePath == null &&
            _selectedFileBytes == null &&
            _selectedFileStream == null)) {
      setState(() => _error = 'กรุณาเลือกไฟล์ก่อนเริ่มวิเคราะห์');
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
      _statusMessage = 'กำลังตรวจการตั้งค่า...';
      _jobStage = 'preparing';
      _observedStages.clear();
    });

    try {
      if (!await _loadSettings()) return;
      if (_selectedDuration == null ||
          !_settings!.acceptsDuration(_selectedDuration!)) {
        await _showVideoTooLongDialog(_selectedDuration);
        return;
      }
      final revision = _revisionContext;
      if (revision == null &&
          _confirmedFormat.isNotEmpty &&
          !_settings!.outcomeContexts.any((item) =>
              item['confirmed_format'] == _confirmedFormat &&
              item['frozen_age_context'] == _referenceAgeContext)) {
        setState(() => _error =
            'กรุณาเลือกบริบทอ้างอิงที่พร้อมใช้งาน หรือเลือกไม่ประเมินผลตอบรับ');
        return;
      }
      if (!mounted) return;
      setState(() {
        _statusMessage = 'กำลังอัปโหลดวิดีโอ...';
        _jobStage = 'uploading';
        _observedStages.add('uploading');
      });
      final jobId = revision == null
          ? await _repository.startAnalyzeAndSaveVideo(
              fileName: _selectedFileName!,
              filePath: _selectedFilePath,
              fileBytes: _selectedFileBytes,
              fileStream: _selectedFileStream,
              fileSize: _selectedFileSize,
              confirmedFormat: _confirmedFormat,
              referenceAgeContext: _referenceAgeContext,
            )
          : await _repository.startRevisionVideo(
              fileName: _selectedFileName!,
              filePath: _selectedFilePath,
              fileBytes: _selectedFileBytes,
              fileStream: _selectedFileStream,
              fileSize: _selectedFileSize,
              context: revision,
              clientRequestId: _revisionClientRequestId!,
            );
      _revisionJobId = revision == null ? null : jobId;

      if (!mounted) return;
      setState(() {
        _statusMessage = 'รับงานวิเคราะห์แล้ว กำลังรอประมวลผล';
      });

      final response =
          await _pollAnalysisJob(jobId, revision: revision != null);

      if (!mounted) return;

      setState(() {
        _statusMessage = 'วิเคราะห์เสร็จแล้ว';
      });

      await Future.delayed(const Duration(milliseconds: 500));

      if (!mounted) return;

      Navigator.pushReplacementNamed(
        context,
        '/result',
        arguments: ResultScreenArgs(initialData: response),
      );
    } catch (error) {
      if (!mounted) return;
      if (_isDurationLimitError(error)) {
        await _loadSettings();
        if (!mounted) return;
        await _showVideoTooLongDialog(_selectedDuration);
        if (mounted) _clearSelection();
        return;
      }
      setState(() {
        _error = error.toString();
        _statusMessage = 'วิเคราะห์ไม่สำเร็จ';
      });
    } finally {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }

  Future<AnalysisResultViewData> _pollAnalysisJob(String jobId,
      {bool revision = false}) async {
    while (true) {
      final job = revision
          ? await _repository.getRevisionJob(jobId)
          : await _repository.getAnalysisJob(jobId);
      if (!mounted) {
        throw Exception('Upload screen was closed.');
      }

      setState(() {
        _jobStage = job.stage.isEmpty ? job.status : job.stage;
        _observedStages.add(_jobStage);
        if (job.message.isNotEmpty) {
          _statusMessage = _localizedJobMessage(job.message, job.stage);
        } else if (job.status == 'queued') {
          _statusMessage = 'กำลังรอคิววิเคราะห์...';
        } else if (job.status == 'running') {
          _statusMessage = _messageForStage(job.stage);
        } else {
          _statusMessage = 'สถานะงาน: ${job.status}';
        }
      });

      if (job.isComplete) {
        final result = job.result;
        if (result == null) {
          throw Exception('งานวิเคราะห์เสร็จแต่ไม่พบผลลัพธ์');
        }
        return result;
      }

      if (job.isFailed) {
        if (revision) _revisionCanRetry = true;
        if (job.status == 'not_found') {
          throw Exception(
            'งานวิเคราะห์หายหลังระบบเริ่มใหม่ กรุณาส่งคลิปอีกครั้ง',
          );
        }
        throw Exception(job.error ?? 'วิเคราะห์คลิปไม่สำเร็จ');
      }
      if (job.isInterrupted) {
        _revisionCanRetry = revision;
        throw Exception(
            'งานหยุดเพราะ Backend รีสตาร์ต สามารถกดลองใหม่โดยใช้ไฟล์และแผนเดิมได้');
      }

      await Future.delayed(const Duration(seconds: 2));
    }
  }

  Future<void> _retryRevision() async {
    final jobId = _revisionJobId;
    if (jobId == null) return;
    setState(() {
      _loading = true;
      _error = null;
      _revisionCanRetry = false;
      _statusMessage = 'กำลังส่งงานเดิมใหม่...';
      _jobStage = 'retrying';
      _observedStages.clear();
    });
    try {
      final accepted = await _repository.retryRevisionJob(jobId);
      _revisionJobId = accepted.jobId.isEmpty ? jobId : accepted.jobId;
      final result = await _pollAnalysisJob(_revisionJobId!, revision: true);
      if (!mounted) return;
      Navigator.pushReplacementNamed(context, '/result',
          arguments: ResultScreenArgs(initialData: result));
    } catch (error) {
      if (mounted) {
        setState(() {
          _error = error.toString();
          _revisionCanRetry = true;
        });
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  String _messageForStage(String stage) {
    switch (stage) {
      case 'extracting_audio':
        return 'กำลังแยกเสียงจากวิดีโอ...';
      case 'transcribing':
        return 'กำลังถอดเสียงทั้งคลิปเป็นข้อความ...';
      case 'normalizing_transcript':
        return 'กำลังปรับศัพท์ในข้อความถอดเสียง...';
      case 'classifying':
        return 'กำลังจำแนกหมวดหมู่คลิป...';
      case 'recommending':
        return 'กำลังสร้างคำแนะนำ...';
      case 'saving':
        return 'กำลังบันทึกผลวิเคราะห์...';
      default:
        return 'กำลังวิเคราะห์วิดีโอ...';
    }
  }

  String _localizedJobMessage(String message, String stage) {
    const knownMessages = {
      'queued': 'กำลังรอคิววิเคราะห์...',
      'running': 'กำลังวิเคราะห์วิดีโอ...',
      'complete': 'วิเคราะห์เสร็จแล้ว',
    };
    final normalized = message.trim().toLowerCase();
    if (knownMessages.containsKey(normalized)) {
      return knownMessages[normalized]!;
    }
    if (stage.isNotEmpty) return _messageForStage(stage);
    return message;
  }

  void _clearSelection() {
    setState(() {
      _selectedFileName = null;
      _selectedFilePath = null;
      _selectedFileBytes = null;
      _selectedFileStream = null;
      _selectedFileSize = null;
      _selectedDuration = null;
      _statusMessage = '';
      _jobStage = '';
      _observedStages.clear();
      _error = null;
      _revisionCanRetry = false;
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_hasReadRouteArgs) {
      final args = ModalRoute.of(context)?.settings.arguments;
      if (args is Map<String, dynamic>) {
        _suggestedTopic = args['suggestedTopic']?.toString();
        final revision = args['revisionContext'];
        if (revision is Map) {
          _revisionContext = Map<String, dynamic>.from(revision);
          _revisionClientRequestId =
              'revision-${DateTime.now().microsecondsSinceEpoch}-${Random.secure().nextInt(0x7fffffff)}';
        }
      }
      _hasReadRouteArgs = true;
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = AuthScope.of(context);
    final theme = Theme.of(context);
    final hasFile = _selectedFileName != null;
    final canPick =
        !_loading && !_settingsLoading && _settings?.asrReady == true;
    return AppShell(
      title: 'วิเคราะห์คลิปของฉัน',
      currentRoute: '/upload',
      isAdmin: auth.isAdmin,
      child: RefreshIndicator(
        onRefresh: () async {
          if (_loading) return;
          _clearSelection();
          await _loadSettings();
        },
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(24),
          children: [
            const PageHeader(title: 'วิเคราะห์คลิปของคุณ'),
            if (_settingsLoading) const LinearProgressIndicator(),
            if (_settingsError != null)
              ErrorStateView(message: _settingsError!, onRetry: _loadSettings),
            if (_settings != null) ...[
              Wrap(spacing: 8, runSpacing: 8, children: [
                StatusBadge(
                    label:
                        'สูงสุด ${_settings!.uploadMaxDurationSeconds} วินาที',
                    icon: Icons.timer_outlined),
                StatusBadge(
                    label: 'Whisper ${_settings!.asrModel}',
                    icon: Icons.graphic_eq),
                StatusBadge(
                    label:
                        'ช่วงเปิดคลิป ${_settings!.hookDurationSeconds} วินาที',
                    icon: Icons.play_circle_outline),
              ]),
              const SizedBox(height: 24),
            ],
            Card(
              margin: EdgeInsets.zero,
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: AnimatedSwitcher(
                  duration: const Duration(milliseconds: 180),
                  child: hasFile
                      ? Column(
                          key: const ValueKey('selected-video'),
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Row(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Icon(Icons.video_file_outlined,
                                      size: 36,
                                      color: theme.colorScheme.primary),
                                  const SizedBox(width: 16),
                                  Expanded(
                                      child: Column(
                                          crossAxisAlignment:
                                              CrossAxisAlignment.start,
                                          children: [
                                        Text(_selectedFileName!,
                                            style: theme.textTheme.titleMedium,
                                            maxLines: 3,
                                            overflow: TextOverflow.ellipsis),
                                        const SizedBox(height: 8),
                                        Text(
                                            '${((_selectedFileSize ?? 0) / (1024 * 1024)).toStringAsFixed(1)} MB'
                                            ' · ${_selectedDuration == null ? '-' : _formatDuration(_selectedDuration!)}'),
                                      ])),
                                  IconButton(
                                      tooltip: 'นำไฟล์ออก',
                                      onPressed:
                                          _loading ? null : _clearSelection,
                                      icon: const Icon(Icons.close)),
                                ]),
                            const SizedBox(height: 16),
                            const Align(
                                alignment: Alignment.centerLeft,
                                child: StatusBadge(
                                    label: 'ตรวจความยาวแล้ว',
                                    icon: Icons.check_circle_outline)),
                            const SizedBox(height: 24),
                            FilledButton.icon(
                              onPressed: canPick ? _uploadAndAnalyze : null,
                              icon: const Icon(Icons.auto_awesome_outlined),
                              label: Text(_loading
                                  ? 'กำลังวิเคราะห์'
                                  : 'เริ่มวิเคราะห์'),
                            ),
                            const SizedBox(height: 8),
                            OutlinedButton.icon(
                                onPressed: canPick
                                    ? () {
                                        _clearSelection();
                                        _pickFile();
                                      }
                                    : null,
                                icon: const Icon(Icons.swap_horiz),
                                label: const Text('เปลี่ยนไฟล์')),
                          ],
                        )
                      : SizedBox(
                          key: const ValueKey('choose-video'),
                          width: double.infinity,
                          child: Column(children: [
                            Icon(Icons.video_camera_back_outlined,
                                size: 56, color: theme.colorScheme.primary),
                            const SizedBox(height: 16),
                            Text('วิดีโอของคุณ',
                                style: theme.textTheme.titleLarge),
                            const SizedBox(height: 24),
                            FilledButton.icon(
                                onPressed: canPick ? _pickFile : null,
                                icon: const Icon(Icons.upload_file),
                                label: const Text('เลือกไฟล์วิดีโอ')),
                          ]),
                        ),
                ),
              ),
            ),
            if (_loading) ...[
              const SizedBox(height: 24),
              AnalysisProgress(
                  stage: _jobStage,
                  observedStages: _observedStages,
                  message: _statusMessage,
                  revision: _revisionContext != null),
            ],
            if (_error != null) ...[
              const SizedBox(height: 16),
              ErrorStateView(
                  message: _error!,
                  onRetry: _loading
                      ? null
                      : _revisionCanRetry
                          ? _retryRevision
                          : hasFile
                              ? _uploadAndAnalyze
                              : _pickFile),
            ],
            if (_suggestedTopic != null) ...[
              const SizedBox(height: 24),
              const SectionHeading(
                  title: 'หัวข้อเทรนด์ที่เลือกมา', icon: Icons.trending_up),
              const SizedBox(height: 8),
              Text(_suggestedTopic!),
            ],
            if (_revisionContext != null) ...[
              const SizedBox(height: 24),
              _RevisionUploadContext(data: _revisionContext!),
            ],
            if (_revisionContext == null && _settings != null) ...[
              const SizedBox(height: 32),
              const Divider(),
              const SizedBox(height: 16),
              const SectionHeading(
                  title: 'บริบทประเมินผลตอบรับ', icon: Icons.tune),
              const SizedBox(height: 16),
              _outcomeContextFields(),
            ],
            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }

  Widget _outcomeContextFields() {
    final contexts = _settings!.outcomeContexts;
    if (contexts.isEmpty && _confirmedFormat.isEmpty) {
      return const Text('ยังไม่มีโมเดลประเมินผลตอบรับที่ผ่านการตรวจรับ');
    }
    final formats =
        contexts.map((item) => item['confirmed_format'].toString()).toSet();
    final ages = contexts
        .where((item) => item['confirmed_format'] == _confirmedFormat)
        .map((item) => item['frozen_age_context'].toString())
        .toSet();
    const ageLabels = {
      'age_0_7d': 'น้อยกว่า 7 วัน',
      'age_7_30d': '7 ถึงน้อยกว่า 30 วัน',
      'age_30_90d': '30 ถึงน้อยกว่า 90 วัน',
      'age_90_365d': '90 ถึงน้อยกว่า 365 วัน',
      'age_365d_plus': '365 วันขึ้นไป',
    };
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Wrap(spacing: 8, runSpacing: 8, children: [
        for (final format in ['', ...formats])
          ChoiceChip(
            key: ValueKey('outcome-format-$format'),
            label: Text(format.isEmpty
                ? 'ไม่ประเมินผลตอบรับ'
                : format == 'short_form'
                    ? 'YouTube Shorts'
                    : 'วิดีโอปกติ'),
            selected: _confirmedFormat == format,
            onSelected: _loading
                ? null
                : (_) => setState(() {
                      _confirmedFormat = format;
                      _referenceAgeContext = '';
                    }),
          ),
      ]),
      if (_confirmedFormat.isNotEmpty) ...[
        const SizedBox(height: 16),
        const Text('อายุคลิปอ้างอิง ณ เวลาเก็บยอดวิว'),
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 8, children: [
          for (final age in ages)
            ChoiceChip(
              key: ValueKey('outcome-age-$_confirmedFormat-$age'),
              label: Text(ageLabels[age] ?? age),
              selected: _referenceAgeContext == age,
              onSelected: _loading
                  ? null
                  : (_) => setState(() => _referenceAgeContext = age),
            ),
        ]),
      ],
    ]);
  }
}

class _RevisionUploadContext extends StatelessWidget {
  const _RevisionUploadContext({required this.data});
  final Map<String, dynamic> data;

  @override
  Widget build(BuildContext context) {
    final topics = (data['selected_topics'] as List? ?? const [])
        .map((item) => item.toString())
        .where((item) => item.isNotEmpty)
        .toList();
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surfaceContainerLow,
          border: Border.all(color: Theme.of(context).dividerColor),
          borderRadius: BorderRadius.circular(6)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('อัปโหลดฉบับแก้ไข',
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Text('ต้นฉบับ: ${data['parent_title'] ?? '-'}'),
        Text('แผนฉบับ ${data['expected_plan_revision']} · '
            '${data['plan_saved_at'] ?? 'ไม่พบเวลาบันทึก'}'),
        const SizedBox(height: 8),
        Text(topics.isEmpty
            ? 'แผนนี้มีเฉพาะบันทึก ระบบจะวิเคราะห์คลิปใหม่โดยไม่มีการเทียบหัวข้ออัตโนมัติ'
            : 'หัวข้อที่จะตรวจ: ${topics.join(' / ')}'),
        const SizedBox(height: 8),
        const Text(
            'ผลจะอธิบายการเปลี่ยนแปลงของข้อความเท่านั้น ไม่ใช่คะแนนว่าคลิปดีขึ้นหรือจะได้รับยอดเพิ่ม'),
      ]),
    );
  }
}

extension on _UploadScreenState {
  Future<void> _showVideoTooLongDialog(Duration? duration) {
    final detail = duration == null
        ? ''
        : '\nความยาววิดีโอที่เลือก: ${_formatDuration(duration)}';
    return showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('วิดีโอยาวเกินกำหนด'),
        content: Text(_settings == null
            ? 'ความยาวเกินขีดจำกัดที่เซิร์ฟเวอร์กำหนด$detail'
            : 'อัปโหลดวิดีโอได้สูงสุด ${_settings!.uploadMaxDurationSeconds} วินาที$detail'),
        actions: [
          FilledButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('ตกลง'),
          ),
        ],
      ),
    );
  }

  Future<void> _showMetadataErrorDialog() {
    return showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('ไม่สามารถอ่านความยาววิดีโอได้'),
        content: const Text(
          'กรุณาเลือกไฟล์ MP4, WebM หรือ MOV ที่เบราว์เซอร์รองรับ',
        ),
        actions: [
          FilledButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('ตกลง'),
          ),
        ],
      ),
    );
  }

  bool _isDurationLimitError(Object error) {
    final message = error.toString().toLowerCase();
    return message.contains('maximum video duration');
  }

  String _formatDuration(Duration duration) {
    final minutes = duration.inMinutes;
    final seconds = duration.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$minutes:$seconds';
  }
}
