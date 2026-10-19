import 'package:content_ai_web/models/common_models.dart';
import 'package:content_ai_web/models/content_history.dart';
import 'package:content_ai_web/repositories/content_repository.dart';
import 'package:content_ai_web/screens/history_screen.dart';
import 'package:content_ai_web/state/auth_controller.dart';
import 'package:content_ai_web/state/auth_scope.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:content_ai_web/ui/app_theme.dart';
import 'package:content_ai_web/screens/result_screen.dart';

class HistoryRepository extends ContentRepository {
  @override
  Future<PaginatedResult<ContentHistoryItem>> listMyContents(
          {int limit = 20, int offset = 0}) async =>
      PaginatedResult(total: 3, items: [
        ContentHistoryItem.fromJson({
          'content_id': 3,
          'title': 'Newest camera',
          'domain': 'camera',
          'created_at': '2026-10-18T12:00:00Z',
          'recommended_duration': 79
        }),
        ContentHistoryItem.fromJson(
            {'content_id': 2, 'title': 'Middle phone', 'domain': 'phone'}),
        ContentHistoryItem.fromJson(
            {'content_id': 1, 'title': 'Oldest camera', 'domain': 'camera'}),
      ]);
}

void main() {
  testWidgets('history preserves newest first API order when filtering',
      (tester) async {
    SharedPreferences.setMockInitialValues({});
    await tester.binding.setSurfaceSize(const Size(800, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final auth = AuthController();
    addTearDown(auth.dispose);
    await tester.pumpWidget(AuthScope(
        controller: auth,
        child: MaterialApp(
          home: HistoryScreen(repository: HistoryRepository()),
        )));
    await tester.pumpAndSettle();
    expect(find.text('เรียงตาม'), findsNothing);
    expect(find.byType(DropdownButtonFormField<String>), findsOneWidget);
    expect(tester.getTopLeft(find.text('Newest camera')).dy,
        lessThan(tester.getTopLeft(find.text('Middle phone')).dy));
    expect(tester.getTopLeft(find.text('Middle phone')).dy,
        lessThan(tester.getTopLeft(find.text('Oldest camera')).dy));
    await tester.tap(find.byType(DropdownButtonFormField<String>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('camera').last);
    await tester.pumpAndSettle();
    expect(find.text('Middle phone'), findsNothing);
    expect(tester.getTopLeft(find.text('Newest camera')).dy,
        lessThan(tester.getTopLeft(find.text('Oldest camera')).dy));
    expect(tester.takeException(), isNull);
  });

  for (final width in [390.0, 768.0, 1280.0, 1600.0]) {
    for (final brightness in Brightness.values) {
      testWidgets(
          'history cards keep reading order and route at $width $brightness',
          (tester) async {
        SharedPreferences.setMockInitialValues({});
        await tester.binding.setSurfaceSize(Size(width, 1000));
        addTearDown(() => tester.binding.setSurfaceSize(null));
        final auth = AuthController();
        addTearDown(auth.dispose);
        await tester.pumpWidget(AuthScope(
            controller: auth,
            child: MaterialApp(
              theme: buildAppTheme(brightness),
              onGenerateRoute: (settings) => MaterialPageRoute(
                  settings: settings,
                  builder: (_) => Scaffold(
                      body: Text(
                          'content:${(settings.arguments as ResultScreenArgs).contentId}'))),
              home: HistoryScreen(repository: HistoryRepository()),
            )));
        await tester.pumpAndSettle();
        expect(find.text('ความยาวแนะนำ: 79 วินาที'), findsOneWidget);
        expect(find.textContaining('18/10/2026'), findsOneWidget);
        final points = ['Newest camera', 'Middle phone', 'Oldest camera']
            .map((title) => tester.getTopLeft(find.text(title)))
            .toList();
        for (var i = 1; i < points.length; i++) {
          expect(
              points[i].dy > points[i - 1].dy ||
                  (points[i].dy == points[i - 1].dy &&
                      points[i].dx > points[i - 1].dx),
              isTrue);
        }
        await tester.ensureVisible(find.text('Newest camera'));
        await tester.tap(find.text('Newest camera'));
        await tester.pumpAndSettle();
        expect(find.text('content:3'), findsOneWidget);
        expect(tester.takeException(), isNull);
      });
    }
  }

  test('history reads optional real timestamps, never creates a fallback date',
      () {
    expect(ContentHistoryItem.fromJson({}).createdAt, isNull);
    expect(ContentHistoryItem.fromJson({'created_at': 'invalid'}).createdAt,
        isNull);
    expect(
        ContentHistoryItem.fromJson({'created_at': '2026-10-18T12:00:00'})
            .createdAt,
        DateTime.utc(2026, 10, 18, 12));
    expect(
        ContentHistoryItem.fromJson({'created_at': '2026-10-18T19:00:00+07:00'})
            .createdAt,
        DateTime.utc(2026, 10, 18, 12));
  });
}
