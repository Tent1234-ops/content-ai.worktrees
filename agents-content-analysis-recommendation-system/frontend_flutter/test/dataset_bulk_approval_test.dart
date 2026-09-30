import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:content_ai_web/models/dataset_review.dart';
import 'package:content_ai_web/repositories/admin_repository.dart';
import 'package:content_ai_web/widgets/dataset_bulk_approval.dart';

class _Repository extends AdminRepository {
  _Repository(this.count);
  final int count;
  int calls = 0;
  final offsets = <int>[];
  final approvedLeaves = <String>[];
  int? failAt;
  bool missingReceipt = false;
  bool changedQueue = false;
  Completer<void>? gate;

  @override
  Future<DatasetReviewQueueResult> listDatasetReviewQueue(
      {required int limit,
      required int offset,
      String status = 'pending',
      String leafKey = 'all',
      int? collectionRunId,
      String search = ''}) async {
    expect(status, 'pending');
    expect(leafKey, 'all');
    expect(search, 'fixture');
    offsets.add(offset);
    return DatasetReviewQueueResult.fromJson({
      'total': count + (changedQueue && offset > 0 ? 1 : 0),
      'offset': offset,
      'limit': limit,
      'items': [
        for (int i = offset; i < count && i < offset + limit; i++)
          {
            'collection_run_id': 1,
            'source_youtube_id': 'video$i',
            'title': 'Candidate $i',
            'proposed_leaf_key': i.isEven ? 'phone' : 'camera',
            'candidate_sha256': 'a' * 64,
          }
      ],
    });
  }

  @override
  Future<DatasetReviewDecisionResult> reviewDatasetCandidate(
      {required DatasetReviewCandidate candidate,
      required String decision,
      String? reviewedLeafKey,
      String? transcriptQuality,
      String notes = '',
      bool requirePending = false}) async {
    expect(requirePending, isTrue);
    expect(transcriptQuality, 'good');
    expect(reviewedLeafKey, candidate.proposedLeafKey);
    final call = calls++;
    if (gate != null) await gate!.future;
    if (call == failAt) throw Exception('fixture failure');
    approvedLeaves.add(reviewedLeafKey!);
    return DatasetReviewDecisionResult.fromJson({
      'decision': 'approve',
      'collection_run_id': candidate.collectionRunId,
      'source_youtube_id': candidate.youtubeId,
      if (!missingReceipt) 'review_event_id': calls,
      if (!missingReceipt) 'dataset_id': calls,
    });
  }
}

Future<void> _show(
    WidgetTester tester, _Repository repo, List<String> reviewed) async {
  tester.view.physicalSize = const Size(1200, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.pumpWidget(MaterialApp(
      home: Scaffold(
          body: DatasetBulkApproval(
    repository: repo,
    leafKey: 'all',
    search: 'fixture',
    enabled: true,
    onBusyChanged: (_) {},
    onReviewed: (row) => reviewed.add(row.youtubeId),
    onFinished: () {},
  ))));
  await tester.tap(find.byKey(const Key('approve-all')));
  await tester.pumpAndSettle();
}

Future<void> _confirm(WidgetTester tester) async {
  expect(
      tester
          .widget<FilledButton>(find.byKey(const Key('confirm-approve-all')))
          .onPressed,
      isNull);
  await tester.tap(find.byType(DropdownButtonFormField<String>));
  await tester.pumpAndSettle();
  await tester.tap(find.text('ดี').last);
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const Key('bulk-review-confirmed')));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const Key('confirm-approve-all')));
}

void main() {
  testWidgets(
      'cancel is read only, approval spans all pages with proposed labels',
      (tester) async {
    final repo = _Repository(101);
    final reviewed = <String>[];
    await _show(tester, repo, reviewed);
    expect(repo.offsets, [0, 100]);
    await tester.tap(find.text('ยกเลิก'));
    await tester.pumpAndSettle();
    expect(repo.calls, 0);
    await tester.tap(find.byKey(const Key('approve-all')));
    await tester.pumpAndSettle();
    await _confirm(tester);
    await tester.pumpAndSettle();
    expect(repo.calls, 101);
    expect(reviewed.length, 101);
    expect(repo.approvedLeaves.toSet(), {'phone', 'camera'});
    expect(find.textContaining('อนุมัติสำเร็จ 101/101'), findsOneWidget);
  });

  testWidgets('failure and absent receipt never count as saved',
      (tester) async {
    final repo = _Repository(3)..failAt = 1;
    final reviewed = <String>[];
    await _show(tester, repo, reviewed);
    await _confirm(tester);
    await tester.pumpAndSettle();
    expect(reviewed, ['video0', 'video2']);
    expect(find.textContaining('อนุมัติสำเร็จ 2/3'), findsOneWidget);
    repo.missingReceipt = true;
    await tester.tap(find.byKey(const Key('approve-all')));
    await tester.pumpAndSettle();
    await _confirm(tester);
    await tester.pumpAndSettle();
    expect(reviewed.length, 2);
    expect(find.textContaining('อนุมัติสำเร็จ 0/3'), findsOneWidget);
  });

  testWidgets(
      'queue changes abort before approval and stop waits only for current request',
      (tester) async {
    final changing = _Repository(101)..changedQueue = true;
    await _show(tester, changing, []);
    expect(changing.calls, 0);
    expect(find.byKey(const Key('confirm-approve-all')), findsNothing);
    final repo = _Repository(3)..gate = Completer<void>();
    final reviewed = <String>[];
    await tester.pumpWidget(const SizedBox());
    await _show(tester, repo, reviewed);
    await _confirm(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.text('หยุดหลังรายการนี้'));
    repo.gate!.complete();
    await tester.pumpAndSettle();
    expect(repo.calls, 1);
    expect(reviewed.length, 1);
    expect(find.textContaining('ยังไม่ดำเนินการ 2'), findsOneWidget);
  });
}
