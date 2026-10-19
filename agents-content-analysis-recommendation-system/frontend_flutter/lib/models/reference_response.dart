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
    this.groups = const [],
  });
  final String id, title;
  final List<ReferenceResponseClip> clips;
  final List<ReferenceResponseGroup> groups;
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
      groups: referenceResponseGroups(bundle, id),
    ));
  }
  final order = recommendedTopics.keys.toList();
  topics.sort((left, right) =>
      order.indexOf(left.id).compareTo(order.indexOf(right.id)));
  return List.unmodifiable(topics);
}

class ReferenceResponseMember {
  const ReferenceResponseMember(
      this.videoId, this.channelId, this.views, this.observedAt, this.passed);
  final String videoId, channelId;
  final int views;
  final DateTime observedAt;
  final bool passed;
  Uri get sourceUrl => Uri.https('www.youtube.com', '/watch', {'v': videoId});
}

class ReferenceResponseGroup {
  const ReferenceResponseGroup({
    required this.category,
    required this.format,
    required this.ageGroup,
    required this.metricVersion,
    required this.thresholdViews,
    required this.benchmarkSize,
    required this.benchmarkChannels,
    this.sourceGroupIndex = 0,
    required this.observedFrom,
    required this.observedUntil,
    required this.members,
  });
  final String category, format, ageGroup, metricVersion;
  final int thresholdViews, benchmarkSize, benchmarkChannels;
  final int sourceGroupIndex;
  final DateTime observedFrom, observedUntil;
  final List<ReferenceResponseMember> members;
  int get sampleSize => members.length;
  int get passingCount => members.where((row) => row.passed).length;
  int get channelCount => members.map((row) => row.channelId).toSet().length;
  String get percentage {
    final value = (100 * passingCount / sampleSize).toStringAsFixed(2);
    return value.replaceFirst(RegExp(r'\.?0+$'), '');
  }

  String get categoryLabel => const {
        'phone': 'Phone',
        'camera': 'Camera',
        'laptop': 'Laptop'
      }[category]!;
  String get formatLabel => format == 'long_form' ? 'คลิปปกติ' : 'Shorts';
  String get ageLabel => const {
        'age_0_7d': 'น้อยกว่า 7 วัน',
        'age_7_30d': '7 ถึงน้อยกว่า 30 วัน',
        'age_30_90d': '30 ถึงน้อยกว่า 90 วัน',
        'age_90_365d': '90 ถึงน้อยกว่า 365 วัน',
        'age_365d_plus': 'ตั้งแต่ 365 วันขึ้นไป',
      }[ageGroup]!;
}

/// Validate the saved calculation against its frozen member observations.
/// Legacy results never acquire a denominator from today's Dataset.
List<ReferenceResponseGroup> referenceResponseGroups(
    Map<String, dynamic> bundle, String topicId) {
  final comparisons = _map(bundle['topic_comparisons']);
  final items = _rows(comparisons['items'])
      .where((item) => item['evidence_topic_id'] == topicId)
      .toList();
  if (items.length != 1) return const [];
  final item = items.single;
  final summary = _map(item['group_response_summary']);
  final cutoff = _date(summary['as_of']);
  if (summary['schema_version'] != 'historical-group-response-v1' ||
      summary['status'] != 'available' ||
      cutoff == null ||
      summary['as_of'] != comparisons['as_of'] ||
      summary['is_prediction'] != false ||
      summary['causal_claim'] != false) {
    return const [];
  }
  final records = <String, Map<String, dynamic>>{};
  final ambiguous = <String>{};
  for (final row in _rows(item['records'])) {
    final id = _text(row['video_id']);
    if (records.containsKey(id)) ambiguous.add(id);
    records[id] = row;
  }
  final groups = <ReferenceResponseGroup>[];
  for (final (sourceGroupIndex, group) in _rows(summary['groups']).indexed) {
    final threshold = _count(group['threshold_views']);
    final from = _date(group['observed_from']);
    final until = _date(group['observed_until']);
    final category = _text(group['category']);
    final format = _text(group['format']);
    final age = _text(group['age_group']);
    final metric = _text(group['view_metric_version']);
    if (threshold == null ||
        from == null ||
        until == null ||
        from.isAfter(until) ||
        until.isAfter(cutoff) ||
        category != bundle['taxonomy_leaf_key'] ||
        !['phone', 'camera', 'laptop'].contains(category) ||
        !['long_form', 'short_form'].contains(format) ||
        !['age_0_7d', 'age_7_30d', 'age_30_90d', 'age_90_365d', 'age_365d_plus']
            .contains(age) ||
        !['youtube_play_start_view_v2', 'youtube_qualified_view_v1']
            .contains(metric)) {
      continue;
    }
    final ids = group['benchmark_video_ids'];
    if (ids is! List ||
        ids.any((id) => id is! String) ||
        ids.toSet().length != ids.length ||
        ids.length != _count(group['benchmark_sample_size'])) {
      continue;
    }
    final benchmark = <ReferenceResponseMember>[];
    final members = <ReferenceResponseMember>[];
    for (final id in ids) {
      final row = records[id];
      if (row == null || ambiguous.contains(id)) continue;
      final observation = _map(row['latest_observation']);
      final views = _count(observation['views']);
      final observed = _date(observation['observed_at']);
      final published = _date(row['published_at']);
      final channel = _text(row['channel_id']);
      if (!RegExp(r'^[A-Za-z0-9_-]{11}$').hasMatch(id) ||
          row['source_record_id'] != id ||
          observation['video_id'] != id ||
          row['data_split'] != 'train' ||
          row['taxonomy_leaf_key'] != category ||
          row['format_group'] != format ||
          row['age_group'] != age ||
          row['view_metric_version'] != metric ||
          observation['view_metric_version'] != metric ||
          row['sampling_frame'] != 'general_protocol_v1' ||
          row['collection_strategy'] == 'recommendation_high_performance' ||
          row['comparison_eligible'] != true ||
          channel.isEmpty ||
          !['detected', 'not_detected'].contains(row['topic_status']) ||
          !['complete', 'partial'].contains(observation['status']) ||
          views == null ||
          observed == null ||
          published == null ||
          observed.isBefore(published) ||
          observed.isBefore(from) ||
          observed.isAfter(until) ||
          cutoff.difference(observed) > const Duration(hours: 24)) {
        continue;
      }
      final member = ReferenceResponseMember(
          id, channel, views, observed, views > threshold);
      benchmark.add(member);
      if (row['topic_status'] == 'detected' &&
          _rows(row['occurrences']).isNotEmpty) {
        members.add(member);
      }
    }
    final passing =
        members.where((row) => row.passed).map((row) => row.videoId).toSet();
    final memberIds = members.map((row) => row.videoId).toSet();
    final declaredIds = group['video_ids'];
    final declaredPassing = group['passing_video_ids'];
    final channels = members.map((row) => row.channelId).toSet().length;
    final benchmarkChannels =
        benchmark.map((row) => row.channelId).toSet().length;
    final percentage = group['percentage'];
    if (benchmark.length != ids.length ||
        members.length < 2 ||
        channels < 2 ||
        members.length != _count(group['sample_size']) ||
        channels != _count(group['channel_count']) ||
        benchmarkChannels != _count(group['benchmark_channel_count']) ||
        passing.length != _count(group['passing_count']) ||
        declaredIds is! List ||
        declaredIds.length != members.length ||
        declaredIds.toSet().length != members.length ||
        !memberIds.containsAll(declaredIds) ||
        declaredPassing is! List ||
        declaredPassing.length != passing.length ||
        declaredPassing.toSet().length != passing.length ||
        !passing.containsAll(declaredPassing) ||
        percentage is! num ||
        !percentage.isFinite ||
        (percentage - 100 * passing.length / members.length).abs() > 0.0051) {
      continue;
    }
    groups.add(ReferenceResponseGroup(
        category: category,
        format: format,
        ageGroup: age,
        metricVersion: metric,
        thresholdViews: threshold,
        benchmarkSize: benchmark.length,
        benchmarkChannels: benchmarkChannels,
        sourceGroupIndex: sourceGroupIndex,
        observedFrom: from,
        observedUntil: until,
        members: List.unmodifiable(members)));
  }
  return List.unmodifiable(groups);
}
