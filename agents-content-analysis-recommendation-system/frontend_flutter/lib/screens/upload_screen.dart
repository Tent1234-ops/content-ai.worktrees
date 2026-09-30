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
  int _uploadProgress = 0;
  String _statusMessage = '';
  String? _suggestedTopic;
  bool _hasReadRouteArgs = false;
  Map<String, dynamic>? _revisionContext;
  String? _revisionClientRequestId;
  String? _revisionJobId;
  bool _revisionCanRetry = false;

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
          _error =
              'Cannot read selected file on this platform. Please try a different browser or device.';
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
        _uploadProgress = 0;
        _statusMessage =
            'File ready ($fileSizeMB MB, ${_formatDuration(selectedDuration!)})';
      });

      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Selected: ${selectedFile.name}'),
          duration: const Duration(seconds: 2),
        ),
      );
    } catch (e) {
      if (mounted) {
        setState(() => _error = 'Error picking file: ${e.toString()}');
      }
    }
  }

  Future<void> _uploadAndAnalyze() async {
    if (_selectedFileName == null ||
        (_selectedFilePath == null &&
            _selectedFileBytes == null &&
            _selectedFileStream == null)) {
      setState(() => _error = 'Please select a file first');
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
      _uploadProgress = 5;
      _statusMessage = 'Uploading video...';
    });

    try {
      if (!await _loadSettings()) return;
      if (_selectedDuration == null ||
          !_settings!.acceptsDuration(_selectedDuration!)) {
        await _showVideoTooLongDialog(_selectedDuration);
        return;
      }
      final revision = _revisionContext;
      final jobId = revision == null
          ? await _repository.startAnalyzeAndSaveVideo(
              fileName: _selectedFileName!,
              filePath: _selectedFilePath,
              fileBytes: _selectedFileBytes,
              fileStream: _selectedFileStream,
              fileSize: _selectedFileSize,
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
        _uploadProgress = 10;
        _statusMessage = 'Queued job $jobId';
      });

      final response =
          await _pollAnalysisJob(jobId, revision: revision != null);

      if (!mounted) return;

      setState(() {
        _uploadProgress = 100;
        _statusMessage = 'Analysis complete!';
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
        _statusMessage = 'Error: ${error.toString()}';
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
        if (job.status == 'queued') {
          _uploadProgress = job.progress > 10 ? job.progress : 10;
        } else if (job.progress > 0) {
          _uploadProgress = job.progress.clamp(0, 100).toInt();
        }
        if (job.message.isNotEmpty) {
          _statusMessage = job.message;
        } else if (job.status == 'queued') {
          _statusMessage = 'Queued for analysis...';
        } else if (job.status == 'running') {
          _statusMessage = _messageForStage(job.stage);
        } else {
          _statusMessage = 'Job status: ${job.status}';
        }
      });

      if (job.isComplete) {
        final result = job.result;
        if (result == null) {
          throw Exception('Analysis completed but no result was returned.');
        }
        return result;
      }

      if (job.isFailed) {
        if (revision) _revisionCanRetry = true;
        if (job.status == 'not_found') {
          throw Exception(
            'Analysis job was lost because the backend restarted. Please submit the clip again.',
          );
        }
        throw Exception(job.error ?? 'Analysis failed.');
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
        return 'Extracting audio from full video...';
      case 'transcribing':
        return 'Generating full video transcript...';
      case 'normalizing_transcript':
        return 'Cleaning transcript...';
      case 'classifying':
        return 'Classifying content type...';
      case 'recommending':
        return 'Building recommendations...';
      case 'saving':
        return 'Saving to My Ideas...';
      default:
        return 'Analyzing video...';
    }
  }

  void _clearSelection() {
    setState(() {
      _selectedFileName = null;
      _selectedFilePath = null;
      _selectedFileBytes = null;
      _selectedFileStream = null;
      _selectedFileSize = null;
      _selectedDuration = null;
      _uploadProgress = 0;
      _statusMessage = '';
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
    final hasFile = _selectedFileName != null;

    return AppShell(
      title: 'Analyze My Clip',
      currentRoute: '/upload',
      isAdmin: auth.isAdmin,
      child: RefreshIndicator(
        onRefresh: () async {
          _clearSelection();
          await _loadSettings();
        },
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: ListView(
            children: [
              if (_settingsLoading) const LinearProgressIndicator(),
              if (_settingsError != null)
                ErrorStateView(
                    message: _settingsError!, onRetry: _loadSettings),
              if (_settings != null)
                Padding(
                    padding: const EdgeInsets.only(bottom: 16),
                    child: Text(
                      'อัปโหลดสูงสุด ${_settings!.uploadMaxDurationSeconds} วินาที · '
                      'Whisper ${_settings!.asrModel} · ช่วงเปิดคลิป ${_settings!.hookDurationSeconds} วินาที',
                    )),
              // Header Card
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Icon(
                            Icons.video_camera_back_outlined,
                            size: 28,
                            color: Theme.of(context).primaryColor,
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  'Analyze Your Clip',
                                  style: TextStyle(
                                    fontWeight: FontWeight.bold,
                                    fontSize: 18,
                                  ),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  'Upload a video to get content analysis',
                                  style: Theme.of(context).textTheme.bodySmall,
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      const Divider(height: 1),
                      const SizedBox(height: 12),
                      const Text(
                        'What we analyze:',
                        style: TextStyle(fontWeight: FontWeight.w600),
                      ),
                      const SizedBox(height: 8),
                      const _AnalysisFeature(
                        icon: Icons.subtitles_outlined,
                        title: 'Transcript',
                        description: 'Auto-generated from your video',
                      ),
                      const SizedBox(height: 8),
                      const _AnalysisFeature(
                        icon: Icons.category_outlined,
                        title: 'Content Classification',
                        description: 'AI-predicted domain/category',
                      ),
                      const SizedBox(height: 8),
                      const _AnalysisFeature(
                        icon: Icons.key_outlined,
                        title: 'Keywords & Gaps',
                        description:
                            'Missing keywords compared to top performers',
                      ),
                      const SizedBox(height: 8),
                      const _AnalysisFeature(
                        icon: Icons.lightbulb_outline,
                        title: 'Hook Suggestions',
                        description:
                            'Opening-segment keywords based on the configured hook duration',
                      ),
                      const SizedBox(height: 8),
                      const _AnalysisFeature(
                        icon: Icons.schedule_outlined,
                        title: 'Duration Recommendation',
                        description: 'Optimal video length for your domain',
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 24),
              if (_suggestedTopic != null)
                Card(
                  color: Theme.of(context).colorScheme.primaryContainer,
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Suggested trend to analyze',
                          style: Theme.of(context)
                              .textTheme
                              .titleMedium
                              ?.copyWith(fontWeight: FontWeight.bold),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          'Upload a clip related to "$_suggestedTopic" to get recommendations that match this trend.',
                          style: Theme.of(context).textTheme.bodyMedium,
                        ),
                      ],
                    ),
                  ),
                ),
              if (_suggestedTopic != null) const SizedBox(height: 16),
              if (_revisionContext != null) ...[
                _RevisionUploadContext(data: _revisionContext!),
                const SizedBox(height: 16),
              ],

              // Upload Section
              if (!hasFile) ...[
                FilledButton.icon(
                  onPressed: _loading ||
                          _settingsLoading ||
                          _settings?.asrReady != true
                      ? null
                      : _pickFile,
                  icon: const Icon(Icons.upload_file),
                  label: const Text('Pick a Video File'),
                  style: FilledButton.styleFrom(
                    padding: const EdgeInsets.symmetric(vertical: 14),
                  ),
                ),
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  onPressed: _loading ||
                          _settingsLoading ||
                          _settings?.asrReady != true
                      ? null
                      : _pickFile,
                  icon: const Icon(Icons.cloud_upload_outlined),
                  label: const Text('Or tap to browse'),
                ),
              ] else ...[
                // Selected File Card
                Card(
                  color: Theme.of(context).colorScheme.primaryContainer,
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            const Icon(Icons.check_circle),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    _selectedFileName!,
                                    style:
                                        Theme.of(context).textTheme.titleSmall,
                                    maxLines: 2,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    _statusMessage,
                                    style:
                                        Theme.of(context).textTheme.bodySmall,
                                  ),
                                ],
                              ),
                            ),
                            if (!_loading)
                              IconButton(
                                icon: const Icon(Icons.close),
                                onPressed: _clearSelection,
                                tooltip: 'Clear selection',
                              ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 16),

                // Upload Progress
                if (_loading) ...[
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        _statusMessage,
                        style: Theme.of(context).textTheme.bodyMedium,
                      ),
                      const SizedBox(height: 8),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(8),
                        child: LinearProgressIndicator(
                          value: _uploadProgress / 100,
                          minHeight: 8,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        '$_uploadProgress% complete',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                ] else ...[
                  FilledButton.icon(
                    onPressed: _uploadAndAnalyze,
                    icon: const Icon(Icons.analytics_outlined),
                    label: const Text('Analyze Now'),
                    style: FilledButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 14),
                    ),
                  ),
                  const SizedBox(height: 12),
                  OutlinedButton(
                    onPressed: _clearSelection,
                    child: const Text('Choose Different File'),
                  ),
                ],
              ],

              const SizedBox(height: 16),

              // Error State
              if (_error != null)
                ErrorStateView(
                  message: _error!,
                  onRetry: _revisionCanRetry
                      ? _retryRevision
                      : hasFile
                          ? _uploadAndAnalyze
                          : _pickFile,
                ),

              const SizedBox(height: 16),

              // Tips Card
              if (!_loading)
                Card(
                  color: Theme.of(context).colorScheme.surfaceContainerHighest,
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Icon(
                              Icons.info_outline,
                              size: 20,
                              color: Theme.of(context)
                                  .colorScheme
                                  .onSurfaceVariant,
                            ),
                            const SizedBox(width: 8),
                            Text(
                              'Tips for better results',
                              style: Theme.of(context).textTheme.labelLarge,
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        const _TipRow(
                            text: 'Use clear audio for better transcription'),
                        const SizedBox(height: 8),
                        const _TipRow(
                          text: 'MP4, WebM, or MOV formats work best',
                        ),
                      ],
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
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

class _AnalysisFeature extends StatelessWidget {
  const _AnalysisFeature({
    required this.icon,
    required this.title,
    required this.description,
  });

  final IconData icon;
  final String title;
  final String description;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 20, color: Theme.of(context).primaryColor),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: Theme.of(context).textTheme.labelMedium,
              ),
              const SizedBox(height: 2),
              Text(
                description,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _TipRow extends StatelessWidget {
  const _TipRow({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 3),
          child: Icon(
            Icons.check,
            size: 18,
            color: Theme.of(context).colorScheme.primary,
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            text,
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ),
      ],
    );
  }
}
