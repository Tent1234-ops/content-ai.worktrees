import 'package:content_ai_web/models/common_models.dart';
import 'package:content_ai_web/models/dataset_item.dart';
import 'package:content_ai_web/models/dataset_review.dart';
import 'package:content_ai_web/models/system_log.dart';
import 'package:content_ai_web/repositories/admin_repository.dart';
import 'package:content_ai_web/screens/admin_datasets_screen.dart';
import 'package:content_ai_web/screens/admin_logs_screen.dart';
import 'package:content_ai_web/utils/system_log_presenter.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets(
      'trash restores only after confirmed persistence; failures keep row visible',
      (tester) async {
    final repository = _DatasetsRepository()..deleted = true;
    await tester.binding.setSurfaceSize(const Size(1280, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
        MaterialApp(home: AdminDatasetsScreen(repository: repository)));
    await tester.pumpAndSettle();
    await tester.tap(find.text('ถังขยะ'));
    await tester.pumpAndSettle();
    repository.failRestore = true;
    await tester.tap(find.byTooltip('กู้คืน Dataset #42'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('ยืนยันกู้คืน'));
    await tester.pumpAndSettle();
    expect(repository.deleted, true);
    expect(find.textContaining('กู้คืนไม่สำเร็จ'), findsOneWidget);
    expect(find.text('Phone review'), findsOneWidget);
    expect(find.text('กู้คืนข้อมูลและสิทธิ์เดิมแล้ว'), findsNothing);
    repository.failRestore = false;
    await tester.tap(find.byTooltip('กู้คืน Dataset #42'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('ยืนยันกู้คืน'));
    await tester.pumpAndSettle();
    expect(repository.deleted, false);
    expect(find.text('ถังขยะว่าง'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
      'editor cancel is not a successful save; failed update stays open',
      (tester) async {
    final repository = _DatasetsRepository();
    await tester.binding.setSurfaceSize(const Size(1280, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
        MaterialApp(home: AdminDatasetsScreen(repository: repository)));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Phone review'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('ยกเลิก'));
    await tester.pumpAndSettle();
    expect(repository.updatedPayload, isNull);
    expect(find.text('บันทึกข้อมูลแล้ว'), findsNothing);
    expect(tester.takeException(), isNull);
    repository.failSave = true;
    await tester.tap(find.text('Phone review'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('dataset-save')));
    await tester.pumpAndSettle();
    expect(find.textContaining('write failed'), findsOneWidget);
    expect(find.byKey(const ValueKey('dataset-save')), findsOneWidget);
    expect(find.text('บันทึกข้อมูลแล้ว'), findsNothing);
  });
  testWidgets(
      'dataset delete requires confirmation and removes the item after success',
      (tester) async {
    final repository = _DatasetsRepository();
    await tester.binding.setSurfaceSize(const Size(1280, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
        MaterialApp(home: AdminDatasetsScreen(repository: repository)));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('ลบ Dataset #42'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('ยกเลิก'));
    await tester.pumpAndSettle();
    expect(repository.deleted, false);
    await tester.tap(find.byTooltip('ลบ Dataset #42'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('ยืนยันลบ Dataset'));
    await tester.pumpAndSettle();
    expect(repository.deleted, true);
    expect(find.text('Phone review'), findsNothing);
    expect(find.text('ไม่พบข้อมูล'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
  test('system log parses backend audit fields and exposes Thai labels', () {
    final item = SystemLogItem.fromJson({
      'log_id': 9,
      'action': 'dataset_review_reject',
      'status': 'failed',
      'detail': 'youtube_id=abc',
      'timestamp': '2026-09-03T08:30:00',
      'user_id': 2,
    });

    expect(item.timestamp?.isUtc, isTrue);
    expect(item.userId, 2);
    expect(
      systemLogActionLabel(item.action),
      'ปฏิเสธข้อมูลฝึกก่อนนำเข้าฐานข้อมูล',
    );
    expect(systemLogStatusLabel(item.status), 'ไม่สำเร็จ');
    expect(
      systemLogActionLabel('admin_dataset_training_content_corrected'),
      'แก้ไข Transcript หรือหมวดข้อมูลฝึกที่อนุมัติแล้ว',
    );
  });

  testWidgets('system logs present audit events in Thai with time and actor',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1280, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      MaterialApp(
        home: AdminLogsScreen(repository: _LogsRepository()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('ค้นหารหัสเหตุการณ์'), findsNothing);
    expect(find.byType(TextField), findsNothing);
    expect(find.text('อนุมัติข้อมูลฝึกเข้าสู่ฐานข้อมูล'), findsOneWidget);
    expect(find.text('dataset_review_approve'), findsOneWidget);
    expect(find.text('สำเร็จ'), findsAtLeastNWidgets(1));
    expect(find.text('ผู้ใช้หมายเลข 2'), findsOneWidget);
  });

  testWidgets('admin navigation omits the removed admin console',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1280, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      MaterialApp(
        home: AdminDatasetsScreen(repository: _DatasetsRepository()),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byType(DrawerButton));
    await tester.pumpAndSettle();

    expect(find.text('Admin Console'), findsNothing);
    expect(find.text('นำเข้า Transcript'), findsOneWidget);
    expect(find.text('ตรวจสอบ Dataset'), findsOneWidget);
    expect(find.text('บันทึกการทำงาน'), findsOneWidget);
  });

  testWidgets(
      'dataset editor submits transcript with the canonical taxonomy leaf',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1280, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final repository = _DatasetsRepository();

    await tester.pumpWidget(
      MaterialApp(home: AdminDatasetsScreen(repository: repository)),
    );
    await tester.pumpAndSettle();

    expect(find.text('Search title or transcript'), findsNothing);
    expect(
        find.byKey(const ValueKey('dataset-category-filter')), findsOneWidget);
    expect(find.text('score'), findsNothing);

    await tester.tap(find.text('Phone review'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('dataset-transcript')),
      List.filled(
        4,
        'camera sensor lens aperture photography image quality ',
      ).join(),
    );
    await tester.tap(find.byKey(const ValueKey('dataset-taxonomy-leaf')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Technology > Electronics > Camera').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('dataset-save')));
    await tester.pumpAndSettle();

    expect(repository.updatedDatasetId, 42);
    expect(repository.updatedPayload?['taxonomy_leaf_key'], 'camera');
    expect(
      repository.updatedPayload?['transcript'],
      contains('camera sensor lens'),
    );
    expect(repository.updatedPayload?.containsKey('category'), isFalse);
    expect(
        repository.updatedPayload?.containsKey('transcript_sha256'), isFalse);
  });

  testWidgets(
      'manual dataset create stays unassigned and only reports persisted success',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1280, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final repository = _DatasetsRepository();

    await tester.pumpWidget(
      MaterialApp(home: AdminDatasetsScreen(repository: repository)),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('เพิ่ม Dataset สำหรับตรวจสอบ'));
    await tester.pumpAndSettle();

    expect(find.textContaining('ยังไม่ใช้ฝึกโมเดลหรือสร้างคำแนะนำ'),
        findsOneWidget);
    await tester.enterText(
      find.byKey(const ValueKey('dataset-create-title')),
      'Camera manual review',
    );
    await tester.tap(
      find.byKey(const ValueKey('dataset-create-taxonomy-leaf')),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Technology > Electronics > Camera').last);
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('dataset-create-transcript')),
      'กล้อง เซนเซอร์ เลนส์ และคุณภาพของภาพจากคลิปทดสอบ',
    );
    await tester.tap(find.byKey(const ValueKey('dataset-create-save')));
    await tester.pumpAndSettle();

    expect(repository.createdPayload?['taxonomy_leaf_key'], 'camera');
    expect(repository.createdPayload?['data_split'], 'unassigned');
    expect(repository.createdPayload?['is_training_eligible'], false);
    expect(repository.createdPayload?['source_platform'], 'admin_manual');
    expect(find.text('Camera manual review'), findsOneWidget);
    expect(find.textContaining('เพิ่ม Dataset #77 เป็นรายการรอตรวจแล้ว'),
        findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

class _LogsRepository extends AdminRepository {
  @override
  Future<PaginatedResult<SystemLogItem>> listLogs({
    required int limit,
    required int offset,
    String status = 'all',
    String action = '',
  }) async {
    return PaginatedResult(
      total: 1,
      items: [
        SystemLogItem.fromJson({
          'log_id': 1,
          'action': 'dataset_review_approve',
          'status': 'success',
          'detail': 'youtube_id=abc, dataset_id=42',
          'timestamp': '2026-09-03T08:30:00',
          'user_id': 2,
        }),
      ],
    );
  }
}

class _DatasetsRepository extends AdminRepository {
  bool failRestore = false;
  bool failSave = false;
  @override
  Future<DatasetItem> restoreDataset(int id) async {
    if (failRestore) throw StateError('restore failed');
    deleted = false;
    return item;
  }

  bool deleted = false;
  bool created = false;
  Map<String, dynamic>? createdPayload;
  @override
  Future<void> deleteDataset(int id) async {
    expect(id, 42);
    deleted = true;
  }

  int? updatedDatasetId;
  Map<String, dynamic>? updatedPayload;

  final DatasetItem item = DatasetItem.fromJson({
    'dataset_id': 42,
    'title': 'Phone review',
    'video_url': 'https://youtu.be/phone000001',
    'transcript': List.filled(
      4,
      'phone battery display camera performance ',
    ).join(),
    'source_platform': 'youtube',
    'category': 'phone',
    'taxonomy_version': 'content-taxonomy-v1',
    'taxonomy_leaf_key': 'phone',
    'category_level_1': 'Technology',
    'category_level_2': 'Electronics',
    'category_level_3': 'Phone',
    'transcript_sha256': List.filled(64, 'a').join(),
    'data_split': 'train',
    'is_training_eligible': true,
    'views': 100,
    'likes': 10,
    'comments': 2,
    'trend_score': 1.0,
    'duration_seconds': 180,
  });

  final DatasetItem createdItem = DatasetItem.fromJson({
    'dataset_id': 77,
    'title': 'Camera manual review',
    'video_url': null,
    'transcript': 'กล้อง เซนเซอร์ เลนส์ และคุณภาพของภาพจากคลิปทดสอบ',
    'source_platform': 'admin_manual',
    'category': 'camera',
    'taxonomy_version': 'content-taxonomy-v1',
    'taxonomy_leaf_key': 'camera',
    'category_level_1': 'Technology',
    'category_level_2': 'Electronics',
    'category_level_3': 'Camera',
    'transcript_sha256':
        'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    'data_split': 'unassigned',
    'is_training_eligible': false,
    'views': 0,
    'likes': 0,
    'comments': 0,
    'trend_score': 0,
  });

  @override
  Future<DatasetItem> createDataset(Map<String, dynamic> payload) async {
    createdPayload = Map<String, dynamic>.from(payload);
    created = true;
    return createdItem;
  }

  @override
  Future<List<DatasetReviewTaxonomyLeaf>> listTaxonomyLeaves() async {
    return [
      DatasetReviewTaxonomyLeaf.fromJson({
        'leaf_key': 'phone',
        'category_level_1': 'Technology',
        'category_level_2': 'Electronics',
        'category_level_3': 'Phone',
      }),
      DatasetReviewTaxonomyLeaf.fromJson({
        'leaf_key': 'camera',
        'category_level_1': 'Technology',
        'category_level_2': 'Electronics',
        'category_level_3': 'Camera',
      }),
    ];
  }

  @override
  Future<PaginatedResult<DatasetItem>> listDatasets({
    required int limit,
    required int offset,
    String source = 'all',
    String category = 'all',
    String search = '',
    bool trashed = false,
  }) async {
    final items = trashed
        ? <DatasetItem>[if (deleted) item]
        : <DatasetItem>[if (created) createdItem, if (!deleted) item];
    return PaginatedResult(
      total: items.length,
      items: items,
    );
  }

  @override
  Future<DatasetItem> updateDataset(
    int datasetId,
    Map<String, dynamic> payload,
  ) async {
    if (failSave) throw StateError('write failed');
    updatedDatasetId = datasetId;
    updatedPayload = Map<String, dynamic>.from(payload);
    return item;
  }
}
