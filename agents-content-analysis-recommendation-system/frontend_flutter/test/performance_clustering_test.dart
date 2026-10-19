import 'dart:async';
import 'package:content_ai_web/models/performance_clustering.dart';
import 'package:content_ai_web/models/reference_response.dart';
import 'package:content_ai_web/repositories/content_repository.dart';
import 'package:content_ai_web/ui/app_theme.dart';
import 'package:content_ai_web/widgets/performance_clustering_panel.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

// Deliberately synthetic UI fixtures; real-data evidence is stored separately.
Map<String, dynamic> fixture({String status = 'ready'}) => {
      'schema_version': 'performance-clustering-v1',
      'category': 'camera',
      'reference_count': 10,
      'eligible_count': 8,
      'minimum_views': 25000,
      'as_of': '2026-10-19T14:00:00Z',
      'excluded_counts': {'below_minimum_views': 2},
      'limitation': 'Low/High เปรียบเทียบภายในชุดอ้างอิงเท่านั้น',
      'clustering': {
        'status': 'ready',
        'clusters': [
          for (final level in ['low', 'high'])
            {
              'performance_level': level,
              'video_count': 4,
              'average_views': level == 'low' ? 30000 : 150000,
              'median_views': level == 'low' ? 30000 : 150000,
              'average_likes': level == 'low' ? 300 : 3000,
              'median_likes': level == 'low' ? 300 : 3000,
            }
        ]
      },
      'content_similarity': {
        'status': status,
        'low_score': 0.35,
        'high_score': 0.78,
        'closest_group': status == 'ready' ? 'high' : null,
        'reason': status == 'ready' ? null : 'similar_scores',
        'k_used': 4
      },
      'reference_videos': [
        for (var i = 1; i <= 8; i++)
          <String, dynamic>{
            'dataset_id': i,
            'video_id': 'testvid000$i',
            'title': 'คลิปทดสอบ $i',
            'channel_title': 'ช่อง $i',
            'published_at': '2026-05-19T12:00:00Z',
            'statistics_captured_at': '2026-10-19T14:00:00Z',
            'views': i < 5 ? 30000 : 150000,
            'likes': i < 5 ? 300 : 3000,
            'performance_level': i < 5 ? 'low' : 'high',
          }
      ],
      'shared_keywords': status == 'ready' ? ['กล้อง', 'แสงน้อย'] : [],
      'missing_keywords': status == 'ready' ? ['กันสั่น'] : [],
      'recommendations': [],
    };

class Repository extends ContentRepository {
  Repository(this.value);
  Map<String, dynamic> value;
  final List<int?> reads = [];
  final List<String?> topicReads = [];
  final List<int?> groupReads = [];
  bool fail = false;
  Completer<PerformanceComparison>? pending;
  @override
  Future<PerformanceComparison> getPerformanceComparison(int contentId,
      {int? minimumViews, String? topicId, int? groupIndex}) async {
    reads.add(minimumViews);
    topicReads.add(topicId);
    groupReads.add(groupIndex);
    if (fail) throw StateError('test offline');
    if (pending != null) return pending!.future;
    return PerformanceComparison.fromJson(value);
  }
}

Future<void> mount(WidgetTester tester, Repository repository,
    {Brightness brightness = Brightness.light,
     List<ReferenceResponseTopic> topics = const []}) async {
  await tester.pumpWidget(MaterialApp(
      theme: buildAppTheme(brightness),
      home: Scaffold(
          body: SingleChildScrollView(
              child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: PerformanceClusteringPanel(
                      contentId: 41, repository: repository, topics: topics))))));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('selecting saved evidence topic sends topic/group not free threshold',
      (tester) async {
    final now = DateTime.utc(2026, 10, 19);
    ReferenceResponseGroup group(int sourceIndex) => ReferenceResponseGroup(
      category: 'phone', format: 'long_form', ageGroup: 'age_90_365d',
      metricVersion: 'youtube_play_start_view_v2', thresholdViews: 14374,
      benchmarkSize: 30, benchmarkChannels: 30, sourceGroupIndex: sourceIndex,
      observedFrom: now, observedUntil: now, members: const []);
    final topics = [
      ReferenceResponseTopic(id: 'charging', title: 'ความเร็วในการชาร์จ',
        clips: const [], groups: [group(3), group(7)]),
      ReferenceResponseTopic(id: 'battery', title: 'แบตเตอรี่',
        clips: const [], groups: [group(9)]),
    ];
    final repo = Repository(fixture()..['selection'] = {
      'topic_sample_size': 29, 'passing_count': 16});
    await mount(tester, repo, topics: topics);
    expect(repo.topicReads, ['charging']);
    expect(repo.groupReads, [3]);
    expect(find.byKey(const ValueKey('performance-minimum-views')), findsNothing);
    expect(find.text('คลิปในหัวข้อ'), findsOneWidget);
    expect(find.text('ผ่าน Benchmark'), findsOneWidget);
    expect(find.text('29'), findsOneWidget);
    expect(find.text('16'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('performance-group-selector-charging')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('0/0 คลิป').last);
    await tester.pumpAndSettle();
    expect(repo.groupReads.last, 7);

    await tester.tap(find.byKey(const ValueKey('performance-topic-selector')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('แบตเตอรี่').last);
    await tester.pumpAndSettle();
    expect(repo.topicReads.last, 'battery');
    expect(repo.groupReads.last, 9);
  });

  test('parser rejects malformed KPI data and never substitutes zero scores',
      () {
    final absent = fixture();
    (absent['content_similarity'] as Map)['high_score'] = null;
    expect(PerformanceComparison.fromJson(absent).highScore, isNull);
    expect(PerformanceComparison.fromJson(absent).closest, isNull);
    final malformed = fixture();
    (malformed['reference_videos'] as List).first['likes'] = null;
    expect(
        () => PerformanceComparison.fromJson(malformed), throwsFormatException);
    final broken = fixture()..['eligible_count'] = 7;
    expect(() => PerformanceComparison.fromJson(broken), throwsFormatException);
  });

  for (final width in [390.0, 768.0, 1280.0, 1600.0]) {
    for (final brightness in Brightness.values) {
      testWidgets('real API-shaped values fit $width $brightness',
          (tester) async {
        await tester.binding.setSurfaceSize(Size(width, 1000));
        addTearDown(() => tester.binding.setSurfaceSize(null));
        final repo = Repository(fixture());
        await mount(tester, repo, brightness: brightness);
        expect(repo.reads, [null]);
        expect(find.text('วิเคราะห์กลุ่มผลงาน · Camera'), findsOneWidget);
        expect(find.text('35.00%'), findsOneWidget);
        expect(find.text('78.00%'), findsOneWidget);
        expect(find.text('ยอดวิวเฉลี่ย 150,000'), findsOneWidget);
        final filter = tester.widget<IconButton>(
            find.widgetWithIcon(IconButton, Icons.filter_alt_outlined));
        final context = tester.element(find.byType(PerformanceClusteringPanel));
        expect(filter.style!.foregroundColor!.resolve({}),
            Theme.of(context).colorScheme.onPrimary);
        final chart = tester.widget<ScatterChart>(find.byType(ScatterChart));
        expect(chart.data.scatterSpots.length, 8);
        final tooltip = chart.data.scatterTouchData.touchTooltipData
            .getTooltipItems(chart.data.scatterSpots.first)!;
        expect(tooltip.text, contains('คลิปทดสอบ 1'));
        expect(tooltip.text, contains('30,000'));
        expect(tooltip.text, contains('300'));
        final overlapping = chart.data.scatterTouchData.touchTooltipData
            .getTooltipItems(chart.data.scatterSpots[1])!;
        expect(overlapping.text, contains('คลิปทดสอบ 2'));
        await tester.ensureVisible(
            find.byKey(const ValueKey('performance-filter-high')));
        await tester.tap(find.byKey(const ValueKey('performance-filter-high')));
        await tester.pumpAndSettle();
        expect(find.byKey(const ValueKey('performance-video-1')), findsNothing);
        expect(
            find.byKey(const ValueKey('performance-video-8')), findsOneWidget);
        await tester.tap(find.byKey(const ValueKey('performance-filter-low')));
        await tester.pumpAndSettle();
        expect(
            find.byKey(const ValueKey('performance-video-1')), findsOneWidget);
        expect(find.byKey(const ValueKey('performance-video-5')), findsNothing);
        await tester.tap(find.byKey(const ValueKey('performance-filter-all')));
        await tester.pumpAndSettle();
        final more = find.text('ดูคลิปเพิ่มเติม');
        await tester.ensureVisible(more);
        await tester.tap(more);
        await tester.pumpAndSettle();
        expect(
            find.byKey(const ValueKey('performance-video-8')), findsOneWidget);
        expect(tester.takeException(), isNull);
      });
    }
  }

  testWidgets('inconclusive scores do not force a group or advice',
      (tester) async {
    await mount(tester, Repository(fixture(status: 'inconclusive')));
    expect(find.text('คะแนนความคล้ายสองกลุ่มใกล้กัน จึงยังสรุปไม่ได้'),
        findsOneWidget);
    expect(find.text('เนื้อหาใกล้เคียงกลุ่ม High มากกว่า'), findsNothing);
    expect(find.text('กันสั่น'), findsNothing);
    expect(
        find.text(
            'คะแนนนี้วัดความคล้ายของเนื้อหา ไม่ใช่การคาดการณ์ยอดวิวหรือยอดไลก์'),
        findsOneWidget);
  });

  testWidgets(
      'threshold reloads, rejects empty value, and shows insufficient state',
      (tester) async {
    final repo = Repository(fixture());
    await mount(tester, repo);
    final field = find.byKey(const ValueKey('performance-minimum-views'));
    await tester.ensureVisible(field);
    await tester.enterText(field, '');
    await tester.ensureVisible(find.byTooltip('คำนวณตามยอดวิวขั้นต่ำ'));
    await tester.tap(find.byTooltip('คำนวณตามยอดวิวขั้นต่ำ'));
    await tester.pumpAndSettle();
    expect(repo.reads.length, 1);
    repo.value = fixture()
      ..['eligible_count'] = 0
      ..['minimum_views'] = 9000000
      ..['clustering'] = {
        'status': 'insufficient_evidence',
        'reason': 'not_enough_references'
      };
    await tester.enterText(field, '9000000');
    await tester.ensureVisible(find.byTooltip('คำนวณตามยอดวิวขั้นต่ำ'));
    await tester.tap(find.byTooltip('คำนวณตามยอดวิวขั้นต่ำ'));
    await tester.pumpAndSettle();
    expect(repo.reads, [null, 9000000]);
    expect(find.byType(ScatterChart), findsNothing);
    expect(find.textContaining('ต้องมีอย่างน้อย 6 คลิป'), findsOneWidget);
  });

  testWidgets('load error is recoverable', (tester) async {
    final repo = Repository(fixture())..fail = true;
    await mount(tester, repo);
    expect(find.text('โหลดการเปรียบเทียบกลุ่มผลงานไม่สำเร็จ'), findsOneWidget);
    repo.fail = false;
    await tester.tap(find.text('ลองอีกครั้ง'));
    await tester.pumpAndSettle();
    expect(find.byType(ScatterChart), findsOneWidget);
  });

  testWidgets('disposed request never updates a dead panel', (tester) async {
    final repo = Repository(fixture())
      ..pending = Completer<PerformanceComparison>();
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body:
                PerformanceClusteringPanel(contentId: 41, repository: repo))));
    await tester.pumpWidget(const SizedBox());
    repo.pending!.complete(PerformanceComparison.fromJson(fixture()));
    await tester.pump();
    expect(tester.takeException(), isNull);
  });
}
