import '../models/app_user.dart';
import '../repositories/auth_repository.dart';

class AuthService {
  AuthService({AuthRepository? repository})
      : _repository = repository ?? AuthRepository();

  final AuthRepository _repository;

  Future<void> login(String email, String password) async {
    await _repository.login(email, password);
  }

  Future<void> register({
    required String username,
    required String email,
    required String password,
  }) async {
    await _repository.register(
        username: username, email: email, password: password);
  }

  Future<bool> hasToken() async {
    final session = await _repository.restoreSession();
    return session != null && session.accessToken.isNotEmpty;
  }

  Future<String?> getStoredRole() async {
    final session = await _repository.restoreSession();
    return session?.user.role;
  }

  Future<Map<String, dynamic>> getCurrentUser() async {
    final AppUser user = await _repository.fetchCurrentUser();
    return user.toJson();
  }

  Future<void> logout() async {
    await _repository.logout();
  }
}
