import 'package:content_ai_web/models/dashboard_overview.dart';
import 'package:content_ai_web/repositories/admin_repository.dart';
import 'package:content_ai_web/repositories/dashboard_repository.dart';
import 'package:content_ai_web/repositories/usage_statistics_repository.dart';
import 'package:content_ai_web/widgets/interest_preferences_panel.dart';
import 'package:content_ai_web/widgets/trend_settings_panel.dart';
import 'package:content_ai_web/widgets/usage_statistics_panel.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Future<void> frame(WidgetTester tester, Widget widget,
      {double width = 1000}) async {
    await tester.binding.setSurfaceSize(Size(width, 950));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(body: SingleChildScrollView(child: widget))));
    await tester.pumpAndSettle();
  }

  testWidgets(
      'statistics supports daily and monthly periods and personal scope',
      (tester) async {
    final repo = _Statistics();
    await frame(tester, UsageStatisticsPanel(repository: repo));
    expect(find.text('บันทึกสำเร็จ 2 ผล · เวลาไทย'), findsOneWidget);
    expect(find.text('วันที่ 1'), findsOneWidget);
    expect(repo.admin, false);
    await tester.tap(find.text('รายเดือน'));
    await tester.pumpAndSettle();
    expect(repo.month, isNull);
    expect(find.text('มกราคม'), findsOneWidget);
    expect(find.text('มือถือ: 2 ผล'), findsOneWidget);
    final before = repo.year!;
    await tester.tap(find.byTooltip('ปีก่อนหน้า'));
    await tester.pumpAndSettle();
    expect(repo.year, before - 1);
    expect(tester.takeException(), isNull);
  });

  testWidgets('statistics empty and error states do not show fabricated counts',
      (tester) async {
    final repo = _Statistics()..fail = true;
    await frame(tester, UsageStatisticsPanel(admin: true, repository: repo),
        width: 760);
    expect(find.text('โหลดสถิติไม่สำเร็จ'), findsOneWidget);
    expect(find.textContaining('บันทึกสำเร็จ'), findsNothing);
    repo.fail = false;
    repo.total = 0;
    await tester.tap(find.byTooltip('โหลดสถิติล่าสุด'));
    await tester.pumpAndSettle();
    expect(find.text('บันทึกสำเร็จ 0 ผล · เวลาไทย'), findsOneWidget);
    expect(repo.admin, true);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
      'trend schedule validates minimum and saves real fields including pause',
      (tester) async {
    final repo = _Schedule();
    await frame(tester, TrendSettingsPanel(repository: repo));
    await tester.enterText(find.byType(TextFormField).first, '30');
    await tester.tap(find.text('บันทึกรอบอัปเดต'));
    await tester.pumpAndSettle();
    expect(repo.saved, isNull);
    expect(find.text('ระบุ 60 ถึง 86400 วินาที'), findsOneWidget);
    await tester.enterText(find.byType(TextFormField).first, '120');
    await tester.enterText(find.byType(TextFormField).last, '900');
    await tester.tap(find.byType(Switch));
    await tester.tap(find.text('บันทึกรอบอัปเดต'));
    await tester.pumpAndSettle();
    expect(repo.saved, {
      'enabled': false,
      'global_interval_seconds': 120,
      'category_interval_seconds': 900,
      'schedule_mode': 'interval',
      'start_hour': 14,
      'end_hour': 23,
    });
    expect(find.text('พักอัปเดตอัตโนมัติ'), findsNWidgets(2));
    await tester.tap(find.byTooltip('โหลดรอบอัปเดตล่าสุด'));
    await tester.pumpAndSettle();
    expect(
        tester
            .widget<TextFormField>(find.byType(TextFormField).first)
            .controller!
            .text,
        '120');
    expect(tester.takeException(), isNull);
  });

  testWidgets(
      'trend schedule failed load retries and failed save is not success',
      (tester) async {
    final repo = _Schedule()..fail = true;
    await frame(tester, TrendSettingsPanel(repository: repo), width: 760);
    expect(find.byType(TextFormField), findsNothing);
    repo.fail = false;
    await tester.tap(find.byTooltip('โหลดรอบอัปเดตล่าสุด'));
    await tester.pumpAndSettle();
    repo.fail = true;
    await tester.tap(find.text('บันทึกรอบอัปเดต'));
    await tester.pumpAndSettle();
    expect(find.text('บันทึกไม่สำเร็จ ค่ายังไม่ถูกยืนยัน'), findsOneWidget);
    expect(find.text('บันทึกรอบอัปเดตเทรนด์แล้ว'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('daily schedule previews ten rounds and saves the window',
      (tester) async {
    final repo = _Schedule();
    await frame(tester, TrendSettingsPanel(repository: repo), width: 850);
    await tester.enterText(find.byType(TextFormField).first, '');
    await tester.tap(find.text('ตามเวลารายวัน'));
    await tester.pumpAndSettle();
    expect(find.text('ทุก 1 ชั่วโมง · 10 รอบ/วัน · เวลาไทย'), findsOneWidget);
    expect(find.byType(TextFormField), findsNothing);
    await tester.tap(find.text('บันทึกรอบอัปเดต'));
    await tester.pumpAndSettle();
    expect(repo.saved!['schedule_mode'], 'hourly_window');
    expect(repo.saved!['global_interval_seconds'], 3600);
    expect(repo.saved!['category_interval_seconds'], 3600);
    expect(repo.saved!['start_hour'], 14);
    expect(repo.saved!['end_hour'], 23);
    expect(find.text('รอบวันนี้'), findsOneWidget);
    expect(find.textContaining('สคริปต์ภายนอกติดต่อล่าสุด:'), findsOneWidget);
    await tester.tap(find.byTooltip('โหลดรอบอัปเดตล่าสุด'));
    await tester.pumpAndSettle();
    expect(find.text('ทุก 1 ชั่วโมง · 10 รอบ/วัน · เวลาไทย'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('daily schedule rejects end before start', (tester) async {
    final repo = _Schedule();
    await frame(tester, TrendSettingsPanel(repository: repo), width: 850);
    await tester.tap(find.text('ตามเวลารายวัน'));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(DropdownButtonFormField<int>).last);
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('13:00').last, -220,
        scrollable: find.byType(Scrollable).last);
    await tester.tap(find.text('13:00').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('บันทึกรอบอัปเดต'));
    await tester.pumpAndSettle();
    expect(repo.saved, isNull);
    expect(find.text('รอบสุดท้ายต้องไม่ก่อนรอบแรก'), findsWidgets);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
      'follow category uses provider ID, saves preferences and can unfollow',
      (tester) async {
    final repo = _Interests();
    await frame(
        tester,
        StatefulBuilder(
            builder: (context, update) => InterestPreferencesPanel(
                  repository: repo,
                  topics: List.of(repo.topics),
                  onChanged: () async {
                    update(() {});
                  },
                )),
        width: 760);
    expect(find.byType(CheckboxListTile), findsNWidgets(2));
    await tester.tap(find.text('เกม'));
    await tester.pumpAndSettle();
    expect(repo.topics.single.value, '20');
    expect(repo.topics.single.platform, 'youtube');
    expect(repo.topics.single.matchType, 'category');
    expect(
        tester
            .widget<CheckboxListTile>(find.byType(CheckboxListTile).first)
            .value,
        true);
    await tester.tap(find.text('เฉพาะที่ติดตาม'));
    await tester.pumpAndSettle();
    expect(repo.mode, 'following');
    await tester.tap(find.text('เกม'));
    await tester.pumpAndSettle();
    expect(repo.topics, isEmpty);
    expect(
        find.text('ยังไม่ได้ติดตามหมวดหรือหัวข้อ จึงยังไม่มีการแจ้งเตือนใหม่'),
        findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('failed interest load cannot overwrite preferences with defaults',
      (tester) async {
    final repo = _Interests()..fail = true;
    await frame(
        tester,
        InterestPreferencesPanel(
            repository: repo, topics: const [], onChanged: () async {}));
    expect(find.text('โหลดการติดตามไม่สำเร็จ'), findsOneWidget);
    for (final chip in tester.widgetList<ChoiceChip>(find.byType(ChoiceChip))) {
      expect(chip.onSelected, isNull);
    }
    repo.fail = false;
    await tester.tap(find.byTooltip('โหลดการติดตามล่าสุด'));
    await tester.pumpAndSettle();
    expect(find.byType(CheckboxListTile), findsNWidgets(2));
    expect(tester.takeException(), isNull);
  });
}

class _Statistics extends UsageStatisticsRepository {
  bool fail = false, admin = false;
  int total = 2;
  int? year, month;
  @override
  Future<Map<String, dynamic>> load(
      {required int year, int? month, bool admin = false}) async {
    if (fail) throw Exception('test unavailable');
    this.year = year;
    this.month = month;
    this.admin = admin;
    return {
      'total': total,
      'series': List.generate(month == null ? 12 : 30,
          (i) => {'index': i + 1, 'count': i == 0 ? total : 0}),
      'categories': total == 0
          ? []
          : [
              {'category': 'phone', 'count': total}
            ]
    };
  }
}

class _Schedule extends AdminRepository {
  @override
  Future<Map<String, dynamic>> sourceHealth() async => {'items': []};
  bool fail = false;
  Map<String, dynamic>? saved;
  @override
  Future<Map<String, dynamic>> trendSettings() async {
    if (fail) throw Exception('test unavailable');
    return {
      ...(saved ??
          {
            'enabled': true,
            'global_interval_seconds': 60,
            'category_interval_seconds': 60
          }),
      'window': {
        'start_hour': saved?['start_hour'] ?? 14,
        'end_hour': saved?['end_hour'] ?? 23,
        'next_at': null,
        'slots_today': [],
      },
      'worker': {'last_seen_at': null, 'status': null},
      'runs': {
        'global': {'last_success_at': null, 'next_at': null},
        'youtube_categories': {'last_success_at': null, 'next_at': null}
      }
    };
  }

  @override
  Future<Map<String, dynamic>> saveTrendSettings(
      Map<String, dynamic> values) async {
    if (fail) throw Exception('test unavailable');
    saved = values;
    return trendSettings();
  }
}

class _Interests extends DashboardRepository {
  bool fail = false;
  String mode = 'all';
  List<FollowedTopicItem> topics = [];
  @override
  Future<Map<String, dynamic>> followPreferences() async {
    if (fail) throw Exception('unavailable');
    return {
      'notification_mode': mode,
      'categories': [
        {'id': '20', 'title': 'Gaming'},
        {'id': '24', 'title': 'Entertainment'}
      ]
    };
  }

  @override
  Future<void> saveNotificationMode(String mode) async {
    this.mode = mode;
  }

  @override
  Future<FollowedTopicItem> followTopic(String value,
      {String matchType = 'keyword', String platform = 'all'}) async {
    final topic = FollowedTopicItem(
        id: 1,
        value: value,
        matchType: matchType,
        platform: platform,
        createdAt: '');
    topics.add(topic);
    return topic;
  }

  @override
  Future<void> unfollowTopic(int id) async {
    topics.removeWhere((t) => t.id == id);
  }
}
