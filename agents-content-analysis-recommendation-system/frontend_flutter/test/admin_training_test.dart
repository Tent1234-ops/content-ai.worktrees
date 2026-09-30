import 'package:content_ai_web/models/common_models.dart';
import 'package:content_ai_web/models/model_training.dart';
import 'package:content_ai_web/repositories/admin_repository.dart';
import 'package:content_ai_web/screens/admin_training_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> modelJson(int id,
        {bool active = false, bool qualified = false}) =>
    {
      'model_id': id,
      'model_key': 'taxonomy-tfidf-logreg-tuned',
      'model_version': 'web-test-$id',
      'status': qualified ? 'qualified' : 'evaluated_below_threshold',
      'is_active': active,
      'can_activate': qualified && !active,
      'artifact_available': true,
      'training_sample_count': 137,
      'unknown_threshold': 0.6,
      'metrics': [
        for (final split in ['grouped_cv', 'test']) ...[
          {
            'split': split,
            'metric': 'accuracy',
            'value': 0.85,
            'sample_size': 17
          },
          {
            'split': split,
            'metric': 'f1_macro',
            'value': 0.81,
            'sample_size': 17
          },
        ]
      ],
      'qualification': {
        'blocked_reasons': qualified ? [] : ['phase22_collection_not_ready']
      },
      'per_category': [
        {
          'split': 'test',
          'category': 'laptop',
          'metric': 'recall',
          'value': 0.6,
          'sample_size': 5
        }
      ],
      'confusion_matrices': [
        {
          'split': 'test',
          'labels': ['phone', 'laptop'],
          'matrix': [
            [8, 0],
            [2, 3]
          ]
        }
      ],
    };

TrainingRun run(String status) => TrainingRun.fromJson({
      'run_id': 'a2fe172d-c608-4b6e-901f-b7d8886e4ac1',
      'status': status,
      'stage': status == 'running' ? 'cross_validation' : status,
      'created_at': '2026-09-07T10:00:00',
      'result': status == 'completed'
          ? {
              'model_ids': [21, 22]
            }
          : null,
    });

class TrainingRepository extends AdminRepository {
  bool ready = true, failLoad = false;
  int starts = 0, active = 14, polls = 0;
  int? activated;
  TrainingRun? latest;
  @override
  Future<TrainingOverview> trainingOverview() async {
    if (failLoad) throw Exception('offline');
    return TrainingOverview.fromJson({
      'dataset': {
        'ready': ready,
        'dataset_fingerprint': 'a' * 64,
        'sample_count': 154,
        'unique_channels': 61,
        'channel_leakage_count': 0,
        'by_leaf': [
          for (final name in ['phone', 'camera', 'laptop'])
            {
              'leaf_key': name,
              'total': 50,
              'ready': ready,
              'unique_channels': 20,
              'minimum_required': 30,
              'minimum_split_counts': {'train': 15, 'validation': 3, 'test': 3},
              'split_counts': {'train': 35, 'validation': 10, 'test': 5},
            }
        ],
        'phase22': {
          'ready': false,
          'by_leaf': [],
          'out_of_scope': {'sample_count': 0, 'minimum_sample_count': 30}
        }
      },
      'policy': {
        'promotion_threshold': 0.8,
        'unknown_threshold': 0.6,
        'grouped_cv_folds': 5
      },
      'runs': latest == null
          ? []
          : [
              {
                'run_id': latest!.id,
                'status': latest!.status,
                'stage': latest!.stage,
                'created_at': latest!.createdAt,
                'result': latest!.result
              }
            ],
      'models': {
        'total': 3,
        'items': [
          modelJson(14, active: active == 14, qualified: true),
          modelJson(21),
          modelJson(22, active: active == 22, qualified: true)
        ]
      },
      'active_model': modelJson(active, active: true, qualified: true),
    });
  }

  @override
  Future<TrainingRun> startTraining(String fingerprint) async {
    expect(fingerprint, 'a' * 64);
    starts++;
    latest = run('queued');
    return latest!;
  }

  @override
  Future<TrainingRun> trainingRun(String id) async {
    polls++;
    latest = run('completed');
    return latest!;
  }

  @override
  Future<TrainedModel> trainingModel(int id) async => TrainedModel.fromJson(
      modelJson(id, active: active == id, qualified: id != 21));
  @override
  Future<void> activateTrainingModel(int id, int? activeId) async {
    expect(activeId, active);
    activated = active = id;
  }

  @override
  Future<PaginatedResult<TrainedModel>> trainingModels(
          {required int offset}) async =>
      const PaginatedResult(total: 3, items: []);
}

void main() {
  Future<void> open(WidgetTester tester, TrainingRepository repository) async {
    await tester.binding.setSurfaceSize(const Size(1440, 1100));
    addTearDown(() async {
      await tester.pumpWidget(const SizedBox());
      await tester.binding.setSurfaceSize(null);
    });
    await tester.pumpWidget(
        MaterialApp(home: AdminTrainingScreen(repository: repository)));
    await tester.pumpAndSettle();
  }

  test('model labels and missing metrics do not invent scores', () {
    final model = TrainedModel.fromJson(modelJson(21));
    expect(trainingModelName(model.key), 'Tuned Logistic Regression');
    expect(model.metric('validation', 'accuracy'), isNull);
    expect(trainingPercent(null), '-');
  });

  testWidgets(
      'readiness and confirmation prevent accidental or duplicate training',
      (tester) async {
    final repository = TrainingRepository();
    await open(tester, repository);
    expect(find.text('Phone'), findsOneWidget);
    expect(find.text('ข้อมูลสำหรับเทรน'), findsOneWidget);
    await tester.tap(find.byKey(const Key('start-training')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('ยกเลิก'));
    await tester.pumpAndSettle();
    expect(repository.starts, 0);
    await tester.tap(find.byKey(const Key('start-training')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('ยืนยันเริ่มเทรน'));
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pump(const Duration(milliseconds: 100));
    expect(repository.starts, 1);
    expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('start-training')))
            .onPressed,
        isNull);
    await tester.pump(const Duration(seconds: 5));
    await tester.pumpAndSettle();
    expect(repository.polls, 1);
    expect(find.text('โมเดลที่บันทึกไว้ (3)'), findsOneWidget);
    expect(repository.activated, isNull);
    expect(tester.takeException(), isNull);
  });

  testWidgets('incomplete dataset disables training', (tester) async {
    await open(tester, TrainingRepository()..ready = false);
    expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('start-training')))
            .onPressed,
        isNull);
    expect(find.textContaining('ขั้นต่ำ 30'), findsNWidgets(3));
  });

  testWidgets(
      'qualified model activation is explicit and results explain blocked models',
      (tester) async {
    final repository = TrainingRepository();
    await open(tester, repository);
    await tester.tap(find.text('เปรียบเทียบโมเดล'));
    await tester.pumpAndSettle();
    expect(find.byTooltip('เปิดใช้โมเดล #21'), findsNothing);
    await tester.tap(find.byTooltip('ดูผลประเมิน #21'));
    await tester.pumpAndSettle();
    expect(find.text('จำนวนข้อมูลหรือความหลากหลายของช่องยังไม่ครบ'),
        findsOneWidget);
    expect(find.text('60.0%'), findsOneWidget);
    await tester.tap(find.text('ทายถูกและสับสน · ชุดทดสอบ'));
    await tester.pumpAndSettle();
    expect(find.text('หมวดจริง / ทายเป็น'), findsOneWidget);
    await tester.tap(find.text('ปิด'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('เปิดใช้โมเดล #22'));
    await tester.pumpAndSettle();
    expect(repository.activated, isNull);
    await tester.tap(find.text('ยืนยันเปิดใช้'));
    await tester.pumpAndSettle();
    expect(repository.activated, 22);
    expect(find.text('เปิดใช้โมเดล #22 แล้ว'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('load failure can retry and compact web layout does not overflow',
      (tester) async {
    final repository = TrainingRepository()..failLoad = true;
    await open(tester, repository);
    expect(find.textContaining('offline'), findsOneWidget);
    repository.failLoad = false;
    await tester.tap(find.byTooltip('โหลดข้อมูลล่าสุด'));
    await tester.pumpAndSettle();
    await tester.binding.setSurfaceSize(const Size(850, 1000));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    await tester.tap(find.text('เปรียบเทียบโมเดล'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });
}
