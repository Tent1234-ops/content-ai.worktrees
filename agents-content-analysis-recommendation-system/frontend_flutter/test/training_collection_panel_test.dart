import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:content_ai_web/repositories/admin_repository.dart';
import 'package:content_ai_web/widgets/training_collection_panel.dart';

class PreviewRepository extends AdminRepository {
  bool fail = false;
  int calls = 0;
  @override
  Future<List<Map<String, dynamic>>> previewTrainingChannels(
      List<String> ids) async {
    calls++;
    if (fail) throw Exception('offline');
    return [
      {
        'channel_id': ids.first,
        'assigned_split': 'validation',
        'existing_dataset_count': 0,
        'split_conflict': false,
        'unknown_usage': 'validation',
        'independence_confirmed': false
      }
    ];
  }
}

void main() {
  final plan = {
    'additional_minimum': 126,
    'collection_ready': false,
    'unknown_train_reserved_count': 0,
    'rows': [
      {
        'leaf_key': 'phone',
        'split': 'all',
        'current': 50,
        'minimum': 80,
        'missing': 30,
        'channels': 21,
        'minimum_channels': 10
      },
      {
        'leaf_key': 'unknown',
        'split': 'validation',
        'current': 0,
        'minimum': 10,
        'missing': 10,
        'channels': 0,
        'minimum_channels': 3
      },
      {
        'leaf_key': 'unknown',
        'split': 'test',
        'current': 0,
        'minimum': 30,
        'missing': 30,
        'channels': 0,
        'minimum_channels': 3
      },
    ]
  };
  testWidgets('collection gaps and preview errors are explicit on compact web',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1000, 1100));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final repository = PreviewRepository();
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: SingleChildScrollView(
                child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: TrainingCollectionPanel(
                        plan: plan, repository: repository))))));
    await tester.pumpAndSettle();
    expect(find.textContaining('ยังขาดอย่างน้อย 126'), findsOneWidget);
    expect(find.text('นอกขอบเขต · เลือกเกณฑ์ (Validation)'), findsOneWidget);
    expect(find.text('นอกขอบเขต · ทดสอบ (Test)'), findsOneWidget);
    await tester.tap(find.text('ตรวจชุดข้อมูลจากรหัสช่อง'));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const Key('collection-channel-ids')), '@handle');
    await tester.tap(find.byKey(const Key('collection-preview')));
    await tester.pumpAndSettle();
    expect(repository.calls, 0);
    await tester.enterText(
        find.byKey(const Key('collection-channel-ids')), 'UC${'a' * 22}');
    await tester.tap(find.byKey(const Key('collection-preview')));
    await tester.pumpAndSettle();
    expect(
        find.textContaining('ยังไม่ยืนยันว่าช่องมีอยู่จริง'), findsOneWidget);
    repository.fail = true;
    await tester.tap(find.byKey(const Key('collection-preview')));
    await tester.pumpAndSettle();
    expect(find.text('ตรวจชุดข้อมูลไม่สำเร็จ กรุณาลองใหม่'), findsOneWidget);
    expect(find.textContaining('ยังไม่ยืนยันว่าช่องมีอยู่จริง'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
