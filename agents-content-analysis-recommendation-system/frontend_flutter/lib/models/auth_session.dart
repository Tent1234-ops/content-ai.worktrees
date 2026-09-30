import 'app_user.dart';

class AuthSession {
  const AuthSession({
    required this.accessToken,
    required this.sessionKey,
    required this.user,
  });

  final String accessToken;
  final String sessionKey;
  final AppUser user;

  factory AuthSession.fromJson(Map<String, dynamic> json) {
    return AuthSession(
      accessToken: json['access_token']?.toString() ?? '',
      sessionKey: json['session_key']?.toString() ?? '',
      user: AppUser.fromJson(
          Map<String, dynamic>.from((json['user'] as Map?) ?? const {})),
    );
  }
}
