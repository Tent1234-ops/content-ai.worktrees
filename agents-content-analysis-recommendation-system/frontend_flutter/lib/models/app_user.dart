class AppUser {
  const AppUser({
    required this.userId,
    required this.username,
    required this.email,
    required this.role,
    required this.isActive,
  });

  final int userId;
  final String username;
  final String email;
  final String role;
  final bool isActive;

  bool get isAdmin => role == 'admin';

  factory AppUser.fromJson(Map<String, dynamic> json) {
    return AppUser(
      userId: (json['user_id'] as num?)?.toInt() ?? 0,
      username: json['username']?.toString() ?? '',
      email: json['email']?.toString() ?? '',
      role: json['role']?.toString() ?? 'user',
      isActive: json['is_active'] as bool? ?? true,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'user_id': userId,
      'username': username,
      'email': email,
      'role': role,
      'is_active': isActive,
    };
  }
}
