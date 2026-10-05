import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/dataset_review.dart';
import '../repositories/admin_repository.dart';
import '../widgets/app_shell.dart';
import '../widgets/state_widgets.dart';
import '../widgets/dataset_bulk_approval.dart';

class AdminDatasetReviewScreen extends StatefulWidget {
  const AdminDatasetReviewScreen({super.key, this.repository});

  final AdminRepository? repository;

  @override
  State<AdminDatasetReviewScreen> createState() =>
      _AdminDatasetReviewScreenState();
}

class _AdminDatasetReviewScreenState extends State<AdminDatasetReviewScreen> {
  late final AdminRepository _repository;
  final _searchController = TextEditingController();
  DatasetReviewQueueResult? _queue;
  String _leafKey = 'all';
  int _offset = 0;
  final int _limit = 12;
  bool _loading = false;
  String? _reviewingKey;
  int _loadRequestId = 0;
  String? _error;
  bool _bulkBusy = false;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? AdminRepository();
    _load();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final requestId = ++_loadRequestId;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final result = await _repository.listDatasetReviewQueue(
        limit: _limit,
        offset: _offset,
        status: 'pending',
        leafKey: _leafKey,
        search: _searchController.text,
      );
      if (!mounted || requestId != _loadRequestId) return;
      setState(() => _queue = result);
    } catch (error) {
      if (!mounted || requestId != _loadRequestId) return;
      setState(() => _error = error.toString());
    } finally {
      if (mounted && requestId == _loadRequestId) {
        setState(() => _loading = false);
      }
    }
  }

  String _candidateKey(DatasetReviewCandidate candidate) =>
      '${candidate.collectionRunId}:${candidate.youtubeId}';

  void _removeReviewedCandidate(
    DatasetReviewCandidate candidate,
    String decision, {
    bool includeOffPage = false,
  }) {
    final queue = _queue;
    if (queue == null) return;
    final key = _candidateKey(candidate);
    final remaining = queue.items
        .where((item) => _candidateKey(item) != key)
        .toList(growable: false);
    if (!includeOffPage && remaining.length == queue.items.length) return;
    final summary = queue.summary;
    _queue = DatasetReviewQueueResult(
      total: queue.total > 0 ? queue.total - 1 : 0,
      limit: queue.limit,
      offset: queue.offset,
      summary: DatasetReviewSummary(
        total: summary.total,
        pending: summary.pending > 0 ? summary.pending - 1 : 0,
        approved: summary.approved + (decision == 'approve' ? 1 : 0),
        rejected: summary.rejected + (decision == 'reject' ? 1 : 0),
      ),
      runs: queue.runs,
      taxonomy: queue.taxonomy,
      items: remaining,
    );
  }

  void _applyFilters() {
    setState(() => _offset = 0);
    _load();
  }

  Future<void> _openVideo(DatasetReviewCandidate candidate) async {
    final uri = Uri.tryParse(candidate.videoUrl);
    if (uri == null ||
        !await launchUrl(uri, mode: LaunchMode.externalApplication)) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('เปิดวิดีโอ YouTube ไม่สำเร็จ')),
      );
    }
  }

  Future<void> _review(
    DatasetReviewCandidate candidate,
    String decision,
  ) async {
    if (_reviewingKey != null || _bulkBusy) return;
    final queue = _queue;
    if (queue == null) return;
    final result = await showDialog<_ReviewDecision>(
      context: context,
      builder: (context) => _ReviewDialog(
        candidate: candidate,
        taxonomy: queue.taxonomy,
        initialDecision: decision,
      ),
    );
    if (result == null || !mounted) return;

    final candidateKey = _candidateKey(candidate);
    setState(() {
      _reviewingKey = candidateKey;
      _error = null;
    });
    try {
      final response = await _repository.reviewDatasetCandidate(
        candidate: candidate,
        decision: result.decision,
        reviewedLeafKey: result.reviewedLeafKey,
        transcriptQuality: result.transcriptQuality,
        notes: result.notes,
      );
      if (!mounted) return;
      if (response.reviewEventId == null ||
          response.collectionRunId != candidate.collectionRunId ||
          response.youtubeId != candidate.youtubeId ||
          response.decision != result.decision) {
        throw StateError(
          'The server did not confirm the review event. Please try again.',
        );
      }
      setState(() => _removeReviewedCandidate(candidate, result.decision));
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            result.decision == 'approve'
                ? 'Approved: ${candidate.title}'
                : 'Rejected: ${candidate.title}',
          ),
        ),
      );
      await _load();
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _reviewingKey = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final queue = _queue;
    return AppShell(
      title: 'ตรวจสอบ Dataset',
      currentRoute: '/admin-dataset-review',
      isAdmin: true,
      actions: [
        IconButton(
          onPressed: _loading || _bulkBusy ? null : _load,
          icon: const Icon(Icons.refresh),
          tooltip: 'โหลดรายการตรวจสอบใหม่',
        ),
      ],
      child: _error != null && queue == null
          ? ErrorStateView(message: _error!, onRetry: _load)
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  if (_loading) const LinearProgressIndicator(),
                  if (_error != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: MaterialBanner(
                        content: Text(_error!),
                        actions: [
                          TextButton(
                            onPressed: () => setState(() => _error = null),
                            child: const Text('ปิด'),
                          ),
                        ],
                      ),
                    ),
                  if (queue != null) ...[
                    _ReviewSummaryBand(summary: queue.summary),
                    const SizedBox(height: 16),
                    AbsorbPointer(
                        absorbing: _bulkBusy,
                        child: _ReviewFilters(
                          searchController: _searchController,
                          leafKey: _leafKey,
                          taxonomy: queue.taxonomy,
                          onLeafChanged: (value) {
                            setState(() => _leafKey = value);
                            _applyFilters();
                          },
                          onSearch: _applyFilters,
                        )),
                    const SizedBox(height: 16),
                    DatasetBulkApproval(
                        repository: _repository,
                        leafKey: _leafKey,
                        search: _searchController.text,
                        enabled: !_loading && _reviewingKey == null,
                        onBusyChanged: (busy) =>
                            setState(() => _bulkBusy = busy),
                        onReviewed: (candidate) => setState(() =>
                            _removeReviewedCandidate(candidate, 'approve',
                                includeOffPage: true)),
                        onFinished: () {
                          setState(() => _offset = 0);
                          _load();
                        }),
                    const SizedBox(height: 16),
                    _TaxonomyProgress(taxonomy: queue.taxonomy),
                    const SizedBox(height: 16),
                    if (queue.items.isEmpty)
                      const EmptyStateView(
                        title: 'ไม่มีข้อมูลรอตรวจสอบ',
                        message:
                            'ลองเปลี่ยนหมวดหมู่หรือนำเข้า Transcript เพิ่ม',
                        icon: Icons.fact_check_outlined,
                      )
                    else
                      ...queue.items.map(
                        (candidate) => _CandidateReviewCard(
                          candidate: candidate,
                          reviewing: _reviewingKey == _candidateKey(candidate),
                          actionsEnabled: _reviewingKey == null && !_bulkBusy,
                          onOpenVideo: () => _openVideo(candidate),
                          onApprove: () => _review(candidate, 'approve'),
                          onReject: () => _review(candidate, 'reject'),
                        ),
                      ),
                    PaginationBar(
                      offset: _offset,
                      limit: _limit,
                      total: queue.total,
                      onPrevious: _bulkBusy || _offset <= 0
                          ? null
                          : () {
                              setState(() {
                                _offset = (_offset - _limit).clamp(0, _offset);
                              });
                              _load();
                            },
                      onNext: _bulkBusy || _offset + _limit >= queue.total
                          ? null
                          : () {
                              setState(() => _offset += _limit);
                              _load();
                            },
                    ),
                  ],
                ],
              ),
            ),
    );
  }
}

class _ReviewSummaryBand extends StatelessWidget {
  const _ReviewSummaryBand({required this.summary});

  final DatasetReviewSummary summary;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        border: Border.all(color: Theme.of(context).dividerColor),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Wrap(
        spacing: 28,
        runSpacing: 12,
        children: [
          _SummaryMetric(label: 'ทั้งหมด', value: summary.total),
          _SummaryMetric(label: 'รอตรวจ', value: summary.pending),
          _SummaryMetric(label: 'อนุมัติแล้ว', value: summary.approved),
          _SummaryMetric(label: 'ปฏิเสธแล้ว', value: summary.rejected),
        ],
      ),
    );
  }
}

class _SummaryMetric extends StatelessWidget {
  const _SummaryMetric({required this.label, required this.value});

  final String label;
  final int value;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 130,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('$value', style: Theme.of(context).textTheme.headlineSmall),
          Text(label, style: Theme.of(context).textTheme.bodySmall),
        ],
      ),
    );
  }
}

class _ReviewFilters extends StatelessWidget {
  const _ReviewFilters({
    required this.searchController,
    required this.leafKey,
    required this.taxonomy,
    required this.onLeafChanged,
    required this.onSearch,
  });

  final TextEditingController searchController;
  final String leafKey;
  final List<DatasetReviewTaxonomyLeaf> taxonomy;
  final ValueChanged<String> onLeafChanged;
  final VoidCallback onSearch;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final fieldWidth = constraints.maxWidth < 720
            ? constraints.maxWidth
            : (constraints.maxWidth - 12) / 2;
        return Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            SizedBox(
              width: fieldWidth,
              child: TextField(
                controller: searchController,
                decoration: const InputDecoration(
                  labelText: 'ค้นหาชื่อ ช่อง หรือ Transcript',
                  prefixIcon: Icon(Icons.search),
                ),
                onSubmitted: (_) => onSearch(),
              ),
            ),
            SizedBox(
              width: fieldWidth,
              child: DropdownButtonFormField<String>(
                initialValue: leafKey,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'หมวดหมู่'),
                items: [
                  const DropdownMenuItem(
                      value: 'all', child: Text('ทุกหมวดหมู่')),
                  ...taxonomy.map(
                    (leaf) => DropdownMenuItem(
                      value: leaf.leafKey,
                      child: Text(leaf.displayName, overflow: TextOverflow.ellipsis),
                    ),
                  ),
                ],
                onChanged: (value) {
                  if (value != null) onLeafChanged(value);
                },
              ),
            ),
          ],
        );
      },
    );
  }
}

class _TaxonomyProgress extends StatelessWidget {
  const _TaxonomyProgress({required this.taxonomy});

  final List<DatasetReviewTaxonomyLeaf> taxonomy;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('ความครอบคลุมที่ตรวจสอบแล้ว',
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: taxonomy
              .expand(
                (leaf) => leaf.coverageLabels.map((label) => Chip(
                  avatar: Icon(
                    leaf.ready ? Icons.check_circle : Icons.pending_outlined,
                    size: 18,
                    color: leaf.ready ? Colors.green : null,
                  ),
                  label: Text(label),
                )),
              )
              .toList(),
        ),
      ],
    );
  }
}

class _CandidateReviewCard extends StatelessWidget {
  const _CandidateReviewCard({
    required this.candidate,
    required this.reviewing,
    required this.actionsEnabled,
    required this.onOpenVideo,
    required this.onApprove,
    required this.onReject,
  });

  final DatasetReviewCandidate candidate;
  final bool reviewing;
  final bool actionsEnabled;
  final VoidCallback onOpenVideo;
  final VoidCallback onApprove;
  final VoidCallback onReject;

  @override
  Widget build(BuildContext context) {
    final passedChecks =
        candidate.automatedChecks.values.where((value) => value).length;
    final transcriptOrigin =
        candidate.transcriptAcquisitionMethod == 'notebooklm_manual_source'
            ? 'NotebookLM transcript'
            : '${candidate.captionType} captions';
    return Card(
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: BorderSide(color: Theme.of(context).dividerColor),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Text(
                    candidate.title,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                const SizedBox(width: 8),
                _StatusChip(status: candidate.reviewStatus),
                IconButton(
                  onPressed: onOpenVideo,
                  icon: const Icon(Icons.open_in_new),
                  tooltip: 'เปิดวิดีโอบน YouTube',
                ),
              ],
            ),
            Text(
              '${candidate.channelTitle} | ${candidate.durationSeconds}s | '
              '${candidate.transcriptLanguage.toUpperCase()} | $transcriptOrigin',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                Chip(label: Text('หมวดที่เสนอ: ${candidate.proposedLeafKey}')),
                Chip(label: Text(candidate.licenseName)),
                Chip(
                  avatar: Icon(
                    candidate.allAutomatedChecksPass
                        ? Icons.verified_outlined
                        : Icons.warning_amber_outlined,
                    size: 18,
                  ),
                  label: Text(
                    'Automated checks $passedChecks/${candidate.automatedChecks.length}',
                  ),
                ),
                const Chip(
                  avatar: Icon(Icons.model_training_outlined, size: 18),
                  label: Text('ใช้จำแนกหมวดและคำสำคัญ'),
                ),
                if (candidate.transcriptAcquisitionMethod ==
                    'notebooklm_manual_source')
                  const Chip(
                    avatar: Icon(Icons.text_snippet_outlined, size: 18),
                    label: Text('แหล่งข้อมูล NotebookLM'),
                  ),
                if (candidate.transcriptScope == 'full_video')
                  const Chip(
                    avatar: Icon(Icons.subject_outlined, size: 18),
                    label: Text('Transcript ทั้งคลิป'),
                  ),
                Chip(
                  avatar: Icon(
                    candidate.datasetUsage['duration_recommendation'] == true
                        ? Icons.schedule_outlined
                        : Icons.timer_off_outlined,
                    size: 18,
                  ),
                  label: Text(
                    candidate.datasetUsage['duration_recommendation'] == true
                        ? 'Duration evidence'
                        : 'Excluded from duration evidence',
                  ),
                ),
                ...candidate.evidenceTerms.take(6).map(
                      (term) => Chip(label: Text(term)),
                    ),
              ],
            ),
            const SizedBox(height: 10),
            SelectionArea(
              child: Text(
                candidate.transcriptPreview,
                maxLines: 5,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            ExpansionTile(
              tilePadding: EdgeInsets.zero,
              childrenPadding: const EdgeInsets.only(bottom: 8),
              title: Text(
                'Full transcript (${candidate.transcript.length} characters)',
                style: Theme.of(context).textTheme.labelLarge,
              ),
              children: [
                ConstrainedBox(
                  constraints: const BoxConstraints(maxHeight: 320),
                  child: SingleChildScrollView(
                    child: SelectionArea(
                      child: Text(candidate.transcript),
                    ),
                  ),
                ),
              ],
            ),
            if (candidate.reviewer != null) ...[
              const SizedBox(height: 10),
              Text(
                'Reviewed by ${candidate.reviewer}'
                '${candidate.reviewedLeafKey == null ? '' : ' as ${candidate.reviewedLeafKey}'}',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
            const SizedBox(height: 14),
            if (reviewing)
              const LinearProgressIndicator()
            else
              Wrap(
                spacing: 10,
                runSpacing: 8,
                children: [
                  FilledButton.icon(
                    onPressed: actionsEnabled ? onApprove : null,
                    icon: const Icon(Icons.check),
                    label: const Text('อนุมัติ'),
                  ),
                  OutlinedButton.icon(
                    onPressed: actionsEnabled ? onReject : null,
                    icon: const Icon(Icons.close),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: Theme.of(context).colorScheme.error,
                      side: BorderSide(
                          color: Theme.of(context).colorScheme.error),
                    ),
                    label: const Text('ปฏิเสธ'),
                  ),
                ],
              ),
          ],
        ),
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.status});

  final String status;

  @override
  Widget build(BuildContext context) {
    final color = switch (status) {
      'approved' => Colors.green,
      'rejected' => Theme.of(context).colorScheme.error,
      _ => Colors.orange,
    };
    return Chip(
      avatar: Icon(
        status == 'approved'
            ? Icons.check_circle_outline
            : status == 'rejected'
                ? Icons.cancel_outlined
                : Icons.pending_outlined,
        size: 18,
        color: color,
      ),
      label: Text(status),
    );
  }
}

class _ReviewDecision {
  const _ReviewDecision({
    required this.decision,
    required this.notes,
    this.reviewedLeafKey,
    this.transcriptQuality,
  });

  final String decision;
  final String? reviewedLeafKey;
  final String? transcriptQuality;
  final String notes;
}

class _ReviewDialog extends StatefulWidget {
  const _ReviewDialog({
    required this.candidate,
    required this.taxonomy,
    required this.initialDecision,
  });

  final DatasetReviewCandidate candidate;
  final List<DatasetReviewTaxonomyLeaf> taxonomy;
  final String initialDecision;

  @override
  State<_ReviewDialog> createState() => _ReviewDialogState();
}

class _ReviewDialogState extends State<_ReviewDialog> {
  late String _decision;
  late String _leafKey;
  String _quality = 'good';
  final _notesController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _decision = widget.initialDecision;
    _leafKey =
        widget.candidate.reviewedLeafKey ?? widget.candidate.proposedLeafKey;
    _quality = widget.candidate.transcriptQuality ?? 'good';
    _notesController.text = widget.candidate.reviewNotes ?? '';
  }

  @override
  void dispose() {
    _notesController.dispose();
    super.dispose();
  }

  void _submit() {
    Navigator.pop(
      context,
      _ReviewDecision(
        decision: _decision,
        reviewedLeafKey: _decision == 'approve' ? _leafKey : null,
        transcriptQuality: _decision == 'approve' ? _quality : null,
        notes: _notesController.text,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final approve = _decision == 'approve';
    return AlertDialog(
      title: Text(approve ? 'Approve candidate' : 'Reject candidate'),
      content: SizedBox(
        width: 760,
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(widget.candidate.title,
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 4),
              Text(
                '${widget.candidate.channelTitle} | '
                '${widget.candidate.durationSeconds}s | '
                '${widget.candidate.transcriptLanguage.toUpperCase()}',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: 14),
              Text('Transcript', style: Theme.of(context).textTheme.labelLarge),
              const SizedBox(height: 6),
              Container(
                constraints: const BoxConstraints(maxHeight: 240),
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  border: Border.all(color: Theme.of(context).dividerColor),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: SelectionArea(
                  child: SingleChildScrollView(
                    child: Text(widget.candidate.transcript),
                  ),
                ),
              ),
              const SizedBox(height: 14),
              SegmentedButton<String>(
                segments: const [
                  ButtonSegment(
                    value: 'approve',
                    icon: Icon(Icons.check),
                    label: Text('อนุมัติ'),
                  ),
                  ButtonSegment(
                    value: 'reject',
                    icon: Icon(Icons.close),
                    label: Text('ปฏิเสธ'),
                  ),
                ],
                selected: {_decision},
                onSelectionChanged: (values) {
                  setState(() => _decision = values.first);
                },
              ),
              if (approve) ...[
                const SizedBox(height: 14),
                DropdownButtonFormField<String>(
                  initialValue: _leafKey,
                  isExpanded: true,
                  decoration:
                      const InputDecoration(labelText: 'หมวดหมู่ที่ตรวจแล้ว'),
                  items: widget.taxonomy
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
                  onChanged: (value) {
                    if (value != null) setState(() => _leafKey = value);
                  },
                ),
                const SizedBox(height: 12),
                SegmentedButton<String>(
                  segments: const [
                    ButtonSegment(
                        value: 'good', label: Text('Transcript คุณภาพดี')),
                    ButtonSegment(
                      value: 'acceptable',
                      label: Text('ใช้งานได้'),
                    ),
                  ],
                  selected: {_quality},
                  onSelectionChanged: (values) {
                    setState(() => _quality = values.first);
                  },
                ),
              ],
              const SizedBox(height: 14),
              TextField(
                controller: _notesController,
                minLines: 2,
                maxLines: 4,
                decoration: InputDecoration(
                  labelText:
                      approve ? 'Review notes (optional)' : 'Reject reason',
                ),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('ยกเลิก'),
        ),
        FilledButton.icon(
          onPressed: _submit,
          icon: Icon(approve ? Icons.check : Icons.close),
          style: approve
              ? null
              : FilledButton.styleFrom(
                  backgroundColor: Theme.of(context).colorScheme.error,
                ),
          label: Text(approve ? 'Confirm approval' : 'Confirm rejection'),
        ),
      ],
    );
  }
}
