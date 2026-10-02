import 'package:flutter/material.dart';

class AppShell extends StatelessWidget {
  const AppShell({
    super.key,
    required this.title,
    required this.child,
    this.actions = const [],
    this.currentRoute,
    this.isAdmin = false,
    this.onLogout,
  });

  final String title;
  final Widget child;
  final List<Widget> actions;
  final String? currentRoute;
  final bool isAdmin;
  final Future<void> Function()? onLogout;

  void _navigate(BuildContext context, String route) {
    if (currentRoute == route) {
      Navigator.pop(context);
      return;
    }
    Navigator.pop(context);
    Navigator.pushNamed(context, route);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(title), actions: actions),
      drawer: Drawer(
        child: SafeArea(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(8, 12, 8, 16),
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(12, 4, 12, 16),
                child: Row(
                  children: [
                    Icon(Icons.auto_awesome,
                        color: Theme.of(context).colorScheme.primary),
                    const SizedBox(width: 10),
                    Text('Content AI',
                        style: Theme.of(context).textTheme.titleLarge),
                  ],
                ),
              ),
              ListTile(
                leading: const Icon(Icons.dashboard_outlined),
                title: const Text('แดชบอร์ด'),
                selected: currentRoute == '/dashboard',
                onTap: () => _navigate(context, '/dashboard'),
              ),
              ListTile(
                leading: const Icon(Icons.upload_file_outlined),
                title: const Text('วิเคราะห์คลิปของฉัน'),
                selected: currentRoute == '/upload',
                onTap: () => _navigate(context, '/upload'),
              ),
              ListTile(
                leading: const Icon(Icons.history_outlined),
                title: const Text('ไอเดียและประวัติ'),
                selected: currentRoute == '/history',
                onTap: () => _navigate(context, '/history'),
              ),
              if (isAdmin) const Divider(),
              if (isAdmin)
                ListTile(
                  leading: const Icon(Icons.manage_accounts_outlined),
                  title: const Text('จัดการผู้ใช้'),
                  selected: currentRoute == '/admin-users',
                  onTap: () => _navigate(context, '/admin-users'),
                ),
              if (isAdmin)
                ListTile(
                  leading: const Icon(Icons.model_training),
                  title: const Text('เทรนโมเดล AI'),
                  selected: currentRoute == '/admin-training',
                  onTap: () => _navigate(context, '/admin-training'),
                ),
              if (isAdmin)
                ListTile(
                  leading: const Icon(Icons.tune),
                  title: const Text('ตั้งค่าการวิเคราะห์'),
                  selected: currentRoute == '/admin-analysis-settings',
                  onTap: () => _navigate(context, '/admin-analysis-settings'),
                ),
              if (isAdmin)
                ListTile(
                  leading: const Icon(Icons.text_snippet_outlined),
                  title: const Text('นำเข้า Transcript'),
                  selected: currentRoute == '/admin-transcript-import',
                  onTap: () => _navigate(context, '/admin-transcript-import'),
                ),
              if (isAdmin)
                ListTile(
                  leading: const Icon(Icons.fact_check_outlined),
                  title: const Text('ตรวจสอบ Dataset'),
                  selected: currentRoute == '/admin-dataset-review',
                  onTap: () => _navigate(context, '/admin-dataset-review'),
                ),
              if (isAdmin)
                ListTile(
                  leading: const Icon(Icons.storage_outlined),
                  title: const Text('จัดการ Dataset'),
                  selected: currentRoute == '/admin-datasets',
                  onTap: () => _navigate(context, '/admin-datasets'),
                ),
              if (isAdmin)
                ListTile(
                  leading: const Icon(Icons.receipt_long_outlined),
                  title: const Text('บันทึกการทำงาน'),
                  selected: currentRoute == '/admin-logs',
                  onTap: () => _navigate(context, '/admin-logs'),
                ),
              if (onLogout != null) const Divider(),
              if (onLogout != null)
                ListTile(
                  leading: const Icon(Icons.logout),
                  title: const Text('ออกจากระบบ'),
                  onTap: () async {
                    Navigator.pop(context);
                    await onLogout!.call();
                  },
                ),
            ],
          ),
        ),
      ),
      body: Align(
          alignment: Alignment.topCenter,
          child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 1600), child: child)),
    );
  }
}
