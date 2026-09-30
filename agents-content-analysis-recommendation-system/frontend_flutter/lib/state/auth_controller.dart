import 'package:flutter/foundation.dart';

import '../models/app_user.dart';
import '../repositories/auth_repository.dart';

class AuthController extends ChangeNotifier {
  AuthController({AuthRepository? repository})
      : _repository = repository ?? AuthRepository();

  final AuthRepository _repository;
  AppUser? _user;
  bool _initialized = false;
  bool _loading = false;

  AppUser? get user => _user;
  bool get initialized => _initialized;
  bool get loading => _loading;
  bool get isAuthenticated => _user != null;
  bool get isAdmin => _user?.isAdmin ?? false;
  String get role => _user?.role ?? 'user';

  Future<void> initialize() async {
    if (_initialized) return;
    _setLoading(true);
    try {
      final session = await _repository.restoreSession();
      _user = session?.user;
      if (session != null) {
        try {
          _user = await _repository.fetchCurrentUser();
        } catch (_) {
          await _repository.clearSession();
          _user = null;
        }
      }
    } finally {
      _initialized = true;
      _setLoading(false);
    }
  }

  Future<void> login(String email, String password) async {
    _setLoading(true);
    try {
      final session = await _repository.login(email, password);
      _user = session.user;
      notifyListeners();
    } finally {
      _setLoading(false);
    }
  }

  Future<void> register({
    required String username,
    required String email,
    required String password,
  }) async {
    _setLoading(true);
    try {
      await _repository.register(
          username: username, email: email, password: password);
    } finally {
      _setLoading(false);
    }
  }

  Future<void> logout() async {
    await _repository.logout();
    _user = null;
    notifyListeners();
  }

  void _setLoading(bool value) {
    if (_loading == value) return;
    _loading = value;
    notifyListeners();
  }
}
