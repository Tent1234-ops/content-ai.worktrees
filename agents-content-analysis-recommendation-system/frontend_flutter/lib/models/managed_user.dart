class ManagedUser {
  ManagedUser.fromJson(Map<String, dynamic> json)
      : id = (json['user_id'] as num).toInt(),
        username = json['username'] as String,
        email = json['email'] as String,
        role = json['role'] as String,
        active = json['is_active'] == true,
        isSelf = json['is_self'] == true,
        revision = json['revision'] as String,
        createdAt = json['created_at']?.toString(),
        stats = Map<String, dynamic>.from(json['stats'] as Map? ?? {});
  final int id;
  final String username, email, role, revision;
  final bool active, isSelf;
  final String? createdAt;
  final Map<String, dynamic> stats;
  String get roleLabel => role == 'admin' ? 'ผู้ดูแลระบบ' : 'ผู้ใช้';
  int count(String name) => (stats[name] as num?)?.toInt() ?? 0;
}

class ManagedUsersPage {
  ManagedUsersPage.fromJson(Map<String, dynamic> json)
      : total = (json['total'] as num).toInt(),
        summary = Map<String, dynamic>.from(json['summary'] as Map),
        items = (json['items'] as List)
            .map((row) =>
                ManagedUser.fromJson(Map<String, dynamic>.from(row as Map)))
            .toList();
  final int total;
  final Map<String, dynamic> summary;
  final List<ManagedUser> items;
}

String accountDate(dynamic raw) {
  if (raw == null) return '-';
  final text = raw.toString();
  final date =
      DateTime.tryParse(text.endsWith('Z') ? text : '${text}Z')?.toLocal();
  if (date == null) return '-';
  return '${date.day}/${date.month}/${date.year} ${date.hour.toString().padLeft(2, '0')}:${date.minute.toString().padLeft(2, '0')}';
}
