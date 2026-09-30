class SystemLogItem {
  const SystemLogItem({
    required this.logId,
    required this.action,
    required this.status,
    required this.detail,
    this.timestamp,
    this.userId,
  });

  final int logId;
  final String action;
  final String status;
  final String detail;
  final DateTime? timestamp;
  final int? userId;

  factory SystemLogItem.fromJson(Map<String, dynamic> json) {
    return SystemLogItem(
      logId: (json['log_id'] as num?)?.toInt() ?? 0,
      action: json['action']?.toString() ?? '-',
      status: json['status']?.toString() ?? 'unknown',
      detail: json['detail']?.toString() ?? '-',
      timestamp: _parseUtcTimestamp(json['timestamp']),
      userId: (json['user_id'] as num?)?.toInt(),
    );
  }
}

DateTime? _parseUtcTimestamp(Object? value) {
  final raw = value?.toString().trim() ?? '';
  if (raw.isEmpty) return null;
  final parsed = DateTime.tryParse(raw);
  if (parsed == null || parsed.isUtc) return parsed;

  final hasExplicitOffset = RegExp(r'(Z|[+-]\d\d:\d\d)$').hasMatch(raw);
  if (hasExplicitOffset) return parsed.toUtc();
  return DateTime.utc(
    parsed.year,
    parsed.month,
    parsed.day,
    parsed.hour,
    parsed.minute,
    parsed.second,
    parsed.millisecond,
    parsed.microsecond,
  );
}
