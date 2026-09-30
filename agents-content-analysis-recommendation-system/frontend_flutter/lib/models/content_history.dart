class ContentHistoryItem {
  const ContentHistoryItem({
    required this.contentId,
    required this.title,
    required this.domain,
    required this.transcriptPreview,
    required this.recommendedKeywords,
    required this.recommendedDuration,
  });

  final int contentId;
  final String title;
  final String domain;
  final String transcriptPreview;
  final List<String> recommendedKeywords;
  final String recommendedDuration;

  factory ContentHistoryItem.fromJson(Map<String, dynamic> json) {
    return ContentHistoryItem(
      contentId: (json['content_id'] as num?)?.toInt() ?? 0,
      title: json['title']?.toString() ?? '-',
      domain: json['domain']?.toString() ?? '-',
      transcriptPreview: json['transcript_preview']?.toString() ?? '',
      recommendedKeywords:
          (json['recommended_keywords'] as List<dynamic>? ?? const [])
              .map((item) => item.toString())
              .toList(),
      recommendedDuration: json['recommended_duration']?.toString() ?? '-',
    );
  }
}
