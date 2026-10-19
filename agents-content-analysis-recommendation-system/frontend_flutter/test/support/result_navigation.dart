import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Future<void> selectResultTab(WidgetTester tester, String tab) async {
  final target = find.byKey(ValueKey('result-tab-$tab'));
  await tester.ensureVisible(target);
  await tester.pumpAndSettle();
  await tester.tap(target);
  await tester.pumpAndSettle();
}
