Map<String, dynamic> _object(dynamic value) =>
    value is Map ? Map<String, dynamic>.from(value) : {};
List<Map<String, dynamic>> _rows(dynamic value) =>
    value is List ? value.whereType<Map>().map(_object).toList() : [];
double? _score(dynamic value) =>
    value is num && value.isFinite && value >= 0 && value <= 1
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
  String get category => raw['category'] as String? ?? 'unknown';
  int get referenceCount => raw['reference_count'] as int;
  int get eligibleCount => raw['eligible_count'] as int;
  int get minimumViews => raw['minimum_views'] as int;
  bool get clusteringReady => clustering['status'] == 'ready';
  List<Map<String, dynamic>> get clusters => _rows(clustering['clusters']);
  double? get lowScore => _score(similarity['low_score']);
  double? get highScore => _score(similarity['high_score']);
  String? get closest => similarity['status'] == 'ready' &&
          lowScore != null &&
          highScore != null &&
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
      'text_centroid_tie' => 'ระยะห่างไปยัง Text Centroid ของ High และ Low เท่ากัน',
      'no_semantic_similarity' => 'ไม่พบความคล้ายเชิงความหมายกับทั้งสองกลุ่ม',
      'embedding_unavailable' => 'ยังโหลดโมเดล SentenceTransformer ไม่สำเร็จ กรุณาตรวจการติดตั้งและไฟล์โมเดล',
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
