import 'package:flutter/material.dart';

import '../models/dataset_review.dart';
import '../repositories/admin_repository.dart';

class DatasetBulkApproval extends StatefulWidget {
  const DatasetBulkApproval(
      {super.key,
      required this.repository,
      required this.leafKey,
      required this.search,
      required this.enabled,
      required this.onBusyChanged,
      required this.onReviewed,
      required this.onFinished});
  final AdminRepository repository;
  final String leafKey, search;
  final bool enabled;
  final ValueChanged<bool> onBusyChanged;
  final ValueChanged<DatasetReviewCandidate> onReviewed;
  final VoidCallback onFinished;
  @override
  State<DatasetBulkApproval> createState() => _DatasetBulkApprovalState();
}

class _DatasetBulkApprovalState extends State<DatasetBulkApproval> {
  bool _busy = false, _running = false, _cancel = false;
  int _total = 0, _completed = 0, _approved = 0;
  final List<String> _failures = [];
  String? _message;

  Future<void> _start() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _cancel = false;
      _message = null;
      _total = 0;
      _completed = 0;
      _approved = 0;
      _failures.clear();
    });
    widget.onBusyChanged(true);
    try {
      final candidates = <DatasetReviewCandidate>[];
      final seen = <String>{};
      int? expectedTotal;
      do {
        final page = await widget.repository.listDatasetReviewQueue(
            limit: 100,
            offset: candidates.length,
            status: 'pending',
            leafKey: widget.leafKey,
            search: widget.search);
        if (!mounted) return;
        expectedTotal ??= page.total;
        if (expectedTotal != page.total ||
            (page.items.isEmpty && candidates.length < expectedTotal)) {
          throw StateError('รายการรอตรวจเปลี่ยนแล้ว กรุณาโหลดใหม่ก่อนอนุมัติ');
        }
        for (final item in page.items) {
          if (!seen.add('${item.collectionRunId}:${item.youtubeId}') ||
              item.candidateSha256.isEmpty) {
            throw StateError('ยืนยันรายการสำหรับอนุมัติไม่ได้ กรุณาโหลดใหม่');
          }
          candidates.add(item);
        }
      } while (candidates.length < expectedTotal);
      if (candidates.isEmpty) {
        setState(() => _message = 'ไม่มีรายการรอตรวจที่ตรงกับตัวกรอง');
        return;
      }
      final quality = await showDialog<String>(
          context: context,
          barrierDismissible: false,
          builder: (_) => _BulkApprovalDialog(candidates: candidates));
      if (!mounted || quality == null) return;
      setState(() {
        _running = true;
        _total = candidates.length;
      });
      // Each existing API call commits its own review event; failures never count as approved.
      for (final candidate in candidates) {
        if (!mounted || _cancel) break;
        try {
          final result = await widget.repository.reviewDatasetCandidate(
              candidate: candidate,
              decision: 'approve',
              reviewedLeafKey: candidate.proposedLeafKey,
              transcriptQuality: quality,
              requirePending: true,
              notes: 'Approved via bulk review confirmation');
          if (result.reviewEventId == null ||
              result.datasetId == null ||
              result.decision != 'approve' ||
              result.collectionRunId != candidate.collectionRunId ||
              result.youtubeId != candidate.youtubeId) {
            throw StateError('เซิร์ฟเวอร์ยังไม่ยืนยันการบันทึก');
          }
          _approved++;
          if (mounted) widget.onReviewed(candidate);
        } catch (error) {
          _failures.add('${candidate.title}: $error');
        }
        _completed++;
        if (mounted) setState(() {});
      }
      if (mounted) {
        setState(() => _message = 'อนุมัติสำเร็จ $_approved/$_total รายการ · '
            'ไม่สำเร็จ ${_failures.length} · ยังไม่ดำเนินการ ${_total - _completed}');
        widget.onFinished();
      }
    } catch (error) {
      if (mounted) setState(() => _message = error.toString());
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
          _running = false;
        });
        widget.onBusyChanged(false);
      }
    }
  }

  @override
  Widget build(BuildContext context) =>
      Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          FilledButton.icon(
              key: const Key('approve-all'),
              onPressed: widget.enabled && !_busy ? _start : null,
              icon: const Icon(Icons.done_all),
              label: Text(
                  _busy && !_running ? 'กำลังเตรียมรายการ' : 'อนุมัติทั้งหมด')),
          if (_running) ...[
            const SizedBox(width: 12),
            OutlinedButton.icon(
                onPressed:
                    _cancel ? null : () => setState(() => _cancel = true),
                icon: const Icon(Icons.stop_circle_outlined),
                label: Text(_cancel ? 'กำลังหยุด' : 'หยุดหลังรายการนี้'))
          ],
        ]),
        if (_running) ...[
          const SizedBox(height: 12),
          LinearProgressIndicator(
              value: _total == 0 ? null : _completed / _total),
          Text('ดำเนินการ $_completed/$_total · อนุมัติแล้ว $_approved')
        ],
        if (_message != null)
          Padding(
              padding: const EdgeInsets.only(top: 12), child: Text(_message!)),
        if (_failures.isNotEmpty)
          ExpansionTile(
              title: Text('รายการที่ไม่สำเร็จ (${_failures.length})'),
              children: [
                for (final error in _failures)
                  ListTile(title: SelectableText(error))
              ]),
      ]);
}

class _BulkApprovalDialog extends StatefulWidget {
  const _BulkApprovalDialog({required this.candidates});
  final List<DatasetReviewCandidate> candidates;
  @override
  State<_BulkApprovalDialog> createState() => _BulkApprovalDialogState();
}

class _BulkApprovalDialogState extends State<_BulkApprovalDialog> {
  bool _confirmed = false;
  String? _quality;
  @override
  Widget build(BuildContext context) {
    final counts = <String, int>{};
    for (final row in widget.candidates) {
      counts.update(row.proposedLeafKey, (n) => n + 1, ifAbsent: () => 1);
    }
    return AlertDialog(
        title: Text('ยืนยันอนุมัติ ${widget.candidates.length} รายการ'),
        content: SizedBox(
            width: 620,
            child: SingleChildScrollView(
                child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                  Text(
                      'รายการรอตรวจทุกหน้าที่ตรงกับตัวกรอง: ${counts.entries.map((e) => '${e.key} ${e.value}').join(', ')}'),
                  const SizedBox(height: 12),
                  SizedBox(
                      height: 180,
                      child: ListView.builder(
                          itemCount: widget.candidates.length,
                          itemBuilder: (_, index) {
                            final row = widget.candidates[index];
                            return ListTile(
                                dense: true,
                                title: Text(row.title),
                                subtitle: Text(
                                    '${row.proposedLeafKey} · ${row.channelTitle}'));
                          })),
                  const SizedBox(height: 16),
                  DropdownButtonFormField<String>(
                      initialValue: _quality,
                      decoration: const InputDecoration(
                          labelText: 'คุณภาพ Transcript ที่ตรวจแล้ว'),
                      items: const [
                        DropdownMenuItem(value: 'good', child: Text('ดี')),
                        DropdownMenuItem(
                            value: 'acceptable', child: Text('ยอมรับได้'))
                      ],
                      onChanged: (value) => setState(() => _quality = value)),
                  CheckboxListTile(
                      key: const Key('bulk-review-confirmed'),
                      value: _confirmed,
                      onChanged: (value) =>
                          setState(() => _confirmed = value == true),
                      contentPadding: EdgeInsets.zero,
                      title: const Text(
                          'ฉันตรวจ Transcript และยืนยันหมวดที่เสนอของรายการทั้งหมดแล้ว')),
                ]))),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('ยกเลิก')),
          FilledButton.icon(
              key: const Key('confirm-approve-all'),
              onPressed: _confirmed && _quality != null
                  ? () => Navigator.pop(context, _quality)
                  : null,
              icon: const Icon(Icons.done_all),
              label: const Text('ยืนยันอนุมัติทั้งหมด'))
        ]);
  }
}
