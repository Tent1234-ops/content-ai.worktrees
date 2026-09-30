import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../models/app_user.dart';
import '../models/auth_session.dart';
import '../services/api_client.dart';

class AuthRepository {
  AuthRepository({ApiClient? client}) : _client = client ?? ApiClient();

  final ApiClient _client;

  Future<AuthSession> login(String email, String password) async {
    final response = await _client.post('/auth/login', {
      'email': email,
      'password': password,
    });
    final session =
        AuthSession.fromJson(Map<String, dynamic>.from(response as Map));
    await persistSession(session);
    return session;
  }

  Future<void> register({
    required String username,
    required String email,
    required String password,
  }) async {
    await _client.post('/auth/register', {
      'username': username,
      'email': email,
      'password': password,
      'role': 'user',
    });
  }

  Future<AuthSession?> restoreSession() async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString('access_token');
    final sessionKey = prefs.getString('trend_session_key');
    final userJson = prefs.getString('auth_user');
    if (token == null ||
        token.isEmpty ||
        sessionKey == null ||
        sessionKey.isEmpty ||
        userJson == null ||
        userJson.isEmpty) {
      return null;
    }
    try {
      final user = AppUser.fromJson(
          Map<String, dynamic>.from(jsonDecode(userJson) as Map));
      return AuthSession(
        accessToken: token,
        sessionKey: sessionKey,
        user: user,
      );
    } catch (_) {
      await clearSession();
      return null;
    }
  }

  Future<AppUser> fetchCurrentUser() async {
    final response = await _client.get('/auth/me');
    final user = AppUser.fromJson(Map<String, dynamic>.from(response as Map));
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('auth_user', jsonEncode(user.toJson()));
    await prefs.setString('user_role', user.role);
    await prefs.setString('username', user.username);
    return user;
  }

  Future<void> persistSession(AuthSession session) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('access_token', session.accessToken);
    await prefs.setString('trend_session_key', session.sessionKey);
    await prefs.setString('auth_user', jsonEncode(session.user.toJson()));
    await prefs.setString('user_role', session.user.role);
    await prefs.setString('username', session.user.username);
  }

  Future<void> clearSession() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('access_token');
    await prefs.remove('trend_session_key');
    await prefs.remove('auth_user');
    await prefs.remove('user_role');
    await prefs.remove('username');
  }

  Future<void> logout() async {
    try {
      await _client.post('/auth/logout', const <String, dynamic>{});
    } finally {
      await clearSession();
    }
  }
}
