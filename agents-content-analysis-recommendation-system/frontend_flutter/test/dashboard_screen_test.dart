import 'package:content_ai_web/models/dashboard_overview.dart';
import 'package:content_ai_web/models/trend_history.dart';
import 'package:content_ai_web/repositories/dashboard_repository.dart';
import 'package:content_ai_web/repositories/auth_repository.dart';
import 'package:content_ai_web/models/app_user.dart';
import 'package:content_ai_web/models/auth_session.dart';
import 'package:content_ai_web/screens/login_screen.dart';
import 'package:content_ai_web/routing/app_router.dart';
import 'package:content_ai_web/screens/upload_screen.dart';
import 'package:content_ai_web/screens/dashboard_screen.dart';
import 'package:content_ai_web/state/auth_controller.dart';
import 'package:content_ai_web/state/auth_scope.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));
  testWidgets('guest reads only public APIs, polls and can sign in to analyze',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1280, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final auth = AuthController(repository: _GuestAuthRepository());
    await auth.initialize();
    addTearDown(auth.dispose);
    final repository = _FakeDashboardRepository();
    final router = AppRouter(auth);
    await tester.pumpWidget(AuthScope(
        controller: auth,
        child: MaterialApp(
          onGenerateRoute: router.onGenerateRoute,
          home: DashboardScreen(repository: repository),
        )));
    await tester.pumpAndSettle();
    expect(repository.publicReads, 1);
    expect(repository.privateReads, 0);
    expect(find.text('การแจ้งเตือนเทรนด์'), findsNothing);
    expect(find.text('หัวข้อที่ติดตาม'), findsNothing);
    final more = find.byKey(const Key('trends-load-more'));
    await Scrollable.ensureVisible(tester.element(more), alignment: 0.5);
    await tester.pumpAndSettle();
    await tester.tap(more);
    await tester.pumpAndSettle();
    expect(repository.publicReads, 1);
    expect(repository.categoryReads, 1);
    await tester.pump(const Duration(seconds: 60));
    await tester.pumpAndSettle();
    expect(repository.publicReads, 2);
    expect(repository.privateReads, 0);

    final analyze = find.widgetWithText(FilledButton, 'วิเคราะห์คลิปของฉัน');
    await tester.scrollUntilVisible(analyze, -500,
        scrollable: find.byType(Scrollable).first);
    await Scrollable.ensureVisible(tester.element(analyze), alignment: 0.5);
    await tester.pumpAndSettle();
    await tester.tap(analyze);
    await tester.pumpAndSettle();
    expect(find.byType(LoginScreen), findsOneWidget);
    expect(find.byType(UploadScreen), findsNothing);
    expect(
        tester.widget<LoginScreen>(find.byType(LoginScreen)).destination.route,
        '/upload');
    await tester.enterText(
        find.byType(TextFormField).at(0), 'guest@example.com');
    await tester.enterText(find.byType(TextFormField).at(1), 'test-password');
    await tester.tap(find.widgetWithText(FilledButton, 'เข้าสู่ระบบ'));
    await tester.pumpAndSettle();
    expect(find.byType(UploadScreen), findsOneWidget);
    expect(find.byType(LoginScreen), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('logout clears private dashboard panels and resumes public reads',
      (tester) async {
    final auth = AuthController(repository: _GuestAuthRepository());
    await auth.initialize();
    await auth.login('guest@example.com', 'test-password');
    addTearDown(auth.dispose);
    final repository = _FakeDashboardRepository();
    await tester.pumpWidget(MaterialApp(
        home: AuthScope(
            controller: auth, child: DashboardScreen(repository: repository))));
    await tester.pumpAndSettle();
    expect(repository.privateReads, 4);
    expect(repository.publicReads, 0);
    await auth.logout();
    await tester.pumpAndSettle();
    expect(repository.publicReads, 1);
    expect(repository.privateReads, 4);
    expect(find.text('หัวข้อที่ติดตาม'), findsNothing);
    expect(find.text('การแจ้งเตือนเทรนด์'), findsNothing);
    expect(find.text('เข้าสู่ระบบ'), findsOneWidget);
  });

  testWidgets('cold private routes request login and keep their destination',
      (tester) async {
    for (final route in [
      '/upload',
      '/history',
      '/result',
      '/admin-datasets',
      '/admin-analysis-settings',
      '/admin-training',
      '/admin-users'
    ]) {
      final auth = AuthController(repository: _GuestAuthRepository());
      final router = AppRouter(auth);
      await tester.pumpWidget(AuthScope(
          controller: auth,
          child: MaterialApp(
            key: ValueKey(route),
            initialRoute: route,
            onGenerateRoute: router.onGenerateRoute,
          )));
      await auth.initialize();
      await tester.pumpAndSettle();
      expect(find.byType(LoginScreen), findsOneWidget);
      expect(
          tester
              .widget<LoginScreen>(find.byType(LoginScreen))
              .destination
              .route,
          route);
      await tester.pumpWidget(const SizedBox());
      auth.dispose();
    }
  });

  testWidgets('top-right inboxes open lists and keep failed writes visible',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1280, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final auth = AuthController(repository: _GuestAuthRepository());
    await auth.initialize();
    await auth.login('guest@example.com', 'test-password');
    addTearDown(auth.dispose);
    final repository = _FakeDashboardRepository()
      ..topics = [
        const FollowedTopicItem(
            id: 1,
            matchType: 'keyword',
            value: 'หัวข้อที่บันทึก',
            createdAt: '')
      ]
      ..messages = [
        NotificationItem.fromJson({
          'notification_id': 1,
          'platform': 'youtube',
          'title': 'เทรนด์ใหม่สำหรับคุณ'
        })
      ];
    await tester.pumpWidget(MaterialApp(
        home: AuthScope(
            controller: auth, child: DashboardScreen(repository: repository))));
    await tester.pumpAndSettle();
    expect(find.text('หมวดที่ติดตามและการแจ้งเตือน'), findsNothing);
    expect(find.text('หัวข้อที่บันทึก'), findsNothing);
    await tester.tap(find.byTooltip('การแจ้งเตือนเทรนด์'));
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsOneWidget);
    expect(find.text('เทรนด์ใหม่สำหรับคุณ'), findsOneWidget);
    repository.failWrite = true;
    await tester.tap(find.byTooltip('อ่านแล้ว'));
    await tester.pumpAndSettle();
    expect(find.text('ดำเนินการไม่สำเร็จ กรุณาลองอีกครั้ง'), findsOneWidget);
    expect(find.byTooltip('อ่านแล้ว'), findsOneWidget);
    repository.failWrite = false;
    await tester.tap(find.byTooltip('อ่านแล้ว'));
    await tester.pumpAndSettle();
    expect(find.byTooltip('อ่านแล้ว'), findsNothing);
    await tester.tap(find.byTooltip('ปิด'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('หัวข้อที่ติดตาม'));
    await tester.pumpAndSettle();
    expect(find.text('หัวข้อที่บันทึก'), findsOneWidget);
    repository.failWrite = true;
    await tester.tap(find.byTooltip('เลิกติดตาม'));
    await tester.pumpAndSettle();
    expect(find.text('หัวข้อที่บันทึก'), findsOneWidget);
    repository.failWrite = false;
    await tester.tap(find.byTooltip('เลิกติดตาม'));
    await tester.pumpAndSettle();
    expect(find.text('ยังไม่มีหัวข้อที่ติดตาม'), findsOneWidget);
    await auth.logout();
    await tester.pumpAndSettle();
    expect(find.text('กรุณาเข้าสู่ระบบเพื่อดูข้อมูลส่วนตัว'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('dashboard keeps platform rankings in separate tabs',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1280, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final authController = AuthController();
    addTearDown(authController.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: AuthScope(
          controller: authController,
          child: DashboardScreen(repository: _FakeDashboardRepository()),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(TabBar), findsOneWidget);
    expect(find.text('YouTube'), findsOneWidget);
    expect(find.text('Google'), findsOneWidget);
    expect(find.text('TikTok'), findsNothing);
    expect(find.text('Current Trend Strength'), findsNothing);
    expect(find.text('Fastest Rising'), findsNothing);
    expect(find.text('Stable'), findsNothing);
    expect(find.text('Momentum Score'), findsNothing);
    expect(find.text('ค้นหาชื่อหรือหมวดหมู่'), findsNothing);
    expect(find.byType(TextField), findsNothing);

    await tester.scrollUntilVisible(
      find.text('อันดับวิดีโอบน YouTube ตอนนี้').first,
      250,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('อันดับวิดีโอบน YouTube ตอนนี้'), findsOneWidget);
    expect(find.text('อันดับคำค้นบน Google ตอนนี้'), findsNothing);

    await tester.tap(find.text('Google').first);
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('อันดับคำค้นบน Google ตอนนี้').first,
      -250,
      scrollable: find.byType(Scrollable).first,
    );

    expect(find.text('อันดับคำค้นบน Google ตอนนี้'), findsOneWidget);
    expect(find.text('อันดับวิดีโอบน YouTube ตอนนี้'), findsNothing);
    expect(find.text('Google search trend'), findsOneWidget);
    expect(find.text('YouTube video 1'), findsNothing);

    const firstRoundMessage =
        'ยังไม่มี Snapshot รอบก่อนสำหรับเปรียบเทียบอันดับ';
    await tester.drag(
      find.byType(Scrollable).first,
      const Offset(0, -500),
    );
    await tester.pumpAndSettle();
    expect(find.text(firstRoundMessage), findsNothing);
    expect(find.text('อันดับคำค้นขยับขึ้นล่าสุดบน Google'), findsNothing);
    expect(find.text('เทรนด์ตามหมวดหมู่'), findsNothing);
  });

  testWidgets(
      'overall ranking displays category donut without movement section',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1280, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final authController = AuthController();
    addTearDown(authController.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: AuthScope(
          controller: authController,
          child: DashboardScreen(
            repository: _FakeDashboardRepository(
              snapshotJson: _stableSnapshotJson(),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('อันดับวิดีโอขยับขึ้นล่าสุดบน YouTube'), findsNothing);
    await tester.scrollUntilVisible(
      find.text('เทรนด์ตามหมวดหมู่').first,
      500,
      maxScrolls: 20,
      scrollable: find.byType(Scrollable).first,
    );
    expect(
      find.text('สัดส่วนจาก 5 คลิปในอันดับรวม YouTube (สูงสุด 50)'),
      findsOneWidget,
    );
    expect(find.text('5 คลิป (100%)'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('youtube category uses its own 1 to 50 ranking', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1280, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final authController = AuthController();
    addTearDown(authController.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: AuthScope(
          controller: authController,
          child: DashboardScreen(repository: _FakeDashboardRepository()),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final categoryDropdown = find.byType(DropdownButtonFormField<String>);
    await tester.scrollUntilVisible(
      categoryDropdown,
      250,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(categoryDropdown);
    await tester.pumpAndSettle();
    await tester.tap(find.text('บันเทิง (50)').last);
    await tester.pumpAndSettle();

    expect(find.text('อันดับวิดีโอ YouTube หมวดบันเทิง'), findsOneWidget);
    expect(find.text('Category 24 video 1'), findsOneWidget);
    expect(find.text('Category 24 video 13'), findsNothing);
    for (var page = 0; page < 4; page++) {
      final more = find.byKey(const Key('trends-load-more'));
      await Scrollable.ensureVisible(tester.element(more), alignment: 0.5);
      await tester.pumpAndSettle();
      await tester.tap(more);
      await tester.pumpAndSettle();
    }
    expect(find.byKey(const Key('trends-load-more')), findsNothing);
    expect(find.text('Category 24 video 50'), findsOneWidget);
    expect(find.text('#50'), findsOneWidget);
    expect(find.text('YouTube video 1'), findsNothing);
    expect(find.text('เทรนด์ตามหมวดหมู่'), findsNothing);
  });

  testWidgets('top trend opens details from the current list without history',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1280, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final authController = AuthController();
    addTearDown(authController.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: AuthScope(
          controller: authController,
          child: DashboardScreen(repository: _FakeDashboardRepository()),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(find.text('YouTube video 1'), 250,
        scrollable: find.byType(Scrollable).first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('YouTube video 1'));
    await tester.pumpAndSettle();

    expect(find.text('รายละเอียดเทรนด์'), findsOneWidget);
    expect(find.text('Test creator channel'), findsWidgets);
    expect(find.text('1,234'), findsOneWidget);
    expect(find.text('2:05'), findsWidgets);
    expect(find.text('คำอธิบายจากช่อง'), findsOneWidget);
    expect(find.text('Description supplied by the channel'), findsOneWidget);
    expect(find.text('ดูบน YouTube'), findsOneWidget);
    expect(find.text('ประวัติอันดับที่ระบบเก็บไว้'), findsNothing);
    expect(find.textContaining('โหลดประวัติเพิ่มเติมไม่สำเร็จ'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('trend details hide metadata fields that are unavailable',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1280, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final authController = AuthController();
    addTearDown(authController.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: AuthScope(
          controller: authController,
          child: DashboardScreen(repository: _FakeDashboardRepository()),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('YouTube video 2'),
      250,
      scrollable: find.byType(Scrollable).first,
    );

    await Scrollable.ensureVisible(tester.element(find.text('YouTube video 2')),
        alignment: 0.5);
    await tester.pumpAndSettle();
    await tester.tap(find.text('YouTube video 2'));
    await tester.pumpAndSettle();

    expect(find.text('รายละเอียดเทรนด์'), findsOneWidget);
    expect(find.text('ความยาว'), findsNothing);
    expect(find.text('สถิติปัจจุบันจาก YouTube'), findsNothing);
    expect(find.text('คำอธิบายจากช่อง'), findsNothing);
    expect(find.text('ไม่มีข้อมูล'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('google trend details show approximate search-volume evidence',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1280, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final authController = AuthController();
    addTearDown(authController.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: AuthScope(
          controller: authController,
          child: DashboardScreen(repository: _FakeDashboardRepository()),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Google').first);
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('Google search trend'),
      250,
      scrollable: find.byType(Scrollable).first,
    );

    await tester.tap(find.text('Google search trend'));
    await tester.pumpAndSettle();

    expect(find.text('จำนวนการค้นหาโดยประมาณ'), findsOneWidget);
    expect(find.text('ประมาณ 50,000 ครั้ง'), findsOneWidget);
    expect(find.textContaining('ไม่ใช่จำนวนผู้ใช้แบบไม่ซ้ำ'), findsOneWidget);
    expect(
        find.textContaining('อันดับ #1 คือลำดับ Trending Now'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('platform tabs fit a narrow web viewport', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final authController = AuthController();
    addTearDown(authController.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: AuthScope(
          controller: authController,
          child: DashboardScreen(repository: _FakeDashboardRepository()),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(TabBar), findsOneWidget);
    expect(find.text('YouTube'), findsOneWidget);
    expect(find.text('Google'), findsOneWidget);
    expect(find.text('TikTok'), findsNothing);
    expect(tester.takeException(), isNull);

    await tester.tap(find.text('Google'));
    await tester.pumpAndSettle();
    expect(find.text('TikTok ยังไม่พร้อมใช้งาน'), findsNothing);
    expect(find.text('หมวดหมู่'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
      'trend detail uses a full-width narrow web panel without overflow',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final authController = AuthController();
    addTearDown(authController.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: AuthScope(
          controller: authController,
          child: DashboardScreen(repository: _FakeDashboardRepository()),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('YouTube video 1'), 250,
        scrollable: find.byType(Scrollable).first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('YouTube video 1'));
    await tester.pumpAndSettle();

    expect(find.text('รายละเอียดเทรนด์'), findsOneWidget);
    expect(find.text('อันดับรวมบน YouTube'), findsOneWidget);
    expect(find.text('การเปลี่ยนแปลงจากรอบก่อน'), findsOneWidget);
    expect(find.text('อันดับคงเดิม'), findsWidgets);
    expect(find.text('ดูบน YouTube'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

class _FakeDashboardRepository extends DashboardRepository {
  @override
  Future<TrendHistory> getTrendHistory(
          {required String platform,
          int days = 5,
          String? categoryId,
          String? itemKey}) async =>
      TrendHistory.fromJson({});

  _FakeDashboardRepository({Map<String, dynamic>? snapshotJson})
      : _snapshot = LiveTrendSnapshot.fromJson(snapshotJson ?? _snapshotJson()),
        _overview = DashboardOverview.fromJson(_overviewJson());

  final LiveTrendSnapshot _snapshot;
  final DashboardOverview _overview;
  int publicReads = 0;
  int privateReads = 0;
  int categoryReads = 0;
  List<FollowedTopicItem> topics = [];
  List<NotificationItem> messages = [];
  bool failWrite = false;

  @override
  Future<void> unfollowTopic(int id) async {
    if (failWrite) throw Exception('offline');
    topics.removeWhere((t) => t.id == id);
  }

  @override
  Future<void> markNotificationsRead(List<int> ids) async {
    if (failWrite) throw Exception('offline');
    messages = messages
        .map((n) => NotificationItem.fromJson({
              'notification_id': n.id,
              'platform': n.platform,
              'title': n.title,
              'is_read': ids.contains(n.id) || n.isRead,
            }))
        .toList();
  }

  @override
  Future<Map<String, dynamic>> followPreferences() async =>
      {'notification_mode': 'all', 'categories': []};

  @override
  Future<LiveTrendSnapshot> getPublicTrendSnapshot({int limit = 50}) async {
    publicReads++;
    return _snapshot;
  }

  @override
  Future<DashboardOverview> getOverview() async {
    privateReads++;
    return _overview;
  }

  @override
  Future<LiveTrendSnapshot> getLiveTrendSnapshot({int limit = 50}) async {
    privateReads++;
    return _snapshot;
  }

  @override
  Future<YouTubeCategoryTrendSnapshot> getYouTubeCategoryTrendSnapshot({
    String? categoryId,
    int limit = 50,
  }) async {
    categoryReads++;
    return YouTubeCategoryTrendSnapshot.fromJson(
      _youtubeCategorySnapshotJson(categoryId: categoryId),
    );
  }

  @override
  Future<List<FollowedTopicItem>> getFollowedTopics() async {
    privateReads++;
    return List.of(topics);
  }

  @override
  Future<List<NotificationItem>> getNotifications({
    bool unreadOnly = false,
    int limit = 20,
  }) async {
    privateReads++;
    return List.of(messages);
  }
}

class _GuestAuthRepository extends AuthRepository {
  @override
  Future<AuthSession?> restoreSession() async => null;

  @override
  Future<AuthSession> login(String email, String password) async =>
      const AuthSession(
        accessToken: 'test-token',
        sessionKey: 'test-session',
        user: AppUser(
            userId: 1,
            username: 'Test',
            email: 'guest@example.com',
            role: 'user',
            isActive: true),
      );

  @override
  Future<void> logout() async {}
}

Map<String, dynamic> _overviewJson() {
  final snapshot = _snapshotJson();
  final platforms = snapshot['platforms'] as Map<String, dynamic>;
  return {
    'user_role': 'user',
    'metrics': {
      'total_dataset_contents': 0,
      'total_users': 0,
      'my_analysis_results': 0,
    },
    'youtube_trends': platforms['youtube'],
    'google_trends': platforms['google'],
    'tiktok_trends': platforms['tiktok'],
    'top_trends': <dynamic>[],
    'platform_summaries': <dynamic>[],
    'platform_comparison': <dynamic>[],
    'source_distribution': <dynamic>[],
  };
}

Map<String, dynamic> _snapshotJson() {
  final youtubeItems = List.generate(
    12,
    (index) => _trendItem(
      title: 'YouTube video ${index + 1}',
      platform: 'youtube_live',
      rank: index + 1,
      category: 'Technology',
      includeMetadata: index != 1,
    ),
  )
    ..add(
      _trendItem(
        title: 'YouTube climber',
        platform: 'youtube_live',
        rank: 13,
        rankChange: 5,
        category: 'Technology',
        changeKind: 'rank_up',
        meaningfulRising: true,
      ),
    )
    ..add(
      _trendItem(
        title: 'YouTube newcomer',
        platform: 'youtube_live',
        rank: 14,
        category: 'Technology',
        changeKind: 'new',
        isNew: true,
        hasPreviousSnapshot: false,
      ),
    );
  return {
    'generated_at': '2026-08-31T10:30:00Z',
    'new_count': 0,
    'new_notifications': <dynamic>[],
    'platforms': {
      'youtube': {'mode': 'live', 'items': youtubeItems},
      'google': {
        'mode': 'live',
        'items': [
          _trendItem(
            title: 'Google search trend',
            platform: 'google_trends_live',
            rank: 1,
            category: 'Search',
            changeKind: 'baseline',
            hasPreviousSnapshot: false,
          ),
        ],
      },
      'tiktok': {'mode': 'live', 'items': <dynamic>[]},
    },
  };
}

Map<String, dynamic> _stableSnapshotJson() {
  final snapshot = _snapshotJson();
  final platforms = snapshot['platforms'] as Map<String, dynamic>;
  platforms['youtube'] = {
    'mode': 'live',
    'items': List.generate(
      5,
      (index) => _trendItem(
        title: 'Stable YouTube video ${index + 1}',
        platform: 'youtube_live',
        rank: index + 1,
        category: 'Technology',
      ),
    ),
  };
  return snapshot;
}

Map<String, dynamic> _youtubeCategorySnapshotJson({String? categoryId}) {
  final categories = [
    {
      'category_id': '24',
      'title': 'Entertainment',
      'total': 50,
      'provider_status': 'ok',
    },
    {
      'category_id': '20',
      'title': 'Gaming',
      'total': 50,
      'provider_status': 'ok',
    },
  ];
  final selected = categoryId == null
      ? null
      : {
          ...categories.firstWhere(
            (item) => item['category_id'] == categoryId,
          ),
          'ranking_scope': 'category:$categoryId',
          'has_previous_snapshot': true,
          'items': List.generate(
            50,
            (index) => {
              ..._trendItem(
                title: 'Category $categoryId video ${index + 1}',
                platform: 'youtube_live',
                rank: index + 1,
                category: categoryId == '24' ? 'Entertainment' : 'Gaming',
                rankChange: index == 1 ? 3 : 0,
                changeKind: index == 1 ? 'rank_up' : 'none',
                meaningfulRising: index == 1,
              ),
              'category_id': categoryId,
              'ranking_scope': 'category:$categoryId',
            },
          ),
        };
  return {
    'run_id': 20,
    'snapshot_status': 'completed',
    'generated_at': '2026-08-31T10:45:00Z',
    'region': 'TH',
    'refresh_interval_seconds': 60,
    'categories': categories,
    'selected_category': selected,
  };
}

Map<String, dynamic> _trendItem({
  required String title,
  required String platform,
  required int rank,
  required String category,
  int rankChange = 0,
  String changeKind = 'none',
  bool meaningfulRising = false,
  bool hasPreviousSnapshot = true,
  bool isNew = false,
  bool includeMetadata = true,
}) {
  return {
    'key': '$platform:$title',
    'platform': platform.contains('youtube')
        ? 'youtube'
        : platform.contains('google')
            ? 'google'
            : 'tiktok',
    'title': title,
    'source_platform': platform,
    'video_url': 'https://example.test/video',
    if (includeMetadata && !platform.contains('google')) ...{
      'channel_title': 'Test creator channel',
      'description': 'Description supplied by the channel',
      'duration_seconds': 125,
      'published_at': '2026-08-31T10:00:00Z',
      'views': 1234,
      'likes': 120,
      'comments': 15,
      'views_available': true,
      'likes_available': true,
      'comments_available': true,
    },
    if (platform.contains('google')) 'trend_score': 50000,
    'category': category,
    'rank': rank,
    'rank_change': rankChange,
    'change_kind': changeKind,
    'change_label': '',
    'is_meaningful_rising': meaningfulRising,
    'has_previous_snapshot': hasPreviousSnapshot,
    'comparison_window_seconds': hasPreviousSnapshot ? 60 : 0,
    'is_new': isNew,
  };
}
