import 'dart:async';
import 'package:flutter/material.dart';
import '../widgets/usage_statistics_panel.dart';

import '../models/managed_user.dart';
import '../repositories/admin_repository.dart';
import '../widgets/app_shell.dart';
import '../widgets/state_widgets.dart';

class AdminUsersScreen extends StatefulWidget {
  const AdminUsersScreen({super.key, this.repository});
  final AdminRepository? repository;
  @override
  State<AdminUsersScreen> createState() => _AdminUsersScreenState();
}

class _AdminUsersScreenState extends State<AdminUsersScreen> {
  late final AdminRepository _repository;
  final _search = TextEditingController();
  Timer? _debounce;
  ManagedUsersPage? _page;
  String _role = 'all', _state = 'all';
  String? _error;
  int _offset = 0, _request = 0;
  bool _loading = true, _busy = false;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? AdminRepository();
    _load();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _search.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final request = ++_request;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await _repository.listUsers(
          query: _search.text.trim(),
          role: _role,
          state: _state,
          offset: _offset);
      if (!mounted || request != _request) return;
      if (_offset > 0 && data.items.isEmpty) {
        _offset = data.total == 0 ? 0 : ((data.total - 1) ~/ 20) * 20;
        await _load();
        return;
      }
      setState(() => _page = data);
    } catch (e) {
      if (mounted && request == _request) setState(() => _error = e.toString());
    } finally {
      if (mounted && request == _request) setState(() => _loading = false);
    }
  }

  void _filter() {
    _offset = 0;
    _debounce?.cancel();
    _load();
  }

  Future<void> _edit([ManagedUser? user]) async {
    final changed = await showDialog<bool>(
        context: context,
        builder: (_) => _UserEditor(repository: _repository, user: user));
    if (!mounted) return;
    if (changed == true) {
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('บันทึกบัญชีผู้ใช้แล้ว')));
    }
    await _load();
  }

  Future<void> _action(ManagedUser user, String action) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final latest = await _repository.userDetail(user.id);
      if (!mounted) return;
      if (action == 'detail') {
        await showDialog<void>(
            context: context,
            builder: (context) => AlertDialog(
                  title: Text('บัญชี ${latest.username}'),
                  content: SizedBox(
                      width: 480,
                      child: SingleChildScrollView(
                          child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisSize: MainAxisSize.min,
                              children: [
                            SelectableText(latest.email),
                            Text(
                                '${latest.roleLabel} · ${latest.active ? 'เปิดใช้งาน' : 'ระงับบัญชี'}'),
                            const Divider(height: 32),
                            Text(
                                'สมัครเมื่อ: ${accountDate(latest.createdAt)}'),
                            Text(
                                'เข้าสู่ระบบล่าสุด: ${accountDate(latest.stats['last_login_at'])}'),
                            Text(
                                'กิจกรรมเซสชันล่าสุด: ${accountDate(latest.stats['last_seen_at'])}'),
                            const SizedBox(height: 16),
                            Text('คลิปที่บันทึก: ${latest.count('contents')}'),
                            Text(
                                'ผลวิเคราะห์ที่บันทึก: ${latest.count('analyses')}'),
                            Text('หัวข้อที่ติดตาม: ${latest.count('follows')}'),
                            Text(
                                'เซสชันที่ยังไม่สิ้นสุด: ${latest.count('sessions')}'),
                          ]))),
                  actions: [
                    TextButton(
                        onPressed: () => Navigator.pop(context),
                        child: const Text('ปิด'))
                  ],
                ));
        return;
      }
      final confirmed = await showDialog<bool>(
          context: context,
          builder: (_) =>
              _AccountConfirmation(user: latest, deleting: action == 'delete'));
      if (confirmed != true || !mounted) return;
      String message;
      if (action == 'delete') {
        final remaining = await _repository.deleteUser(latest, latest.username);
        message = remaining == 0
            ? 'ลบบัญชีและข้อมูลส่วนตัวที่บันทึกแล้ว'
            : 'ลบบัญชีแล้ว แต่มีไฟล์ที่ลบไม่สำเร็จ $remaining ไฟล์ ตรวจสอบ System Logs';
      } else {
        await _repository.revokeUserSessions(latest);
        message = 'ยุติเซสชันแล้ว บัญชีนี้ต้องเข้าสู่ระบบใหม่';
      }
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(message)));
      await _load();
    } catch (e) {
      await _load();
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final data = _page;
    final compact = MediaQuery.sizeOf(context).width < 1000;
    return AppShell(
      title: 'จัดการผู้ใช้',
      currentRoute: '/admin-users',
      isAdmin: true,
      actions: [
        IconButton(
            tooltip: 'สถิติการวิเคราะห์ทั้งหมด',
            icon: const Icon(Icons.bar_chart),
            onPressed: () => showDialog<void>(
                  context: context,
                  builder: (context) => Dialog(
                      child: SizedBox(
                          width: 880,
                          child: SingleChildScrollView(
                              child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Align(
                                  alignment: Alignment.centerRight,
                                  child: IconButton(
                                      tooltip: 'ปิดสถิติ',
                                      onPressed: () => Navigator.pop(context),
                                      icon: const Icon(Icons.close))),
                              const UsageStatisticsPanel(admin: true),
                            ],
                          )))),
                )),
        IconButton(
            tooltip: 'โหลดผู้ใช้ล่าสุด',
            onPressed: _loading || _busy ? null : _load,
            icon: const Icon(Icons.refresh))
      ],
      child: Column(children: [
        Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Wrap(
                      alignment: WrapAlignment.spaceBetween,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      runSpacing: 12,
                      spacing: 16,
                      children: [
                        if (data != null)
                          Text(
                              'ทั้งหมด ${data.summary['total']} บัญชี · เปิดใช้งาน ${data.summary['active']} · ผู้ดูแลที่ใช้งาน ${data.summary['active_admins']}',
                              style: Theme.of(context).textTheme.titleMedium),
                        FilledButton.icon(
                            onPressed: _busy || _loading ? null : () => _edit(),
                            icon: const Icon(Icons.person_add_alt_1),
                            label: const Text('เพิ่มผู้ใช้')),
                      ]),
                  const SizedBox(height: 20),
                  Wrap(spacing: 16, runSpacing: 12, children: [
                    SizedBox(
                        width: 340,
                        child: TextField(
                            controller: _search,
                            decoration: const InputDecoration(
                                labelText: 'ชื่อผู้ใช้หรืออีเมล',
                                prefixIcon: Icon(Icons.search)),
                            onChanged: (_) {
                              _debounce?.cancel();
                              _debounce = Timer(
                                  const Duration(milliseconds: 350), _filter);
                            })),
                    SizedBox(
                        width: 195,
                        child: DropdownButtonFormField<String>(
                            isExpanded: true,
                            initialValue: _role,
                            decoration:
                                const InputDecoration(labelText: 'สิทธิ์'),
                            items: const [
                              DropdownMenuItem(
                                  value: 'all', child: Text('ทุกสิทธิ์')),
                              DropdownMenuItem(
                                  value: 'user', child: Text('ผู้ใช้')),
                              DropdownMenuItem(
                                  value: 'admin', child: Text('ผู้ดูแลระบบ')),
                            ],
                            onChanged: (v) {
                              if (v != null) {
                                _role = v;
                                _filter();
                              }
                            })),
                    SizedBox(
                        width: 195,
                        child: DropdownButtonFormField<String>(
                            isExpanded: true,
                            initialValue: _state,
                            decoration:
                                const InputDecoration(labelText: 'สถานะ'),
                            items: const [
                              DropdownMenuItem(
                                  value: 'all', child: Text('ทุกสถานะ')),
                              DropdownMenuItem(
                                  value: 'active', child: Text('เปิดใช้งาน')),
                              DropdownMenuItem(
                                  value: 'inactive', child: Text('ระงับบัญชี')),
                            ],
                            onChanged: (v) {
                              if (v != null) {
                                _state = v;
                                _filter();
                              }
                            })),
                  ]),
                  if (_error != null)
                    Padding(
                        padding: const EdgeInsets.only(top: 12),
                        child: Text(_error!,
                            style: TextStyle(
                                color: Theme.of(context).colorScheme.error))),
                ])),
        SizedBox(
            height: 3,
            child: _loading ? const LinearProgressIndicator() : null),
        Expanded(
            child: data == null
                ? (_loading
                    ? const SizedBox()
                    : ErrorStateView(
                        message: 'โหลดรายชื่อไม่สำเร็จ', onRetry: _load))
                : data.items.isEmpty
                    ? const Center(child: Text('ไม่พบผู้ใช้ที่ตรงกับตัวกรอง'))
                    : SingleChildScrollView(
                        padding: const EdgeInsets.symmetric(horizontal: 24),
                        child: Align(
                            alignment: Alignment.topLeft,
                            child: SingleChildScrollView(
                                scrollDirection: Axis.horizontal,
                                child: DataTable(
                                  columnSpacing: 24,
                                  dataRowMinHeight: 72,
                                  dataRowMaxHeight: 82,
                                  columns: [
                                    const DataColumn(label: Text('บัญชี')),
                                    const DataColumn(label: Text('สิทธิ์')),
                                    const DataColumn(label: Text('สถานะ')),
                                    const DataColumn(
                                        label: Text('ผลวิเคราะห์')),
                                    if (!compact)
                                      const DataColumn(
                                          label: Text('เข้าสู่ระบบล่าสุด')),
                                    const DataColumn(label: Text('จัดการ'))
                                  ],
                                  rows: data.items
                                      .map((user) => DataRow(cells: [
                                            DataCell(SizedBox(
                                                width: compact ? 260 : 320,
                                                child: Column(
                                                    mainAxisAlignment:
                                                        MainAxisAlignment
                                                            .center,
                                                    crossAxisAlignment:
                                                        CrossAxisAlignment
                                                            .start,
                                                    children: [
                                                      Text(
                                                          '${user.username}${user.isSelf ? ' (คุณ)' : ''}',
                                                          maxLines: 1,
                                                          overflow: TextOverflow
                                                              .ellipsis),
                                                      Text(user.email,
                                                          maxLines: 1,
                                                          overflow: TextOverflow
                                                              .ellipsis,
                                                          style:
                                                              Theme.of(context)
                                                                  .textTheme
                                                                  .bodySmall),
                                                    ]))),
                                            DataCell(Text(user.roleLabel)),
                                            DataCell(Row(
                                                mainAxisSize: MainAxisSize.min,
                                                children: [
                                                  Icon(
                                                      user.active
                                                          ? Icons
                                                              .check_circle_outline
                                                          : Icons.block,
                                                      size: 18,
                                                      color: user.active
                                                          ? Colors.teal
                                                          : Colors.redAccent),
                                                  const SizedBox(width: 6),
                                                  Text(user.active
                                                      ? 'เปิดใช้งาน'
                                                      : 'ระงับ')
                                                ])),
                                            DataCell(Text(
                                                '${user.count('analyses')}')),
                                            if (!compact)
                                              DataCell(Text(accountDate(user
                                                  .stats['last_login_at']))),
                                            DataCell(Row(
                                                mainAxisSize: MainAxisSize.min,
                                                children: [
                                                  IconButton(
                                                      tooltip:
                                                          'รายละเอียด #${user.id}',
                                                      onPressed: _busy ||
                                                              _loading
                                                          ? null
                                                          : () => _action(
                                                              user, 'detail'),
                                                      icon: const Icon(Icons
                                                          .person_search_outlined)),
                                                  IconButton(
                                                      tooltip: user.isSelf
                                                          ? 'บัญชีที่กำลังใช้งาน แก้จากหน้านี้ไม่ได้'
                                                          : 'แก้ไขบัญชี #${user.id}',
                                                      onPressed: _busy ||
                                                              _loading ||
                                                              user.isSelf
                                                          ? null
                                                          : () => _edit(user),
                                                      icon: const Icon(
                                                          Icons.edit_outlined)),
                                                  PopupMenuButton<String>(
                                                      tooltip:
                                                          'จัดการบัญชี #${user.id}',
                                                      enabled: !_busy &&
                                                          !_loading &&
                                                          !user.isSelf,
                                                      onSelected: (action) =>
                                                          _action(user, action),
                                                      itemBuilder:
                                                          (_) => const [
                                                                PopupMenuItem(
                                                                    value:
                                                                        'revoke',
                                                                    child: ListTile(
                                                                        leading:
                                                                            Icon(Icons
                                                                                .logout),
                                                                        title: Text(
                                                                            'ออกจากระบบทุกเซสชัน'),
                                                                        contentPadding:
                                                                            EdgeInsets.zero)),
                                                                PopupMenuItem(
                                                                    value:
                                                                        'delete',
                                                                    child: ListTile(
                                                                        leading: Icon(Icons.delete_outline,
                                                                            color: Colors
                                                                                .redAccent),
                                                                        title: Text(
                                                                            'ลบบัญชี'),
                                                                        contentPadding:
                                                                            EdgeInsets.zero)),
                                                              ]),
                                                ])),
                                          ]))
                                      .toList(),
                                ))))),
        if (data != null)
          Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
              child: Row(children: [
                Text(
                    'แสดง ${data.total == 0 ? 0 : _offset + 1}–${(_offset + data.items.length)} จาก ${data.total} บัญชี'),
                const Spacer(),
                IconButton(
                    tooltip: 'หน้าก่อนหน้า',
                    onPressed: _loading || _offset == 0
                        ? null
                        : () {
                            _offset -= 20;
                            _load();
                          },
                    icon: const Icon(Icons.chevron_left)),
                IconButton(
                    tooltip: 'หน้าถัดไป',
                    onPressed: _loading || _offset + 20 >= data.total
                        ? null
                        : () {
                            _offset += 20;
                            _load();
                          },
                    icon: const Icon(Icons.chevron_right)),
              ])),
      ]),
    );
  }
}

class _UserEditor extends StatefulWidget {
  const _UserEditor({required this.repository, this.user});
  final AdminRepository repository;
  final ManagedUser? user;
  @override
  State<_UserEditor> createState() => _UserEditorState();
}

class _UserEditorState extends State<_UserEditor> {
  final _form = GlobalKey<FormState>();
  late final TextEditingController _name, _email;
  final _password = TextEditingController(), _confirm = TextEditingController();
  late String _role;
  late bool _active;
  bool _saving = false, _obscure = true;
  String? _error;
  @override
  void initState() {
    super.initState();
    _name = TextEditingController(text: widget.user?.username);
    _email = TextEditingController(text: widget.user?.email);
    _role = widget.user?.role ?? 'user';
    _active = widget.user?.active ?? true;
  }

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    _password.dispose();
    _confirm.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_saving || !_form.currentState!.validate()) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final fields = <String, dynamic>{
        'username': _name.text.trim(),
        'email': _email.text.trim(),
        'role': _role
      };
      if (widget.user == null) {
        await widget.repository
            .createUser({...fields, 'password': _password.text});
      } else {
        await widget.repository.updateUser(widget.user!.id, {
          ...fields,
          'is_active': _active,
          'expected_revision': widget.user!.revision
        });
      }
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) => PopScope(
      canPop: !_saving,
      child: AlertDialog(
        title: Text(widget.user == null
            ? 'เพิ่มผู้ใช้'
            : 'แก้ไขบัญชี #${widget.user!.id}'),
        content: SizedBox(
            width: 480,
            child: SingleChildScrollView(
                child: Form(
                    key: _form,
                    child: Column(mainAxisSize: MainAxisSize.min, children: [
                      TextFormField(
                          controller: _name,
                          enabled: !_saving,
                          maxLength: 100,
                          decoration:
                              const InputDecoration(labelText: 'ชื่อผู้ใช้'),
                          validator: (v) => (v?.trim().length ?? 0) < 3
                              ? 'ชื่อผู้ใช้อย่างน้อย 3 ตัวอักษร'
                              : null),
                      const SizedBox(height: 12),
                      TextFormField(
                          controller: _email,
                          enabled: !_saving,
                          maxLength: 255,
                          keyboardType: TextInputType.emailAddress,
                          decoration: const InputDecoration(labelText: 'อีเมล'),
                          validator: (v) =>
                              !RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
                                      .hasMatch(v?.trim() ?? '')
                                  ? 'กรอกอีเมลให้ถูกต้อง'
                                  : null),
                      const SizedBox(height: 12),
                      DropdownButtonFormField<String>(
                          isExpanded: true,
                          initialValue: _role,
                          decoration:
                              const InputDecoration(labelText: 'สิทธิ์บัญชี'),
                          items: const [
                            DropdownMenuItem(
                                value: 'user', child: Text('ผู้ใช้')),
                            DropdownMenuItem(
                                value: 'admin', child: Text('ผู้ดูแลระบบ'))
                          ],
                          onChanged: _saving
                              ? null
                              : (v) => setState(() => _role = v!)),
                      if (widget.user != null) ...[
                        const SizedBox(height: 12),
                        SwitchListTile(
                            contentPadding: EdgeInsets.zero,
                            title: const Text('เปิดใช้งานบัญชี'),
                            value: _active,
                            onChanged: _saving
                                ? null
                                : (v) => setState(() => _active = v)),
                        const Text(
                            'การเปลี่ยนสิทธิ์ สถานะ หรืออีเมล จะยุติเซสชันเดิมของบัญชีนี้'),
                      ] else ...[
                        const SizedBox(height: 16),
                        TextFormField(
                            controller: _password,
                            enabled: !_saving,
                            obscureText: _obscure,
                            decoration: InputDecoration(
                                labelText: 'รหัสผ่าน',
                                suffixIcon: IconButton(
                                    tooltip: _obscure
                                        ? 'แสดงรหัสผ่าน'
                                        : 'ซ่อนรหัสผ่าน',
                                    onPressed: () =>
                                        setState(() => _obscure = !_obscure),
                                    icon: Icon(_obscure
                                        ? Icons.visibility
                                        : Icons.visibility_off))),
                            validator: (v) =>
                                (v?.length ?? 0) < 8 || (v?.length ?? 0) > 128
                                    ? 'รหัสผ่าน 8–128 ตัวอักษร'
                                    : null),
                        const SizedBox(height: 16),
                        TextFormField(
                            controller: _confirm,
                            enabled: !_saving,
                            obscureText: true,
                            decoration: const InputDecoration(
                                labelText: 'ยืนยันรหัสผ่าน'),
                            validator: (v) => v != _password.text
                                ? 'รหัสผ่านไม่ตรงกัน'
                                : null),
                      ],
                      if (_error != null)
                        Padding(
                            padding: const EdgeInsets.only(top: 16),
                            child: Text(_error!,
                                style: TextStyle(
                                    color:
                                        Theme.of(context).colorScheme.error))),
                    ])))),
        actions: [
          TextButton(
              onPressed: _saving ? null : () => Navigator.pop(context),
              child: const Text('ยกเลิก')),
          FilledButton.icon(
              onPressed: _saving ? null : _save,
              icon: const Icon(Icons.save_outlined),
              label: Text(_saving ? 'กำลังบันทึก' : 'ยืนยันบันทึก'))
        ],
      ));
}

class _AccountConfirmation extends StatefulWidget {
  const _AccountConfirmation({required this.user, required this.deleting});
  final ManagedUser user;
  final bool deleting;
  @override
  State<_AccountConfirmation> createState() => _AccountConfirmationState();
}

class _AccountConfirmationState extends State<_AccountConfirmation> {
  final _confirmation = TextEditingController();
  @override
  void dispose() {
    _confirmation.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(widget.deleting
            ? 'ลบบัญชี ${widget.user.username}?'
            : 'ออกจากระบบทุกเซสชัน?'),
        content: SizedBox(
            width: 480,
            child: SingleChildScrollView(
                child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                  if (widget.deleting) ...[
                    Text(
                        'ลบบัญชี คลิปที่บันทึก ${widget.user.count('contents')} รายการ ผลวิเคราะห์ ${widget.user.count('analyses')} รายการ และรายการติดตามของบัญชีนี้อย่างถาวร'),
                    const SizedBox(height: 12),
                    const Text(
                        'Dataset โมเดล ประวัติเทรน และ Log ของระบบจะยังคงอยู่'),
                    const SizedBox(height: 20),
                    TextField(
                        controller: _confirmation,
                        onChanged: (_) => setState(() {}),
                        decoration: InputDecoration(
                            labelText: 'พิมพ์ชื่อผู้ใช้เพื่อยืนยัน',
                            helperText: widget.user.username)),
                  ] else
                    Text(
                        '${widget.user.username} จะต้องเข้าสู่ระบบใหม่ บัญชีและผลวิเคราะห์ยังคงอยู่'),
                ]))),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('ยกเลิก')),
          FilledButton.icon(
            style: widget.deleting
                ? FilledButton.styleFrom(
                    backgroundColor: Theme.of(context).colorScheme.error,
                    foregroundColor: Theme.of(context).colorScheme.onError)
                : null,
            onPressed:
                widget.deleting && _confirmation.text != widget.user.username
                    ? null
                    : () => Navigator.pop(context, true),
            icon: Icon(widget.deleting ? Icons.delete_outline : Icons.logout),
            label: Text(widget.deleting ? 'ยืนยันลบบัญชี' : 'ยืนยันออกจากระบบ'),
          )
        ],
      );
}
