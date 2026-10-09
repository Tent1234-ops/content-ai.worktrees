import 'package:content_ai_web/models/model_training.dart';
import 'package:content_ai_web/models/outcome_model_training.dart';
import 'package:content_ai_web/repositories/admin_repository.dart';
import 'package:content_ai_web/screens/admin_training_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> outcomeModelJson({bool canActivate = false}) => {
      'model_id': 7,
      'model_version': 'outcome-candidate-v1',
      'target_version': 'reference_relative_views_v1',
      'status': canActivate ? 'qualified' : 'validation_passed',
      'source_kind': 'real',
      'manifest_sha256': 'a' * 64,
      'protocol_sha256': 'b' * 64,
      'feature_schema_sha256': 'c' * 64,
      'is_active': false,
      'can_activate': canActivate,
      'independent_test_passed': canActivate,
      'production_eligible': canActivate,
      'training_sample_count': 126,
      'activation_reason_codes': canActivate
          ? []
          : [
              'model_not_independent_test_qualified',
              'independent_test_not_passed',
              'production_eligibility_false'
            ],
      'artifact_available': true,
      'metrics': {
        'tuning': {
          for (final key in [
            'constant_prior',
            'metadata_logistic_regression',
            'metadata_topics_logistic_regression'
          ])
            key: {
              'after': {
                'overall': {
                  'channel_balanced': {
                    'status': 'evaluated',
                    'brier_score': key == 'metadata_topics_logistic_regression'
                        ? 0.19
                        : 0.24,
                    'sample_count': 30,
                  }
                }
              }
            }
        },
        'calibration': {
          'metadata_topics_logistic_regression': {
            'after': {
              'calibration': {
                'passed': true,
                'maximum_observed_gap': 0.08,
                'actual_bins': 3,
              }
            }
          }
        },
        'independent_test': {
          'status':
              canActivate ? 'evaluated' : 'sealed_until_phase_6_evaluation'
        },
        'partition_counts': {
          'fit': {'videos': 50, 'channels': 10},
          'tuning': {'videos': 30, 'channels': 6},
          'calibration': {'videos': 20, 'channels': 5},
          'independent_test': {'videos': 30, 'channels': 10},
        },
      },
      'evaluated_scopes': ['overall', 'category'],
    };

class OutcomeAdminRepository extends AdminRepository {
  bool ready = false;
  bool canActivate = false;
  bool rejectActivation = false;
  int starts = 0;
  int activations = 0;

  @override
  Future<TrainingOverview> trainingOverview() async =>
      TrainingOverview.fromJson({
        'dataset': {
          'ready': false,
          'dataset_fingerprint': 'd' * 64,
          'sample_count': 0,
          'unique_channels': 0,
          'channel_leakage_count': 0,
          'by_leaf': [],
          'phase22': {'ready': false, 'by_leaf': [], 'out_of_scope': {}}
        },
        'policy': {
          'promotion_threshold': 0.8,
          'unknown_threshold': 0.6,
          'grouped_cv_folds': 5,
        },
        'runs': [],
        'models': {'total': 0, 'items': []},
        'active_model': null,
      });

  Map<String, dynamic> get overviewJson => {
        'preflight': ready
            ? {
                'ready': true,
                'reason_codes': [],
                'manifest_sha256': 'a' * 64,
                'counts': {
                  'fit': {'videos': 50, 'channels': 10},
                  'tuning': {'videos': 30, 'channels': 6},
                  'calibration': {'videos': 20, 'channels': 5},
                  'independent_test': {'videos': 30, 'channels': 10},
                }
              }
            : {
                'ready': false,
                'reason_codes': [
                  'phase2_frozen_manifest_missing',
                  'data_use_not_confirmed'
                ],
                'latest_phase2_report': {
                  'active_source_rows': 308,
                  'structurally_eligible_rows': 0,
                  'training_allowed_rows': 0,
                }
              },
        'runs': [],
        'models': {
          'total': 1,
          'items': [outcomeModelJson(canActivate: canActivate)]
        },
        'active_model': null,
        'independent_test_opened': false,
      };

  @override
  Future<OutcomeTrainingOverview> outcomeTrainingOverview() async =>
      OutcomeTrainingOverview.fromJson(overviewJson);

  @override
  Future<OutcomeTrainingRun> startOutcomeTraining(String manifestSha256) async {
    expect(manifestSha256, 'a' * 64);
    starts++;
    return OutcomeTrainingRun.fromJson({
      'run_id': '83f5f88e-136d-4eaa-b3ef-cabeb258719f',
      'status': 'queued',
      'stage': 'queued',
      'progress': 0,
      'manifest_sha256': manifestSha256,
      'created_at': '2026-10-09T10:00:00Z',
    });
  }

  @override
  Future<OutcomeModelSummary> outcomeModel(int id) async =>
      OutcomeModelSummary.fromJson(outcomeModelJson(canActivate: canActivate));

  @override
  Future<void> activateOutcomeModel(int id, int? activeId) async {
    activations++;
    if (rejectActivation) throw Exception('server rejected activation gate');
  }
}

Future<void> openOutcome(WidgetTester tester, OutcomeAdminRepository repository,
    {double width = 1000}) async {
  await tester.binding.setSurfaceSize(Size(width, 900));
  addTearDown(() async {
    await tester.pumpWidget(const SizedBox());
    await tester.binding.setSurfaceSize(null);
  });
  await tester.pumpWidget(
      MaterialApp(home: AdminTrainingScreen(repository: repository)));
  await tester.pumpAndSettle();
  await tester.tap(find.text('ประเมินผลตอบรับ'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('blocked readiness uses API facts and disables training',
      (tester) async {
    final repository = OutcomeAdminRepository();
    await openOutcome(tester, repository, width: 390);
    expect(find.text('ยังเริ่มเทรนไม่ได้'), findsOneWidget);
    expect(find.textContaining('Frozen manifest'), findsOneWidget);
    expect(find.textContaining('แถวต้นทาง 308'), findsOneWidget);
    expect(
        tester
            .widget<FilledButton>(
                find.byKey(const ValueKey('start-outcome-training')))
            .onPressed,
        isNull);
    expect(find.textContaining('Independent Test: ยังไม่ผ่าน'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
      'ready preflight starts a durable background run only after confirm',
      (tester) async {
    final repository = OutcomeAdminRepository()..ready = true;
    await openOutcome(tester, repository);
    await tester.tap(find.byKey(const ValueKey('start-outcome-training')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('ยกเลิก'));
    await tester.pumpAndSettle();
    expect(repository.starts, 0);
    await tester.tap(find.byKey(const ValueKey('start-outcome-training')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('ยืนยันเริ่มเทรน'));
    await tester.pump();
    expect(repository.starts, 1);
    expect(find.text('รอเริ่มเทรน'), findsWidgets);
  });

  testWidgets('activation rejection never reports success', (tester) async {
    final repository = OutcomeAdminRepository()
      ..canActivate = true
      ..rejectActivation = true;
    await openOutcome(tester, repository);
    await tester.tap(find.byTooltip('เปิดใช้ Outcome #7'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('ยืนยันเปิดใช้'));
    await tester.pumpAndSettle();
    expect(repository.activations, 1);
    expect(
        find.textContaining('server rejected activation gate'), findsOneWidget);
    expect(find.textContaining('เปิดใช้ Outcome model #7 แล้ว'), findsNothing);
  });

  testWidgets('model detail separates baselines calibration and sealed test',
      (tester) async {
    final repository = OutcomeAdminRepository();
    await openOutcome(tester, repository);
    await tester.tap(find.byTooltip('ดูผลประเมิน Outcome #7'));
    await tester.pumpAndSettle();
    expect(find.text('Constant baseline'), findsOneWidget);
    expect(find.text('Metadata + topics'), findsOneWidget);
    expect(find.text('Calibration'), findsOneWidget);
    expect(find.text('ยังไม่เปิดผล Independent Test'), findsOneWidget);
    expect(find.textContaining('Brier score ยิ่งต่ำ'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
