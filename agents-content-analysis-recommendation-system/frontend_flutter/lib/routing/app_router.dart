import 'package:flutter/material.dart';

import '../screens/auth_gate.dart';
import '../screens/admin_dataset_review_screen.dart';
import '../screens/admin_datasets_screen.dart';
import '../screens/admin_analysis_settings_screen.dart';
import '../screens/admin_training_screen.dart';
import '../screens/admin_users_screen.dart';
import '../screens/admin_logs_screen.dart';
import '../screens/admin_transcript_import_screen.dart';
import '../screens/dashboard_screen.dart';
import '../screens/history_screen.dart';
import '../screens/login_screen.dart';
import '../screens/register_screen.dart';
import '../screens/result_screen.dart';
import '../screens/upload_screen.dart';
import '../state/auth_controller.dart';

class AppRouter {
  AppRouter(this.authController);

  final AuthController authController;

  static const Set<String> _publicRoutes = {
    '/',
    '/dashboard',
    '/login',
    '/register',
  };
  static const Set<String> _adminRoutes = {
    '/admin-users',
    '/admin-training',
    '/admin-analysis-settings',
    '/admin-dataset-review',
    '/admin-datasets',
    '/admin-logs',
    '/admin-transcript-import',
  };

  Route<dynamic> onGenerateRoute(RouteSettings settings) {
    final name = settings.name ?? '/';
    if (!authController.initialized) {
      return _page(
        AuthGate(
          destination: name == '/' ? '/dashboard' : name,
          arguments: settings.arguments,
        ),
        settings,
      );
    }
    if (!_publicRoutes.contains(name) && !authController.isAuthenticated) {
      return _page(
        LoginScreen(
          destination: LoginDestination(name, arguments: settings.arguments),
        ),
        settings.copyWith(name: '/login'),
      );
    }
    if (_adminRoutes.contains(name) && !authController.isAdmin) {
      return _page(
          const DashboardScreen(), settings.copyWith(name: '/dashboard'));
    }

    switch (name) {
      case '/':
        return _page(const AuthGate(), settings);
      case '/login':
        return _page(
          LoginScreen(
            destination: settings.arguments is LoginDestination
                ? settings.arguments as LoginDestination
                : const LoginDestination('/dashboard'),
          ),
          settings,
        );
      case '/register':
        return _page(
          RegisterScreen(
            destination: settings.arguments is LoginDestination
                ? settings.arguments as LoginDestination
                : const LoginDestination('/dashboard'),
          ),
          settings,
        );
      case '/dashboard':
        return _page(const DashboardScreen(), settings);
      case '/upload':
        return _page(const UploadScreen(), settings);
      case '/history':
        return _page(const HistoryScreen(), settings);
      case '/result':
        return _page(const ResultScreen(), settings);
      case '/admin-dataset-review':
        return _page(const AdminDatasetReviewScreen(), settings);
      case '/admin-datasets':
        return _page(const AdminDatasetsScreen(), settings);
      case '/admin-analysis-settings':
        return _page(const AdminAnalysisSettingsScreen(), settings);
      case '/admin-training':
        return _page(const AdminTrainingScreen(), settings);
      case '/admin-users':
        return _page(const AdminUsersScreen(), settings);
      case '/admin-logs':
        return _page(const AdminLogsScreen(), settings);
      case '/admin-transcript-import':
        return _page(const AdminTranscriptImportScreen(), settings);
      default:
        return _page(
            const DashboardScreen(), settings.copyWith(name: '/dashboard'));
    }
  }

  MaterialPageRoute<dynamic> _page(Widget child, RouteSettings settings) {
    return MaterialPageRoute<dynamic>(
        builder: (_) => child, settings: settings);
  }
}

extension on RouteSettings {
  RouteSettings copyWith({String? name, Object? arguments}) {
    return RouteSettings(
        name: name ?? this.name, arguments: arguments ?? this.arguments);
  }
}
