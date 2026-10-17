Map<String, dynamic> _map(dynamic value) =>
    value is Map ? Map<String, dynamic>.from(value) : const {};
Iterable<Map<String, dynamic>> _rows(dynamic value) =>
    value is List ? value.whereType<Map>().map(_map) : const [];
String _text(dynamic value) => value is String ? value.trim() : '';
int? _count(dynamic value) => value is num &&
        value.isFinite &&
        value >= 0 &&
        value == value.roundToDouble()
    ? value.toInt()
    : null;
DateTime? _date(dynamic value) => DateTime.tryParse(_text(value));

class ReferenceResponseClip {
  const ReferenceResponseClip({
    required this.datasetId,
    required this.videoId,
    required this.title,
    required this.channelId,
    required this.channelTitle,
    required this.quote,
    required this.publishedAt,
    required this.capturedAt,
    required this.views,
    required this.likes,
    required this.comments,
  });

  final int datasetId;
  final String videoId, title, channelId, channelTitle, quote;
  final DateTime? publishedAt, capturedAt;
  final int? views, likes, comments;
  Uri get sourceUrl => Uri.https('www.youtube.com', '/watch', {'v': videoId});
  bool get hasStatistics => views != null || likes != null || comments != null;
}

class ReferenceResponseTopic {
  const ReferenceResponseTopic({
    required this.id,
    required this.title,
    required this.clips,
  });
  final String id, title;
  final List<ReferenceResponseClip> clips;
  int get knownChannelCount => clips
      .map((clip) => clip.channelId)
      .where((id) => id.isNotEmpty)
      .toSet()
      .length;
}

/// A view of the saved evidence, never a query for current counters or a forecast.
List<ReferenceResponseTopic> referenceResponses(
  Map<String, dynamic> bundle, {
  required Map<String, String> recommendedTopics,
}) {
  if (_map(bundle['input'])['availability'] != 'available' ||
      !['phone', 'camera', 'laptop'].contains(bundle['taxonomy_leaf_key'])) {
    return const [];
  }
  final documents = <int, Map<String, dynamic>>{};
  final ambiguousIds = <int>{};
  for (final document in _rows(bundle['reference_documents'])) {
    final id = _count(document['dataset_id']);
    if (id == null || id == 0) continue;
    if (documents.containsKey(id)) ambiguousIds.add(id);
    documents[id] = document;
  }
  final cutoff = _date(bundle['generated_at']);
  final topics = <ReferenceResponseTopic>[];
  final seenTopics = <String>{};
  // An explicitly empty action-topic list is not permission to use legacy topics.
  final sourceTopics = bundle.containsKey('action_topics')
      ? bundle['action_topics']
      : bundle['topics'];
  for (final topic in _rows(sourceTopics)) {
    final id = _text(topic['topic_id']);
    if (!recommendedTopics.containsKey(id) ||
        !seenTopics.add(id) ||
        topic['source_type'] != 'transcript' ||
        _map(topic['user'])['status'] != 'not_detected') {
      continue;
    }
    final clips = <ReferenceResponseClip>[];
    final seenVideos = <String>{};
    for (final support in _rows(topic['references'])) {
      final datasetId = _count(support['dataset_id']);
      final document = documents[datasetId];
      if (document == null ||
          ambiguousIds.contains(datasetId) ||
          document['source_type'] != 'dataset_transcript' ||
          document['taxonomy_leaf_key'] != bundle['taxonomy_leaf_key'] ||
          ['validation', 'test'].contains(document['data_split'])) {
        continue;
      }
      final videoId = _text(document['video_id']);
      final recordId = _text(document['source_record_id']);
      if (!RegExp(r'^[A-Za-z0-9_-]{11}$').hasMatch(videoId) ||
          (recordId.isNotEmpty && recordId != videoId)) {
        continue;
      }
      final transcript = _text(document['transcript']);
      final quotes = _rows(support['occurrences'])
          .map((row) => _text(row['quote']))
          .where((quote) => quote.isNotEmpty && transcript.contains(quote));
      if (quotes.isEmpty || !seenVideos.add(videoId)) continue;
      final publishedAt = _date(document['published_at']);
      final observedAt = _date(document['statistics_captured_at']);
      final timestampVerified = cutoff != null &&
          observedAt != null &&
          !observedAt.isAfter(cutoff) &&
          (publishedAt == null || !observedAt.isBefore(publishedAt)) &&
          _text(document['statistics_source']).isNotEmpty;
      final stats = timestampVerified ? _map(document['statistics']) : const {};
      clips.add(ReferenceResponseClip(
        datasetId: datasetId!,
        videoId: videoId,
        title: _text(document['title']),
        channelId: _text(document['channel_id']),
        channelTitle: _text(document['channel_title']),
        quote: quotes.first,
        publishedAt: publishedAt,
        capturedAt: timestampVerified ? observedAt : null,
        views: _count(stats['views']),
        likes: _count(stats['likes']),
        comments: _count(stats['comments']),
      ));
    }
    topics.add(ReferenceResponseTopic(
      id: id,
      title: recommendedTopics[id]!,
      clips: List.unmodifiable(clips),
    ));
  }
  final order = recommendedTopics.keys.toList();
  topics.sort((left, right) =>
      order.indexOf(left.id).compareTo(order.indexOf(right.id)));
  return List.unmodifiable(topics);
}
