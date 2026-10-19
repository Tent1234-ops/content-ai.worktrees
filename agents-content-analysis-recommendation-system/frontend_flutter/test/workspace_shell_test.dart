import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:content_ai_web/ui/app_theme.dart';
import 'package:content_ai_web/widgets/app_shell.dart';

void main() {
  for (final width in [390.0, 768.0, 1280.0, 1600.0]) {
    for (final brightness in Brightness.values) {
      testWidgets(
          'shell is responsive and keeps navigation at $width $brightness',
          (tester) async {
        await tester.binding.setSurfaceSize(Size(width, 1000));
        addTearDown(() => tester.binding.setSurfaceSize(null));
        await tester.pumpWidget(MaterialApp(
            theme: buildAppTheme(brightness),
            initialRoute: '/upload',
            onGenerateRoute: (settings) => MaterialPageRoute(
                settings: settings,
                builder: (_) => AppShell(
                    title: 'วิเคราะห์คลิปของฉัน',
                    isAdmin: true,
                    child: Text('route:${settings.name}')))));
        await tester.pumpAndSettle();
        final desktop = width >= 1180;
        if (!desktop) {
          await tester.tap(find.byTooltip('Open navigation menu'));
          await tester.pumpAndSettle();
        }
        final active = tester.widget<ListTile>(
            find.widgetWithText(ListTile, 'วิเคราะห์คลิปของฉัน'));
        expect(active.selected, isTrue);
        expect(find.text('ผู้ดูแลระบบ'), findsOneWidget);
        await tester.tap(find.widgetWithText(ListTile, 'วิเคราะห์คลิปของฉัน'));
        await tester.pumpAndSettle();
        expect(find.text('route:/upload'), findsOneWidget);
        if (!desktop) {
          await tester.tap(find.byTooltip('Open navigation menu'));
          await tester.pumpAndSettle();
        }
        await tester.tap(find.widgetWithText(ListTile, 'ไอเดียและประวัติ'));
        await tester.pumpAndSettle();
        expect(find.text('route:/history'), findsOneWidget);
        expect(tester.takeException(), isNull);
      });
    }
  }
  testWidgets('non-admin sidebar never exposes admin navigation',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1280, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(MaterialApp(
        theme: buildAppTheme(Brightness.light),
        home: const AppShell(title: 'Content AI', child: Text('content'))));
    expect(find.text('เทรนโมเดล AI'), findsNothing);
    expect(find.text('content'), findsOneWidget);
  });
  for (final width in [390.0, 1280.0]) {
    testWidgets('result highlights history but can navigate back at $width',
        (tester) async {
      await tester.binding.setSurfaceSize(Size(width, 1000));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(MaterialApp(
          theme: buildAppTheme(Brightness.light),
          initialRoute: '/result',
          onGenerateRoute: (settings) => MaterialPageRoute(
              settings: settings,
              builder: (_) => AppShell(
                  title: 'ผลวิเคราะห์คลิป',
                  currentRoute: settings.name,
                  child: Text('route:${settings.name}')))));
      await tester.pumpAndSettle();
      if (width < 1180) {
        await tester.tap(find.byTooltip('Open navigation menu'));
        await tester.pumpAndSettle();
      }
      final history = find.widgetWithText(ListTile, 'ไอเดียและประวัติ');
      expect(tester.widget<ListTile>(history).selected, isTrue);
      await tester.tap(history);
      await tester.pumpAndSettle();
      expect(find.text('route:/history'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  }
}
