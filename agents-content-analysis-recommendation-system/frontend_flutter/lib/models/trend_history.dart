class TrendHistory {
  TrendHistory.fromJson(Map<String, dynamic> json)
      : region = json['region'] as String? ?? 'TH',
        selectedKey = json['selected_key'] as String?,
        scope = json['ranking_scope'] as String? ?? 'global',
        items = (json['items'] as List? ?? [])
            .map((e) => HistoryItem.fromJson(Map<String, dynamic>.from(e)))
            .toList(),
        points = (json['points'] as List? ?? [])
            .map((e) => HistoryPoint.fromJson(Map<String, dynamic>.from(e)))
            .toList(),
        stale = (json['coverage'] as Map?)?['is_stale'] == true,
        latestUnavailable =
            (json['coverage'] as Map?)?['latest_unavailable'] == true,
        requestedFrom =
            DateTime.tryParse(json['requested_from']?.toString() ?? '')
                ?.toLocal(),
        requestedTo = DateTime.tryParse(json['requested_to']?.toString() ?? '')
            ?.toLocal(),
        hoursObserved =
            ((json['coverage'] as Map?)?['hours_observed'] as num?)?.toInt() ??
                0,
        hoursRequested =
            ((json['coverage'] as Map?)?['hours_requested'] as num?)?.toInt() ??
                0,
        hours = (json['hours'] as List? ?? [])
            .map((e) => HistoryHour.fromJson(Map<String, dynamic>.from(e)))
            .toList(),
        failedAttempts =
            ((json['coverage'] as Map?)?['failed_attempts'] as num?)?.toInt() ??
                0,
        unobservedHours =
            ((json['coverage'] as Map?)?['unobserved_hours'] as num?)
                    ?.toInt() ??
                0,
        gaps = ((json['coverage'] as Map?)?['gap_count'] as num?)?.toInt() ?? 0;

  final String scope;
  final String region;
  final String? selectedKey;
  final List<HistoryItem> items;
  final List<HistoryPoint> points;
  final bool stale;
  final bool latestUnavailable;
  final DateTime? requestedFrom, requestedTo;
  final int hoursObserved, hoursRequested;
  final List<HistoryHour> hours;
  final int gaps;
  final int failedAttempts;
  final int unobservedHours;
}

class HistoryItem {
  HistoryItem.fromJson(Map<String, dynamic> json)
      : key = json['key'] as String,
        title = json['title'] as String,
        latestRank = (json['latest_rank'] as num?)?.toInt(),
        movement = Map<String, dynamic>.from(json['movement'] as Map? ?? {});
  final String key;
  final String title;
  final int? latestRank;
  final Map<String, dynamic> movement;
}

class HistoryPoint {
  HistoryPoint.fromJson(Map<String, dynamic> json)
      : at = DateTime.parse(json['observed_at'] as String).toLocal(),
        runId = (json['run_id'] as num).toInt(),
        breakBefore = json['break_before'] == true,
        total = (json['total'] as num).toInt(),
        ranks = Map<String, dynamic>.from(json['ranks'] as Map)
            .map((key, value) => MapEntry(key, (value as num).toInt())),
        categories =
            Map<String, dynamic>.from(json['category_counts'] as Map? ?? {})
                .map((key, value) => MapEntry(key, (value as num).toInt())),
        views = Map<String, dynamic>.from(json['views'] as Map? ?? {})
            .map((key, value) => MapEntry(key, (value as num).toInt())),
        itemIds = Map<String, dynamic>.from(json['item_ids'] as Map? ?? {}),
        viewIntervals =
            Map<String, dynamic>.from(json['view_intervals'] as Map? ?? {}).map(
                (key, value) => MapEntry(key,
                    ViewInterval.fromJson(Map<String, dynamic>.from(value))));

  final DateTime at;
  final int runId;
  final bool breakBefore;
  final int total;
  final Map<String, int> ranks;
  final Map<String, int> categories;
  final Map<String, int> views;
  final Map<String, dynamic> itemIds;
  final Map<String, ViewInterval> viewIntervals;
  double? share(String category) =>
      total == 0 ? null : 100 * (categories[category] ?? 0) / total;
}

class ViewInterval {
  ViewInterval.fromJson(Map<String, dynamic> json)
      : status = json['status']?.toString() ?? 'missing_views',
        delta = (json['delta'] as num?)?.toInt(),
        perHour = (json['per_hour'] as num?)?.toDouble(),
        seconds = (json['elapsed_seconds'] as num?)?.toDouble(),
        from = DateTime.tryParse(json['from_at']?.toString() ?? '')?.toLocal(),
        fromRunId = (json['from_run_id'] as num?)?.toInt(),
        fromItemId = (json['from_item_id'] as num?)?.toInt(),
        fromViews = (json['from_views'] as num?)?.toInt();
  final String status;
  final int? delta, fromRunId, fromItemId, fromViews;
  final double? perHour, seconds;
  final DateTime? from;
  bool get measured =>
      status == 'measured' &&
      delta != null &&
      delta! >= 0 &&
      perHour != null &&
      perHour!.isFinite &&
      perHour! >= 0 &&
      seconds != null &&
      seconds! > 0 &&
      from != null;
}

class HistoryHour {
  HistoryHour.fromJson(Map<String, dynamic> json)
      : at = DateTime.parse(json['hour']).toLocal(),
        status = json['status']?.toString() ?? 'no_observation',
        observed = json['observed'] == true,
        failures = (json['failed_attempts'] as num?)?.toInt() ?? 0;
  final DateTime at;
  final String status;
  final bool observed;
  final int failures;
}
