import 'package:content_ai_web/models/managed_user.dart';
import 'package:content_ai_web/repositories/admin_repository.dart';
import 'package:content_ai_web/screens/admin_users_screen.dart';
import 'package:content_ai_web/utils/system_log_presenter.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> account(int id, {bool self = false}) => {
      'user_id': id,
      'username': self ? 'admin' : 'creator',
      'email': self ? 'admin@example.test' : 'creator@example.test',
      'role': self ? 'admin' : 'user',
      'is_active': true,
      'is_self': self,
      'revision': 'a' * 64,
      'created_at': '2026-09-07T10:00:00',
      'stats': {'contents': 2, 'analyses': 2, 'follows': 1, 'sessions': 2}
    };

class UserRepository extends AdminRepository {
  Map<String, dynamic> target = account(2);
  Map<String, dynamic>? created, updated;
  bool deleted = false, failLoad = false, failSave = false;
  int revocations = 0, loads = 0, offset = 0;
  String query = '';
  @override
  Future<ManagedUsersPage> listUsers(
      {String query = '',
      String role = 'all',
      String state = 'all',
      int offset = 0}) async {
    this.query = query;
    this.offset = offset;
    loads++;
    if (failLoad) throw Exception('โหลดรายชื่อไม่สำเร็จ');
    return ManagedUsersPage.fromJson({
      'total': query.isEmpty ? 22 : 1,
      'summary': {'total': 22, 'active': 20, 'active_admins': 1},
      'items': [
        if (!deleted) target,
        if (query.isEmpty && offset == 0) account(1, self: true)
      ]
    });
  }

  @override
  Future<ManagedUser> userDetail(int id) async =>
      ManagedUser.fromJson(id == 1 ? account(1, self: true) : target);
  @override
  Future<void> createUser(Map<String, dynamic> fields) async {
    created = fields;
  }

  @override
  Future<void> updateUser(int id, Map<String, dynamic> fields) async {
    if (failSave) throw Exception('ข้อมูลเปลี่ยนไป กรุณาโหลดใหม่');
    updated = fields;
    target = {...target, ...fields};
  }

  @override
  Future<void> revokeUserSessions(ManagedUser user) async {
    revocations++;
  }

  @override
  Future<int> deleteUser(ManagedUser user, String confirmation) async {
    expect(confirmation, target['username']);
    deleted = true;
    return 0;
  }
}

void main() {
  Future<void> open(WidgetTester tester, UserRepository repository) async {
    await tester.binding.setSurfaceSize(const Size(1440, 1000));
    addTearDown(() async {
      await tester.pumpWidget(const SizedBox());
      await tester.binding.setSurfaceSize(null);
    });
    await tester.pumpWidget(
        MaterialApp(home: AdminUsersScreen(repository: repository)));
    await tester.pumpAndSettle();
  }

  test('deleted actors retain audit identity and events have Thai names', () {
    expect(systemLogActorLabel(null, '{"deleted_actor_user_id":3}'),
        'ผู้ใช้หมายเลข 3 (ลบบัญชีแล้ว)');
    expect(systemLogActorLabel(null, 'legacy'), 'ระบบอัตโนมัติ');
    expect(systemLogActionLabel('admin_user_delete'), contains('ลบบัญชี'));
  });
  testWidgets(
      'lists users with protected self and debounced search, pagination',
      (tester) async {
    final repository = UserRepository();
    await open(tester, repository);
    expect(find.text('admin (คุณ)'), findsOneWidget);
    expect(
        tester
            .widget<IconButton>(find.byWidgetPredicate((w) =>
                w is IconButton &&
                w.tooltip == 'บัญชีที่กำลังใช้งาน แก้จากหน้านี้ไม่ได้'))
            .onPressed,
        isNull);
    await tester.tap(find.byTooltip('หน้าถัดไป'));
    await tester.pumpAndSettle();
    expect(repository.offset, 20);
    await tester.enterText(find.byType(TextField).first, 'creator');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    expect(repository.offset, 0);
    expect(repository.query, 'creator');
  });
  testWidgets(
      'edit role and active status sends current revision and no password',
      (tester) async {
    final repository = UserRepository();
    await open(tester, repository);
    await tester.tap(find.byTooltip('แก้ไขบัญชี #2'));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(DropdownButtonFormField<String>).last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('ผู้ดูแลระบบ').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byType(SwitchListTile));
    await tester.pumpAndSettle();
    await tester.tap(find.text('ยืนยันบันทึก'));
    await tester.pumpAndSettle();
    expect(repository.updated?['role'], 'admin');
    expect(repository.updated?['is_active'], false);
    expect(repository.updated?['expected_revision'], 'a' * 64);
    expect(repository.updated?.containsKey('password'), false);
    expect(tester.takeException(), isNull);
  });
  testWidgets('create validates identity and password confirmation',
      (tester) async {
    final repository = UserRepository();
    await open(tester, repository);
    await tester.tap(find.text('เพิ่มผู้ใช้'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('ยืนยันบันทึก'));
    await tester.pumpAndSettle();
    expect(repository.created, isNull);
    final fields = find.byType(TextFormField);
    await tester.enterText(fields.at(0), 'new_user');
    await tester.enterText(fields.at(1), 'new@example.test');
    await tester.enterText(fields.at(2), 'strong-password');
    await tester.enterText(fields.at(3), 'different');
    await tester.tap(find.text('ยืนยันบันทึก'));
    await tester.pumpAndSettle();
    expect(find.text('รหัสผ่านไม่ตรงกัน'), findsOneWidget);
    await tester.enterText(fields.at(3), 'strong-password');
    await tester.tap(find.text('ยืนยันบันทึก'));
    await tester.pumpAndSettle();
    expect(repository.created?['username'], 'new_user');
    expect(repository.created?['role'], 'user');
  });
  testWidgets('delete requires exact typed name and cancel has no side effects',
      (tester) async {
    final repository = UserRepository();
    await open(tester, repository);
    Future<void> deleteDialog() async {
      await tester.tap(find.byTooltip('จัดการบัญชี #2'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('ลบบัญชี'));
      await tester.pumpAndSettle();
    }

    await deleteDialog();
    expect(find.textContaining('Dataset โมเดล'), findsOneWidget);
    expect(
        tester
            .widget<FilledButton>(
                find.widgetWithText(FilledButton, 'ยืนยันลบบัญชี'))
            .onPressed,
        isNull);
    await tester.tap(find.text('ยกเลิก'));
    await tester.pumpAndSettle();
    expect(repository.deleted, false);
    await deleteDialog();
    await tester.enterText(find.byType(TextField).last, 'wrong');
    await tester.pump();
    expect(
        tester
            .widget<FilledButton>(
                find.widgetWithText(FilledButton, 'ยืนยันลบบัญชี'))
            .onPressed,
        isNull);
    await tester.enterText(find.byType(TextField).last, 'creator');
    await tester.pump();
    await tester.tap(find.text('ยืนยันลบบัญชี'));
    await tester.pumpAndSettle();
    expect(repository.deleted, true);
    expect(find.text('creator'), findsNothing);
  });
  testWidgets('session revocation and details do not delete accounts',
      (tester) async {
    final repository = UserRepository();
    await open(tester, repository);
    await tester.tap(find.byTooltip('รายละเอียด #2'));
    await tester.pumpAndSettle();
    expect(find.text('ผลวิเคราะห์ที่บันทึก: 2'), findsOneWidget);
    await tester.tap(find.text('ปิด'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('จัดการบัญชี #2'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('ออกจากระบบทุกเซสชัน'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('ยืนยันออกจากระบบ'));
    await tester.pumpAndSettle();
    expect(repository.revocations, 1);
    expect(repository.deleted, false);
  });
  testWidgets('load and stale save errors remain visible, compact web fits',
      (tester) async {
    final repository = UserRepository()..failLoad = true;
    await open(tester, repository);
    expect(find.text('โหลดรายชื่อไม่สำเร็จ'), findsOneWidget);
    repository.failLoad = false;
    await tester.tap(find.byTooltip('โหลดผู้ใช้ล่าสุด'));
    await tester.pumpAndSettle();
    await tester.binding.setSurfaceSize(const Size(850, 900));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    await tester.ensureVisible(find.byTooltip('รายละเอียด #2'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('รายละเอียด #2'));
    await tester.pumpAndSettle();
    expect(find.text('ผลวิเคราะห์ที่บันทึก: 2'), findsOneWidget);
    await tester.tap(find.text('ปิด'));
    await tester.pumpAndSettle();
    await tester.binding.setSurfaceSize(const Size(1440, 1000));
    await tester.pumpAndSettle();
    repository.failSave = true;
    await tester.tap(find.byTooltip('แก้ไขบัญชี #2'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('ยืนยันบันทึก'));
    await tester.pumpAndSettle();
    expect(find.textContaining('ข้อมูลเปลี่ยนไป'), findsOneWidget);
    expect(repository.updated, isNull);
  });
}
