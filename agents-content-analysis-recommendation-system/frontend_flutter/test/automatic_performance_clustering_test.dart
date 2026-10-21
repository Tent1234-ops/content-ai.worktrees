import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:content_ai_web/models/performance_overview.dart';
import 'package:content_ai_web/models/performance_clustering.dart';
import 'package:content_ai_web/models/reference_response.dart';
import 'package:content_ai_web/repositories/content_repository.dart';
import 'package:content_ai_web/widgets/automatic_performance_clustering_panel.dart';

Map<String, dynamic> overviewFixture() => {
  'schema_version': 'performance-clustering-overview-v1',
  'content_id': 41,
  'category': 'phone',
  'status': 'ready',
  'limitation': 'คะแนนความคล้ายไม่ใช่การทำนายยอดวิว',
  'topic_count': 2,
  'group_count': 2,
  'ready_count': 1,
  'high_count': 1,
  'low_count': 0,
  'inconclusive_count': 1,
  'groups': [
    {
      'topic_id': 'charging',
      'topic_title': 'ความเร็วในการชาร์จ',
      'group_index': 3,
      'format': 'long_form',
      'age_group': 'age_90_365d',
      'threshold_views': 14374,
      'topic_sample_size': 29,
      'passing_count': 16,
      'eligible_count': 15,
      'clustering_status': 'ready',
      'similarity_status': 'ready',
      'low_score': 0.11,
      'high_score': 0.25,
      'closest_group': 'high',
      'reason': null,
    },
    {
      'topic_id': 'camera',
      'topic_title': 'กล้อง',
      'group_index': 0,
      'format': 'long_form',
      'age_group': 'age_90_365d',
      'threshold_views': 5000,
      'topic_sample_size': 19,
      'passing_count': 11,
      'eligible_count': 11,
      'clustering_status': 'ready',
      'similarity_status': 'inconclusive',
      'low_score': 0.13,
      'high_score': 0.14,
      'closest_group': null,
      'reason': 'similar_scores',
    },
  ],
};

Map<String, dynamic> detailFixture() => {
  'schema_version': 'performance-clustering-v1',
  'category': 'phone',
  'reference_count': 16,
  'eligible_count': 0,
  'minimum_views': 14374,
  'as_of': '2026-10-19T14:00:00Z',
  'excluded_counts': {},
  'limitation': 'Only descriptive comparison',
  'clustering': {
    'status': 'insufficient_evidence',
    'reason': 'not_enough_references',
    'clusters': [],
  },
  'content_similarity': {
    'status': 'insufficient_evidence',
    'reason': 'clustering_unavailable',
    'low_score': null, 'high_score': null,
    'closest_group': null,
    'k_used': 0,
  },
  'reference_videos': [],
  'recommendations': [],
  'shared_keywords': [],
  'missing_keywords': [],
};

class FakeRepository extends ContentRepository {
  FakeRepository(this.data);
  Map<String, dynamic> data;
  bool fail = false;
  int overviewReads = 0;
  int detailReads = 0;
  // This legacy overview API is not declared on ContentRepository anymore.
  Future<PerformanceOverview> getAutomaticPerformanceOverview(int contentId) async {
    overviewReads++;
    if (fail) throw StateError('offline');
    return PerformanceOverview.fromJson(data);
  }

  @override
  Future<PerformanceComparison> getPerformanceComparison(int contentId,
      {int? minimumViews,
      String? topicId,
      int? groupIndex,
      String comparisonMethod = 'embedding_centroid'}) async {
    detailReads++;
    return PerformanceComparison.fromJson(detailFixture());
  }
}

ReferenceResponseTopic topic(String id, String title, int groupIndex) {
  final now = DateTime.utc(2026, 10, 19);
  return ReferenceResponseTopic(
    id: id, title: title, clips: const [],
    groups: [ReferenceResponseGroup(
      category: 'phone', format: 'long_form',
      ageGroup: 'age_90_365d',
      metricVersion: 'youtube_play_start_view_v2',
      thresholdViews: 14374, benchmarkSize: 30,
      benchmarkChannels: 30, sourceGroupIndex: groupIndex,
      observedFrom: now, observedUntil: now, members: const [],
    )],
  );
}

Future<void> pumpPanel(WidgetTester tester, FakeRepository repo) async {
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(body: SingleChildScrollView(
      child: AutomaticPerformanceClusteringPanel(
        contentId: 41, repository: repo,
        topics: [
          topic('charging', 'ความเร็วในการชาร์จ', 3),
          topic('camera', 'กล้อง', 0),
        ],
      ),
    )),
  ));
  await tester.pumpAndSettle();
}

void main() {
  test('overview parser rejects invented High/Low and inconsistent counts', () {
    final invalid = overviewFixture();
    (invalid['groups'] as List)[1]['closest_group'] = 'high';
    expect(() => PerformanceOverview.fromJson(invalid), throwsFormatException);
    final counts = overviewFixture()..['ready_count'] = 2;
    expect(() => PerformanceOverview.fromJson(counts), throwsFormatException);
  });

  testWidgets('all saved topics display automatically before opening dropdown',
      (tester) async {
    final repo = FakeRepository(overviewFixture());
    await pumpPanel(tester, repo);
    expect(repo.overviewReads, 1);
    expect(repo.detailReads, 0);
    expect(find.byKey(const ValueKey('automatic-performance-overview')),
        findsOneWidget);
    expect(find.text('ความเร็วในการชาร์จ'), findsOneWidget);
    expect(find.text('กล้อง'), findsOneWidget);
    expect(find.textContaining('29 คลิป'), findsOneWidget);
    expect(find.textContaining('16 คลิป'), findsWidgets);
    expect(find.text('เนื้อหาคล้ายกลุ่ม High มากกว่า'), findsOneWidget);
    expect(find.textContaining('ยังสรุปไม่ได้'), findsWidgets);
    expect(find.byKey(const ValueKey('performance-topic-selector')),
        findsNothing);
    await tester.ensureVisible(
        find.byKey(const ValueKey('automatic-performance-detail-toggle')));
    await tester.tap(
        find.byKey(const ValueKey('automatic-performance-detail-toggle')));
    await tester.pumpAndSettle();
    expect(repo.detailReads, 1);
    expect(find.byKey(const ValueKey('performance-topic-selector')),
        findsOneWidget);
  });

  testWidgets('empty saved evidence does not fall back to category KMeans',
      (tester) async {
    final raw = overviewFixture()..['status'] = 'no_saved_topic_groups'
      ..['topic_count'] = 0
      ..['group_count'] = 0
      ..['ready_count'] = 0
      ..['high_count'] = 0
      ..['inconclusive_count'] = 0
      ..['groups'] = [];
    final repo = FakeRepository(raw);
    await pumpPanel(tester, repo);
    expect(find.textContaining('ยังไม่มีชุดหลักฐานอ้างอิงรายหัวข้อ'),
        findsOneWidget);
    expect(repo.detailReads, 0);
  });

  testWidgets('overview load error has a working retry', (tester) async {
    final repo = FakeRepository(overviewFixture())..fail = true;
    await pumpPanel(tester, repo);
    expect(find.text('โหลดผลวิเคราะห์ทุกหัวข้ออัตโนมัติไม่สำเร็จ'),
        findsOneWidget);
    repo.fail = false;
    await tester.tap(find.byKey(
        const ValueKey('automatic-performance-retry')));
    await tester.pumpAndSettle();
    expect(find.text('ความเร็วในการชาร์จ'), findsOneWidget);
    expect(repo.overviewReads, 2);
  });
}
