class CurrentTrendIdeas {
  const CurrentTrendIdeas(
      {this.status = 'not_evaluated', this.generatedAt, this.items = const []});

  final String status;
  final DateTime? generatedAt;
  final List<CurrentTrendIdea> items;

  List<CurrentTrendIdea> validAt(DateTime now) => items
      .where((item) =>
          item.expiresAt != null &&
          item.expiresAt!.isAfter(now) &&
          generatedAt != null &&
          !generatedAt!.isAfter(now))
      .toList();

  factory CurrentTrendIdeas.fromJson(Map<String, dynamic> json) =>
      CurrentTrendIdeas(
        status: json['status']?.toString() ?? 'not_evaluated',
        generatedAt: DateTime.tryParse(json['generated_at']?.toString() ?? ''),
        items: (json['items'] as List? ?? const [])
            .whereType<Map>()
            .map((row) =>
                CurrentTrendIdea.fromJson(Map<String, dynamic>.from(row)))
            .toList(),
      );
}

class CurrentTrendIdea {
  const CurrentTrendIdea(
      {required this.topic,
      required this.suggestion,
      required this.supportCount,
      required this.sources,
      required this.userEvidence,
      this.expiresAt});
  final String topic;
  final String suggestion;
  final int supportCount;
  final DateTime? expiresAt;
  final List<CurrentTrendSource> sources;
  final List<String> userEvidence;

  factory CurrentTrendIdea.fromJson(Map<String, dynamic> json) =>
      CurrentTrendIdea(
        topic: json['topic']?.toString() ?? '',
        suggestion: json['suggestion']?.toString() ?? '',
        supportCount: (json['support_count'] as num?)?.toInt() ?? 0,
        expiresAt: DateTime.tryParse(json['expires_at']?.toString() ?? ''),
        sources: (json['sources'] as List? ?? const [])
            .whereType<Map>()
            .map((row) =>
                CurrentTrendSource.fromJson(Map<String, dynamic>.from(row)))
            .toList(),
        userEvidence: (json['user_evidence'] as List? ?? const [])
            .whereType<Map>()
            .map((row) => row['text']?.toString() ?? '')
            .where((text) => text.isNotEmpty)
            .toSet()
            .toList(),
      );
}

class CurrentTrendSource {
  const CurrentTrendSource(
      {required this.platform,
      required this.title,
      required this.url,
      required this.thumbnailUrl,
      required this.field,
      required this.quote,
      required this.runId,
      required this.itemId,
      this.observedAt,
      this.publishedAt});
  final String platform, title, url, thumbnailUrl, field, quote;
  final int runId, itemId;
  final DateTime? observedAt, publishedAt;

  factory CurrentTrendSource.fromJson(Map<String, dynamic> json) =>
      CurrentTrendSource(
        platform: json['platform']?.toString() ?? '',
        title: json['title']?.toString() ?? '',
        url: json['url']?.toString() ?? '',
        thumbnailUrl: json['thumbnail_url']?.toString() ?? '',
        field: json['evidence_field']?.toString() ?? '',
        quote: json['context_text']?.toString() ??
            json['evidence_text']?.toString() ??
            '',
        runId: (json['snapshot_run_id'] as num?)?.toInt() ?? 0,
        itemId: (json['snapshot_item_id'] as num?)?.toInt() ?? 0,
        observedAt: DateTime.tryParse(json['observed_at']?.toString() ?? ''),
        publishedAt: DateTime.tryParse(json['published_at']?.toString() ?? ''),
      );
}
