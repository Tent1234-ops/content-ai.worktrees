import 'package:content_ai_web/models/common_models.dart';
import 'package:content_ai_web/models/content_history.dart';
import 'package:content_ai_web/repositories/content_repository.dart';
import 'package:content_ai_web/screens/history_screen.dart';
import 'package:content_ai_web/state/auth_controller.dart';
import 'package:content_ai_web/state/auth_scope.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

class HistoryRepository extends ContentRepository {
  @override
  Future<PaginatedResult<ContentHistoryItem>> listMyContents(
          {int limit = 20, int offset = 0}) async =>
      PaginatedResult(total: 3, items: [
        ContentHistoryItem.fromJson(
            {'content_id': 3, 'title': 'Newest camera', 'domain': 'camera'}),
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
    await tester.binding.setSurfaceSize(const Size(1000, 1000));
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
}
