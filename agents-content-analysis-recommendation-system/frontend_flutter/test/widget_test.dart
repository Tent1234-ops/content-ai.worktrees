import 'package:content_ai_web/models/recommendation_result.dart';
import 'package:content_ai_web/models/dataset_review.dart';
import 'package:content_ai_web/repositories/admin_repository.dart';
import 'package:content_ai_web/screens/admin_dataset_review_screen.dart';
import 'package:content_ai_web/screens/login_screen.dart';
import 'package:content_ai_web/screens/result_screen.dart';
import 'package:content_ai_web/state/auth_controller.dart';
import 'package:content_ai_web/state/auth_scope.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('classification result displays hierarchy and Unknown/Other', () {
    final classified = ClassificationResult.fromJson({
      'domain': 'headphone',
      'confidence': 0.84,
      'rule_domain': 'audio',
      'source': 'youtube',
      'taxonomy_version': 'content-taxonomy-v1',
      'taxonomy_leaf_key': 'headphone',
      'category_level_1': 'Technology',
      'category_level_2': 'Electronics',
      'category_level_3': 'Headphone',
      'is_unknown': false,
      'taxonomy_ready': true,
      'candidates': <dynamic>[],
    });
    final unknown = ClassificationResult.fromJson({
      'domain': 'unknown',
      'confidence': 0.0,
      'rule_domain': 'keyboard',
      'source': 'youtube',
      'is_unknown': true,
      'candidates': <dynamic>[],
    });

    expect(
      classified.displayCategory,
      'Technology > Electronics > Headphone',
    );
    expect(unknown.displayCategory, 'Unknown/Other');
  });

  test('recommendation evidence keeps dataset lineage', () {
    final evidence = RecommendationEvidence.fromJson({
      'source': 'youtube_public_human_verified',
      'dataset_sources': ['youtube_public_research'],
      'dataset_versions': ['youtube-public-research-th-v1'],
      'source_record_ids': ['video000001', 'video000002'],
      'data_source_label': 'Human-reviewed public YouTube transcripts',
      'dataset_sample_size': 2,
      'eligible_pool_size': 5,
      'source_platform_counts': {'youtube': 2},
      'language_counts': {'th': 1, 'en': 1},
      'verification_status': 'human_verified',
      'license_name': 'YouTube Standard License',
    });

    expect(evidence.datasetSources, ['youtube_public_research']);
    expect(evidence.datasetVersions, ['youtube-public-research-th-v1']);
    expect(evidence.sourceRecordIds.length, 2);
    expect(evidence.eligiblePoolSize, 5);
    expect(evidence.languageCounts, {'th': 1, 'en': 1});
  });

  test('dataset review candidate keeps review controls and checks', () {
    final candidate = DatasetReviewCandidate.fromJson({
      'collection_run_id': 1,
      'dataset_version': 'youtube-cc-th-v1',
      'source_youtube_id': 'ikPAwWtj2qQ',
      'title': 'Galaxy Z Flip 6 Review',
      'video_url': 'https://www.youtube.com/watch?v=ikPAwWtj2qQ',
      'channel_title': 'Tech Maniac',
      'proposed_leaf_key': 'phone',
      'transcript_language': 'en',
      'caption_type': 'manual',
      'duration_seconds': 58,
      'transcript': 'Galaxy Z Flip phone review transcript',
      'transcript_preview': 'Galaxy Z Flip phone review transcript',
      'evidence_terms': ['phone'],
      'automated_checks': {
        'creative_commons': true,
        'within_five_minutes': true,
        'public_transcript': true,
      },
      'views': 11,
      'likes': 0,
      'comments': 0,
      'review_status': 'pending',
    });

    expect(candidate.reviewStatus, 'pending');
    expect(candidate.proposedLeafKey, 'phone');
    expect(candidate.durationSeconds, 58);
    expect(candidate.allAutomatedChecksPass, isTrue);
  });

  testWidgets('login screen renders expected fields',
      (WidgetTester tester) async {
    final controller = AuthController();
    addTearDown(controller.dispose);
    await tester.pumpWidget(
      MaterialApp(
        home: AuthScope(
          controller: controller,
          child: const LoginScreen(),
        ),
      ),
    );

    expect(find.text('Login'), findsAtLeastNWidgets(1));
    expect(find.text('Email'), findsOneWidget);
    expect(find.text('Password'), findsOneWidget);
    expect(find.text('Create account'), findsOneWidget);
  });

  testWidgets('admin dataset review shows approve and reject controls',
      (WidgetTester tester) async {
    await tester.binding.setSurfaceSize(const Size(1280, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      MaterialApp(
        home: AdminDatasetReviewScreen(
          repository: _FakeAdminRepository(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Galaxy Z Flip 6 Review'), findsOneWidget);
    expect(find.widgetWithText(FilledButton, 'Approve'), findsOneWidget);
    expect(find.widgetWithText(OutlinedButton, 'Reject'), findsOneWidget);
    expect(find.text('Phone 0/30'), findsOneWidget);
    expect(find.text('Review status'), findsNothing);
    expect(find.text('Collection run'), findsNothing);
    expect(find.text('Collection progress'), findsNothing);
  });

  testWidgets('approved dataset candidate leaves the pending queue',
      (WidgetTester tester) async {
    await tester.binding.setSurfaceSize(const Size(1280, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final repository = _FakeAdminRepository();
    await tester.pumpWidget(
      MaterialApp(
        home: AdminDatasetReviewScreen(repository: repository),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(FilledButton, 'Approve'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Confirm approval'));
    await tester.pumpAndSettle();

    expect(repository.reviewCalls, 1);
    expect(find.text('Galaxy Z Flip 6 Review'), findsNothing);
    expect(find.text('No candidates waiting for review'), findsOneWidget);
  });

  testWidgets('analysis result shows explicit states for empty outputs',
      (WidgetTester tester) async {
    await tester.binding.setSurfaceSize(const Size(1280, 2400));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final controller = AuthController();
    addTearDown(controller.dispose);
    final navigatorKey = GlobalKey<NavigatorState>();

    await tester.pumpWidget(
      AuthScope(
        controller: controller,
        child: MaterialApp(
          navigatorKey: navigatorKey,
          home: const Scaffold(body: SizedBox.shrink()),
        ),
      ),
    );
    navigatorKey.currentState!.push(
      MaterialPageRoute<void>(
        settings: RouteSettings(
          arguments: ResultScreenArgs(
            initialData: _analysisResultData(populated: false),
          ),
        ),
        builder: (_) => const ResultScreen(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('1. พบอะไรในคลิป'), findsOneWidget);
    expect(find.text('2. ควรเพิ่มอะไร'), findsOneWidget);
    expect(find.text('3. เพราะอะไรจึงแนะนำ'), findsOneWidget);
    await tester.tap(find.text('คำสำคัญและข้อความถอดเสียง'));
    await tester.pumpAndSettle();
    for (final heading in <String>[
      'คำสำคัญที่พบทั้งคลิป',
      'หัวข้อหลักที่ใช้เปรียบเทียบ',
      'คำสำคัญที่พบในช่วงเปิดคลิป',
      'คำแนะนำที่บันทึกไว้เดิม',
      'คำแนะนำช่วงเปิดที่บันทึกไว้เดิม',
    ]) {
      expect(find.text(heading), findsOneWidget);
    }
    expect(find.text('ความยาวคลิปที่แนะนำ'), findsOneWidget);
    expect(
      find.text('ยังไม่พบคำสำคัญจากเนื้อหาในคลิปนี้'),
      findsOneWidget,
    );
    expect(
      find.text('ยังไม่พบหัวข้อที่ระบบรู้จักสำหรับใช้เปรียบเทียบ'),
      findsOneWidget,
    );
    expect(
      find.text('ยังไม่พบคำสำคัญจากเสียงพูดในช่วงเปิดคลิป'),
      findsOneWidget,
    );
    expect(
      find.text('ไม่มีคำแนะนำคำสำคัญบันทึกไว้'),
      findsOneWidget,
    );
    expect(
      find.text('ไม่มีคำแนะนำช่วงเปิดบันทึกไว้'),
      findsOneWidget,
    );
    expect(
      find.text('ข้อมูลอ้างอิงยังไม่เพียงพอ'),
      findsAtLeastNWidgets(1),
    );
  });

  testWidgets('analysis result keeps detected and suggested outputs separate',
      (WidgetTester tester) async {
    await tester.binding.setSurfaceSize(const Size(1280, 2400));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final controller = AuthController();
    addTearDown(controller.dispose);
    final navigatorKey = GlobalKey<NavigatorState>();

    await tester.pumpWidget(
      AuthScope(
        controller: controller,
        child: MaterialApp(
          navigatorKey: navigatorKey,
          home: const Scaffold(body: SizedBox.shrink()),
        ),
      ),
    );
    navigatorKey.currentState!.push(
      MaterialPageRoute<void>(
        settings: RouteSettings(
          arguments: ResultScreenArgs(
            initialData: _analysisResultData(populated: true),
          ),
        ),
        builder: (_) => const ResultScreen(),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('คำสำคัญและข้อความถอดเสียง'));
    await tester.pumpAndSettle();
    expect(find.text('แบตเตอรี่'), findsOneWidget);
    expect(find.text('battery life'), findsAtLeastNWidgets(1));
    expect(find.text('ชิป'), findsOneWidget);
    expect(find.text('camera quality'), findsAtLeastNWidgets(1));
    expect(find.text('display quality'), findsOneWidget);
    expect(
      find.text('ยังไม่พบคำสำคัญจากเนื้อหาในคลิปนี้'),
      findsNothing,
    );
    expect(
      find.text('ยังไม่พบคำสำคัญจากเสียงพูดในช่วงเปิดคลิป'),
      findsNothing,
    );
  });
}

AnalysisResultViewData _analysisResultData({required bool populated}) {
  return AnalysisResultViewData.fromJson({
    'title': 'คลิปทดสอบ',
    'transcript': 'ทดสอบข้อความถอดเสียง',
    'saved': true,
    'analysis': <String, dynamic>{},
    'recommendation': {
      'domain': 'phone',
      'user_keywords': populated ? ['battery life'] : <String>[],
      'content_keywords': populated ? ['แบตเตอรี่'] : <String>[],
      'comparable_keywords': populated ? ['battery life'] : <String>[],
      'hook_terms': populated ? ['ชิป'] : <String>[],
      'missing_keywords': populated
          ? [
              {'keyword': 'camera quality', 'score': 0.8},
            ]
          : <Map<String, dynamic>>[],
      'hook_keywords': populated
          ? [
              {'keyword': 'display quality', 'score': 0.7},
            ]
          : <Map<String, dynamic>>[],
      'missing_dimensions': <Map<String, dynamic>>[],
      'recommended_duration': {
        'recommended_seconds': populated ? 75 : null,
        'recommended_range': populated ? '60-90 sec' : 'Insufficient evidence',
        'sample_size': populated ? 10 : 0,
        'minimum_sample_size': 10,
        'target_sample_size': 15,
        'source': populated ? 'youtube_metadata' : 'none',
        'evidence_status': populated ? 'sufficient' : 'insufficient_evidence',
        'cohort': 'upload_compatible_under_5m',
        'median_seconds': populated ? 75 : null,
        'percentile_low': 25,
        'percentile_high': 75,
      },
      'dataset_profile': {
        'domain': 'phone',
        'sample_size': populated ? 10 : 0,
        'source': populated ? 'youtube_public_human_verified' : 'none',
        'source_platform_counts': populated ? {'youtube': 10} : <String, int>{},
        'exemplar_titles': <String>[],
      },
      'evidence': <String, dynamic>{},
      'classification': {
        'domain': 'phone',
        'confidence': 0.91,
        'rule_domain': 'phone',
        'source': 'youtube_public_research',
        'taxonomy_version': 'content-taxonomy-v1',
        'taxonomy_leaf_key': 'phone',
        'category_level_1': 'Technology',
        'category_level_2': 'Electronics',
        'category_level_3': 'Phone',
        'is_unknown': false,
        'taxonomy_ready': true,
        'candidates': <Map<String, dynamic>>[],
      },
    },
  });
}

class _FakeAdminRepository extends AdminRepository {
  bool _pending = true;
  int reviewCalls = 0;

  @override
  Future<DatasetReviewQueueResult> listDatasetReviewQueue({
    required int limit,
    required int offset,
    String status = 'pending',
    String leafKey = 'all',
    int? collectionRunId,
    String search = '',
  }) async {
    return DatasetReviewQueueResult.fromJson({
      'total': _pending ? 1 : 0,
      'limit': limit,
      'offset': offset,
      'summary': {
        'total': 1,
        'pending': _pending ? 1 : 0,
        'approved': _pending ? 0 : 1,
        'rejected': 0,
      },
      'runs': [
        {
          'collection_run_id': 1,
          'dataset_version': 'youtube-cc-th-v1',
          'status': 'review_pending',
          'started_at': '2026-08-12T12:00:00Z',
          'total': 1,
          'pending': 1,
          'approved': 0,
          'rejected': 0,
        }
      ],
      'taxonomy': [
        {
          'leaf_key': 'phone',
          'category_level_1': 'Technology',
          'category_level_2': 'Electronics',
          'category_level_3': 'Phone',
          'minimum_sample_count': 30,
          'verified_sample_count': 0,
          'ready': false,
        }
      ],
      'items': _pending
          ? [
              {
                'collection_run_id': 1,
                'dataset_version': 'youtube-cc-th-v1',
                'source_youtube_id': 'ikPAwWtj2qQ',
                'title': 'Galaxy Z Flip 6 Review',
                'video_url': 'https://www.youtube.com/watch?v=ikPAwWtj2qQ',
                'channel_title': 'Tech Maniac',
                'proposed_leaf_key': 'phone',
                'transcript_language': 'en',
                'caption_type': 'manual',
                'duration_seconds': 58,
                'transcript': 'Galaxy Z Flip phone review transcript',
                'transcript_preview': 'Galaxy Z Flip phone review transcript',
                'evidence_terms': ['phone'],
                'automated_checks': {
                  'creative_commons': true,
                  'within_five_minutes': true,
                  'public_transcript': true,
                },
                'views': 11,
                'likes': 0,
                'comments': 0,
                'review_status': 'pending',
              }
            ]
          : [],
    });
  }

  @override
  Future<DatasetReviewDecisionResult> reviewDatasetCandidate({
    required DatasetReviewCandidate candidate,
    required String decision,
    bool requirePending = true,
    String? reviewedLeafKey,
    String? transcriptQuality,
    String notes = '',
  }) async {
    reviewCalls++;
    _pending = false;
    return DatasetReviewDecisionResult(
      status: 'success',
      decision: decision,
      youtubeId: candidate.youtubeId,
      collectionRunId: candidate.collectionRunId,
      reviewEventId: 1,
      datasetId: 1,
    );
  }
}
