import 'package:flutter/material.dart';

import 'routing/app_router.dart';
import 'ui/app_theme.dart';
import 'state/auth_controller.dart';
import 'state/auth_scope.dart';
import 'state/theme_controller.dart';

void main() {
  runApp(const ContentAiApp());
}

class ContentAiApp extends StatefulWidget {
  const ContentAiApp({super.key});

  @override
  State<ContentAiApp> createState() => _ContentAiAppState();
}

class _ContentAiAppState extends State<ContentAiApp> {
  late final AuthController _authController;
  late final AppRouter _router;

  @override
  void initState() {
    super.initState();
    _authController = AuthController();
    _router = AppRouter(_authController);
    _authController.initialize();
  }

  @override
  void dispose() {
    _authController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AuthScope(
      controller: _authController,
      child: ValueListenableBuilder<ThemeMode>(
        valueListenable: themeModeNotifier,
        builder: (context, themeMode, child) {
          return MaterialApp(
            title: 'Content AI',
            debugShowCheckedModeBanner: false,
            theme: buildAppTheme(Brightness.light),
            darkTheme: buildAppTheme(Brightness.dark),
            themeMode: themeMode,
            onGenerateRoute: _router.onGenerateRoute,
          );
        },
      ),
    );
  }
}
