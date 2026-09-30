class ActionableRecommendations {
  const ActionableRecommendations(
      {required this.status,
      required this.items,
      required this.methodVersion,
      required this.templateVersion,
      required this.catalogHash,
      required this.limitation});
  final String status, methodVersion, templateVersion, catalogHash, limitation;
  final List<ActionableAdvice> items;

  factory ActionableRecommendations.fromJson(Map<String, dynamic> json) =>
      ActionableRecommendations(
        status: json['status']?.toString() ?? 'unavailable',
        methodVersion: json['method_version']?.toString() ?? '',
        templateVersion: json['template_version']?.toString() ?? '',
        catalogHash: json['catalog_sha256']?.toString() ?? '',
        limitation: json['limitation']?.toString() ?? '',
        items: (json['items'] as List? ?? [])
            .whereType<Map>()
            .map((item) =>
                ActionableAdvice.fromJson(Map<String, dynamic>.from(item)))
            .toList(),
      );
}

class ActionableAdvice {
  const ActionableAdvice(
      {required this.id,
      required this.evidenceTopicId,
      required this.title,
      required this.finding,
      required this.proposal,
      required this.condition,
      required this.steps,
      required this.example,
      required this.reason,
      required this.relevanceReason,
      required this.foundTopics});
  final String id,
      evidenceTopicId,
      title,
      finding,
      proposal,
      condition,
      example,
      reason,
      relevanceReason;
  final List<String> steps;
  final List<Map<String, dynamic>> foundTopics;

  factory ActionableAdvice.fromJson(Map<String, dynamic> json) =>
      ActionableAdvice(
        id: json['id']?.toString() ?? '',
        evidenceTopicId: json['evidence_topic_id']?.toString() ?? '',
        title: json['title']?.toString() ?? '',
        finding: json['finding']?.toString() ?? '',
        proposal: json['proposal']?.toString() ?? '',
        condition: json['condition']?.toString() ?? '',
        example: json['example']?.toString() ?? '',
        reason: json['reason']?.toString() ?? '',
        relevanceReason: json['relevance_reason']?.toString() ?? '',
        steps: (json['steps'] as List? ?? [])
            .map((step) => step.toString())
            .toList(),
        foundTopics: (json['found_topics'] as List? ?? [])
            .whereType<Map>()
            .map((item) => Map<String, dynamic>.from(item))
            .toList(),
      );
}
