import 'package:flutter/material.dart';
import '../state/theme_controller.dart';

class AppShell extends StatelessWidget {
  const AppShell(
      {super.key,
      required this.title,
      required this.child,
      this.actions = const [],
      this.currentRoute,
      this.isAdmin = false,
      this.onLogout});

  final String title;
  final Widget child;
  final List<Widget> actions;
  final String? currentRoute;
  final bool isAdmin;
  final Future<void> Function()? onLogout;

  String _activeRoute(BuildContext context) {
    final route = currentRoute ?? ModalRoute.of(context)?.settings.name ?? '';
    return route == '/result'
        ? '/history'
        : route == '/'
            ? '/dashboard'
            : route;
  }

  void _navigate(BuildContext context, String route, {required bool drawer}) {
    final current = currentRoute ?? ModalRoute.of(context)?.settings.name ?? '';
    final active = current == '/' ? '/dashboard' : current;
    if (drawer) Navigator.pop(context);
    if (active != route) Navigator.pushNamed(context, route);
  }

  Widget _navigation(BuildContext context, {required bool drawer}) {
    final theme = Theme.of(context);
    Widget item(String route, String label, IconData icon) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: ListTile(
            leading: Icon(icon, size: 21),
            title: Text(label),
            selected: _activeRoute(context) == route,
            onTap: () => _navigate(context, route, drawer: drawer),
            contentPadding: const EdgeInsets.symmetric(horizontal: 14),
          ),
        );
    return Material(
      color: theme.colorScheme.surface,
      child: SafeArea(
          child: Column(children: [
        Padding(
            padding: const EdgeInsets.fromLTRB(24, 24, 20, 24),
            child: Row(children: [
              Container(
                  width: 36,
                  height: 36,
                  decoration: BoxDecoration(
                      color: theme.colorScheme.primary,
                      borderRadius: BorderRadius.circular(8)),
                  child: Icon(Icons.graphic_eq,
                      color: theme.colorScheme.onPrimary)),
              const SizedBox(width: 12),
              Expanded(
                  child: Text('Content AI',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.titleLarge)),
            ])),
        Expanded(
            child: ListView(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                children: [
              Padding(
                  padding: const EdgeInsets.fromLTRB(14, 0, 14, 12),
                  child: Text('พื้นที่ทำงาน',
                      style: theme.textTheme.labelMedium?.copyWith(
                          color: theme.colorScheme.onSurfaceVariant))),
              item('/dashboard', 'แดชบอร์ด', Icons.dashboard_outlined),
              item('/upload', 'วิเคราะห์คลิปของฉัน', Icons.video_call_outlined),
              item('/history', 'ไอเดียและประวัติ', Icons.history_outlined),
              if (isAdmin) ...[
                const Divider(height: 32),
                Padding(
                    padding: const EdgeInsets.fromLTRB(14, 0, 14, 12),
                    child: Text('ผู้ดูแลระบบ',
                        style: theme.textTheme.labelMedium?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant))),
                item('/admin-users', 'จัดการผู้ใช้',
                    Icons.manage_accounts_outlined),
                item('/admin-training', 'เทรนโมเดล AI', Icons.model_training),
                item('/admin-analysis-settings', 'ตั้งค่าการวิเคราะห์',
                    Icons.tune),
                item('/admin-transcript-import', 'นำเข้า Transcript',
                    Icons.text_snippet_outlined),
                item('/admin-dataset-review', 'ตรวจสอบ Dataset',
                    Icons.fact_check_outlined),
                item('/admin-datasets', 'จัดการ Dataset',
                    Icons.storage_outlined),
                item('/admin-logs', 'บันทึกการทำงาน',
                    Icons.receipt_long_outlined),
              ],
            ])),
        const Divider(height: 1),
        Padding(
            padding: const EdgeInsets.all(12),
            child: Column(children: [
              ListTile(
                  leading: Icon(theme.brightness == Brightness.dark
                      ? Icons.light_mode_outlined
                      : Icons.dark_mode_outlined),
                  title: Text(theme.brightness == Brightness.dark
                      ? 'โหมดสว่าง'
                      : 'โหมดมืด'),
                  onTap: toggleThemeMode),
              if (onLogout != null)
                ListTile(
                    leading: const Icon(Icons.logout),
                    title: const Text('ออกจากระบบ'),
                    onTap: () async {
                      if (drawer) Navigator.pop(context);
                      await onLogout!();
                    }),
            ])),
      ])),
    );
  }

  @override
  Widget build(BuildContext context) =>
      LayoutBuilder(builder: (context, constraints) {
        final desktop = constraints.maxWidth >= 1180;
        final header = AppBar(
          automaticallyImplyLeading: !desktop,
          title: Text(title, maxLines: 1, overflow: TextOverflow.ellipsis),
          actions: [...actions, const SizedBox(width: 8)],
        );
        final content = Align(
            alignment: Alignment.topCenter,
            child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 1360),
                child: child));
        if (!desktop) {
          return Scaffold(
              appBar: header,
              drawer: Drawer(child: _navigation(context, drawer: true)),
              body: content);
        }
        return Scaffold(
            body: SafeArea(
                child: Row(children: [
          SizedBox(width: 248, child: _navigation(context, drawer: false)),
          VerticalDivider(
              width: 1,
              thickness: 1,
              color: Theme.of(context).colorScheme.outlineVariant),
          Expanded(child: Column(children: [header, Expanded(child: content)])),
        ])));
      });
}
