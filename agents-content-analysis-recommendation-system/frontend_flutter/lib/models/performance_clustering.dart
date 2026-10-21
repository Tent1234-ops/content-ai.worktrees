Map<String, dynamic> _object(dynamic value) =>
    value is Map ? Map<String, dynamic>.from(value) : {};
List<Map<String, dynamic>> _rows(dynamic value) =>
    value is List ? value.whereType<Map>().map(_object).toList() : [];
double? _score(dynamic value, {double min = 0, double max = 1}) =>
    value is num && value.isFinite && value >= min && value <= max
        ? value.toDouble()
        : null;

class PerformanceComparison {
  PerformanceComparison.fromJson(Map<String, dynamic> json)
      : raw = json,
        clustering = _object(json['clustering']),
        similarity = _object(json['content_similarity']),
        videos = _rows(json['reference_videos']),
        advice = _rows(json['recommendations']) {
    if (json['schema_version'] != 'performance-clustering-v1' ||
        json['reference_count'] is! int ||
        json['eligible_count'] is! int ||
        json['minimum_views'] is! int ||
        referenceCount < 0 ||
        eligibleCount < 0 ||
        eligibleCount > referenceCount ||
        minimumViews < 0) {
      throw const FormatException('Invalid performance comparison');
    }
    if (clusteringReady &&
        (clusters.length != 2 ||
            videos.length != eligibleCount ||
            clusters
                .map((c) => c['performance_level'])
                .toSet()
                .difference({'low', 'high'}).isNotEmpty ||
            clusters.map((c) => c['performance_level']).toSet().length != 2)) {
      throw const FormatException('Incomplete performance clusters');
    }
    if (clusteringReady) {
      bool validNumber(dynamic value) =>
          value is num && value.isFinite && value >= 0;
      if (videos.isEmpty ||
          clusters.any((c) =>
              c['video_count'] is! int ||
              c['video_count'] < 2 ||
              ['average_views', 'average_likes', 'median_views', 'median_likes']
                  .any((key) => !validNumber(c[key]))) ||
          videos.any((v) =>
              !validNumber(v['views']) ||
              !validNumber(v['likes']) ||
              !const ['low', 'high'].contains(v['performance_level'])) ||
          clusters.any((c) =>
              c['video_count'] !=
              videos
                  .where(
                      (v) => v['performance_level'] == c['performance_level'])
                  .length)) {
        throw const FormatException('Invalid performance measurements');
      }
    }
  }
  final Map<String, dynamic> raw, clustering, similarity;
  final List<Map<String, dynamic>> videos, advice;
  List<PerformanceInsight> get insights => closest == null
      ? const []
      : advice
          .map((item) => PerformanceInsight.parse(item, videos))
          .whereType<PerformanceInsight>()
          .toList(growable: false);
  String get category => raw['category'] as String? ?? 'unknown';
  int get referenceCount => raw['reference_count'] as int;
  int get eligibleCount => raw['eligible_count'] as int;
  int get minimumViews => raw['minimum_views'] as int;
  bool get clusteringReady => clustering['status'] == 'ready';
  List<Map<String, dynamic>> get clusters => _rows(clustering['clusters']);
  bool get usesTextCentroid =>
      similarity['method'] == 'sentence_embedding_text_centroid_cosine';
  double? get lowScore =>
      _score(similarity['low_score'], min: usesTextCentroid ? -1 : 0);
  double? get highScore =>
      _score(similarity['high_score'], min: usesTextCentroid ? -1 : 0);
  double? get lowDistance => _score(similarity['low_distance'], max: 2);
  double? get highDistance => _score(similarity['high_distance'], max: 2);
  String? get closest => similarity['status'] == 'ready' &&
          lowScore != null &&
          highScore != null &&
          (!usesTextCentroid ||
              (lowDistance != null && highDistance != null)) &&
          const ['low', 'high'].contains(similarity['closest_group'])
      ? similarity['closest_group'] as String
      : null;
  List<String> get sharedKeywords =>
      (raw['shared_keywords'] as List? ?? []).whereType<String>().toList();
  List<String> get missingKeywords =>
      (raw['missing_keywords'] as List? ?? []).whereType<String>().toList();
  Map<String, int> get exclusions => _object(raw['excluded_counts'])
      .map((key, value) => MapEntry(key, (value as num).toInt()));
}

String _text(dynamic value) => value is String ? value.trim() : '';

class PerformanceInsightReference {
  const PerformanceInsightReference({
    required this.datasetId,
    required this.videoId,
    required this.title,
    required this.channelTitle,
    required this.quote,
    required this.matchedText,
    required this.transcriptHash,
  });
  final int datasetId;
  final String videoId, title, channelTitle, quote, matchedText, transcriptHash;
  Uri get url => Uri.https('www.youtube.com', '/watch', {'v': videoId});
}

class PerformanceInsight {
  const PerformanceInsight({
    required this.topic,
    required this.title,
    required this.summary,
    required this.supportCount,
    required this.channelCount,
    required this.application,
    required this.condition,
    required this.references,
  });
  final String topic, title, summary, application, condition;
  final int supportCount, channelCount;
  final List<PerformanceInsightReference> references;

  static PerformanceInsight? parse(
      Map<String, dynamic> json, List<Map<String, dynamic>> videos) {
    final high = {
      for (final video in videos)
        if (video['performance_level'] == 'high') video['dataset_id']: video
    };
    final ids = json['supporting_dataset_ids'];
    final count = json['support_count'], channels = json['channel_count'];
    if (ids is! List ||
        ids.any((id) => id is! int || !high.containsKey(id)) ||
        ids.toSet().length != ids.length ||
        count is! int ||
        count < 2 ||
        count != ids.length ||
        channels is! int ||
        channels < 2 ||
        ids.map((id) => _text(high[id]!['channel_id'])).toSet().length !=
            channels ||
        ids.any((id) => _text(high[id]!['channel_id']).isEmpty)) {
      return null;
    }
    final topic = _text(json['topic']), title = _text(json['title']);
    final summary = _text(json['summary']);
    if (topic.isEmpty || title.isEmpty || summary.isEmpty) return null;
    final references = <PerformanceInsightReference>[];
    final seen = <int>{};
    for (final ref in _rows(json['references'])) {
      final id = ref['dataset_id'], video = high[ref['dataset_id']];
      if (id is! int || !ids.contains(id) || video == null || !seen.add(id)) {
        continue;
      }
      final videoId = _text(video['video_id']);
      final quote = ref['quote'] is String ? ref['quote'] as String : '';
      final matched =
          ref['matched_text'] is String ? ref['matched_text'] as String : '';
      final hash = _text(ref['transcript_sha256']);
      final start = ref['start_char'], end = ref['end_char'];
      final quoteStart = ref['quote_start_char'],
          quoteEnd = ref['quote_end_char'];
      final runes = quote.runes.toList();
      if (!RegExp(r'^[A-Za-z0-9_-]{11}$').hasMatch(videoId) ||
          ref['video_id'] != videoId ||
          ref['channel_id'] != video['channel_id'] ||
          !RegExp(r'^[a-f0-9]{64}$').hasMatch(hash) ||
          quote.isEmpty ||
          matched.isEmpty ||
          start is! int ||
          end is! int ||
          quoteStart is! int ||
          quoteEnd is! int ||
          quoteStart < 0 ||
          start < quoteStart ||
          end <= start ||
          end > quoteEnd ||
          quoteEnd - quoteStart != runes.length ||
          String.fromCharCodes(
                  runes.sublist(start - quoteStart, end - quoteStart)) !=
              matched) {
        continue;
      }
      references.add(PerformanceInsightReference(
        datasetId: id,
        videoId: videoId,
        title: _text(video['title']).isEmpty ? videoId : _text(video['title']),
        channelTitle: _text(video['channel_title']),
        quote: quote,
        matchedText: matched,
        transcriptHash: hash,
      ));
    }
    if (references.isEmpty) return null;
    final action = _object(json['application']);
    final basis = action['basis_dataset_ids'];
    final groundedAction = action['source'] == 'versioned_topic_template' &&
        action['template_key'] == topic &&
        _text(action['template_version']).isNotEmpty &&
        action['causal_engagement_claim'] == false &&
        basis is List &&
        basis.length == ids.length &&
        basis.toSet().length == ids.length &&
        basis.every(ids.contains);
    return PerformanceInsight(
      topic: topic,
      title: title,
      summary: summary,
      supportCount: count,
      channelCount: channels,
      application: groundedAction ? _text(action['text']) : '',
      condition: groundedAction ? _text(action['condition']) : '',
      references: List.unmodifiable(references),
    );
  }
}

String performanceReason(dynamic reason) => switch (reason) {
      'classification_not_accepted' =>
        'ยังไม่ยืนยันหมวด Phone, Camera หรือ Laptop จึงไม่เลือกกลุ่มอ้างอิง',
      'not_enough_references' =>
        'คลิปอ้างอิงที่มีข้อมูลครบและถึงยอดวิวขั้นต่ำยังไม่พอ (ต้องมีอย่างน้อย 6 คลิป)',
      'identical_kpi_points' =>
        'Views และ Likes เหมือนกันทั้งหมด จึงแบ่งสองกลุ่มไม่ได้',
      'cluster_too_small' =>
        'มีกลุ่มที่เล็กกว่า 2 คลิป จึงยังไม่ใช้เปรียบเทียบ',
      'centroid_order_tie' =>
        'Views และ Likes ให้ลำดับสวนทางกันจนคะแนนเท่ากัน จึงยังตั้งชื่อ Low/High ไม่ได้',
      'insufficient_user_transcript' =>
        'ข้อความถอดเสียงของคลิปนี้ไม่ครบหรือสั้นเกินไปสำหรับเปรียบเทียบ',
      'no_shared_features' => 'ไม่พบคำที่เปรียบเทียบร่วมกับคลิปอ้างอิงได้',
      'empty_vocabulary' => 'ยังไม่มีคำที่ใช้สร้างเวกเตอร์เปรียบเทียบได้',
      'group_without_comparable_features' =>
        'มีกลุ่มที่ไม่มีข้อความเพียงพอสำหรับเปรียบเทียบ',
      'low_similarity' => 'ความคล้ายกับทั้งสองกลุ่มต่ำ จึงยังไม่เลือกกลุ่ม',
      'similar_scores' => 'คะแนนความคล้ายสองกลุ่มใกล้กัน จึงยังสรุปไม่ได้',
      'text_centroid_tie' =>
        'ระยะห่างไปยัง Text Centroid ของ High และ Low เท่ากัน',
      'overlapping_text_centroids' =>
        'Text Centroid ของสองกลุ่มใกล้กันมาก จึงยังแยกด้วยเนื้อหาไม่ได้',
      'similar_text_distances' =>
        'ระยะห่างไปยังสองกลุ่มใกล้กัน จึงยังไม่เลือกกลุ่ม',
      'no_semantic_similarity' => 'ไม่พบความคล้ายเชิงความหมายกับทั้งสองกลุ่ม',
      'embedding_unavailable' =>
        'ยังโหลดโมเดล SentenceTransformer ไม่สำเร็จ กรุณาตรวจการติดตั้งและไฟล์โมเดล',
      'insufficient_reference_transcript' =>
        'Transcript อ้างอิงไม่ครบหรือสั้นเกินไป',
      'below_minimum_views' => 'ยอดวิวต่ำกว่าขั้นต่ำ',
      'missing_or_invalid_kpi' => 'Views หรือ Likes ไม่ครบหรือไม่ถูกต้อง',
      'duplicate_video_or_transcript' => 'วิดีโอหรือข้อความซ้ำ',
      'incompatible_view_metric' => 'นิยามยอดวิวต่างกัน',
      'no_recent_statistics' => 'ไม่มีสถิติภายใน 24 ชั่วโมง',
      'latest_statistics_unavailable' => 'สถิติรอบล่าสุดเก็บไม่สำเร็จ',
      'unknown_view_metric' => 'ไม่ทราบนิยามยอดวิว',
      'statistics_before_publication' => 'วันเก็บสถิติก่อนวันเผยแพร่',
      'transcript_hash_mismatch' => 'ข้อความไม่ตรงกับหลักฐานที่บันทึก',
      _ => 'ข้อมูลยังไม่พร้อมสำหรับการเปรียบเทียบ',
    };
