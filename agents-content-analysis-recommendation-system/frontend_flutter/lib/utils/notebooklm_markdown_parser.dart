class NotebookLmMarkdownDocument {
  const NotebookLmMarkdownDocument({
    required this.transcript,
    this.sourceTitle,
    this.creatorChannel,
    this.sourceUrl,
    this.sourceVideoId,
  });

  final String transcript;
  final String? sourceTitle;
  final String? creatorChannel;
  final String? sourceUrl;
  final String? sourceVideoId;
}

class NotebookLmMarkdownParser {
  static const minTranscriptCharacters = 80;
  static const maxTranscriptCharacters = 2000000;

  static final RegExp _transcriptHeading = RegExp(
    r'^(#{1,6})\s*(cleaned transcription text|cleaned transcript|full source transcript|full transcript|transcription text|transcript|transcript content|transcript segments|[^#]*\(\s*transcript\s*\)|ข้อความถอดเสียง|บทถอดเสียง|ทรานสคริปต์)\s*$',
    caseSensitive: false,
  );
  static final RegExp _anyHeading = RegExp(r'^(#{1,6})\s+\S');
  static final RegExp _boldMetadata = RegExp(
    r'^\s*[-*]\s+\*\*([^*]+?):\*\*\s*(.*?)\s*$',
    caseSensitive: false,
  );
  static final RegExp _plainMetadata = RegExp(
    r'^\s*[-*]\s+([^:]+):\s*(.*?)\s*$',
    caseSensitive: false,
  );
  static final RegExp _standaloneBoldMetadata = RegExp(
    r'^\s*(?:[-*]\s+)?\*\*([^*:]+?)\s*:?\*\*\s*:?\s*(.*?)\s*$',
    caseSensitive: false,
  );
  static final RegExp _documentTitle = RegExp(r'^#\s+(.+?)\s*$');

  static NotebookLmMarkdownDocument parse(String markdown) {
    final normalized = markdown
        .replaceFirst('\uFEFF', '')
        .replaceAll('\r\n', '\n')
        .replaceAll('\r', '\n');
    if (normalized.trim().isEmpty) {
      throw const FormatException('The Markdown file is empty.');
    }

    final lines = normalized.split('\n');
    final metadata = _readMetadata(lines);
    final sourceTitle = metadata['source video'] ??
        metadata['video title'] ??
        metadata['source title'] ??
        metadata['title'] ??
        metadata['ชื่อวิดีโอ'] ??
        _readDocumentTitle(lines);
    final creatorChannel = metadata['creator channel'] ??
        metadata['channel title'] ??
        metadata['ช่อง'] ??
        metadata['ชื่อช่อง'];
    final sourceUrlValue = metadata['source url'] ??
        metadata['video url'] ??
        metadata['video link'] ??
        metadata['direct video link'] ??
        metadata['direct link'] ??
        metadata['youtube url'] ??
        metadata['ลิงก์วิดีโอ'] ??
        metadata['ลิงก์ยูทูบ'] ??
        metadata['source video'];
    final sourceUrl = _urlFrom(sourceUrlValue) ?? _urlFromLines(lines);
    var headingIndex = -1;
    var headingLevel = 0;
    for (var index = 0; index < lines.length; index++) {
      final match = _transcriptHeading.firstMatch(lines[index].trim());
      if (match == null) continue;
      headingIndex = index;
      headingLevel = (match.group(1) ?? '').length;
      break;
    }
    late final List<String> transcriptLines;
    if (headingIndex >= 0) {
      var endIndex = lines.length;
      for (var index = headingIndex + 1; index < lines.length; index++) {
        final match = _anyHeading.firstMatch(lines[index].trim());
        final level = (match?.group(1) ?? '').length;
        if (match != null && level <= headingLevel) {
          endIndex = index;
          break;
        }
      }
      transcriptLines = lines.sublist(headingIndex + 1, endIndex);
    } else {
      final compactStart = _compactTranscriptStart(lines);
      if (compactStart < 0 || sourceUrl == null) {
        throw const FormatException(
          'Transcript section not found. Expected a transcript heading or '
          'a compact document with title, source metadata, and transcript.',
        );
      }
      transcriptLines = lines.sublist(compactStart);
    }
    _trimBlankAndRuleLines(transcriptLines);
    if (transcriptLines.isNotEmpty &&
        transcriptLines.first.trimLeft().startsWith('```')) {
      transcriptLines.removeAt(0);
    }
    if (transcriptLines.isNotEmpty &&
        transcriptLines.last.trimLeft().startsWith('```')) {
      transcriptLines.removeLast();
    }
    _trimBlankAndRuleLines(transcriptLines);

    // Segment numbers are export structure, not spoken words or timestamps.
    transcriptLines.removeWhere((line) => RegExp(
          r'^#{1,6}\s+Segment\s+\d+\s*$',
          caseSensitive: false,
        ).hasMatch(line.trim()));
    final transcript = transcriptLines.join('\n').trim();
    if (RegExp(
      r'^\s*[\[(]?\s*(ไม่พบคำบรรยาย|ไม่พบ\s*transcript|no transcript|transcript (unavailable|not available))',
      caseSensitive: false,
    ).hasMatch(transcript)) {
      throw const FormatException(
        'The file contains a missing-transcript notice, not a transcript.',
      );
    }
    if (transcript.length < minTranscriptCharacters) {
      throw const FormatException(
        'The transcript section must contain at least 80 characters.',
      );
    }
    if (transcript.length > maxTranscriptCharacters) {
      throw const FormatException(
        'The transcript exceeds the 2,000,000 character limit.',
      );
    }

    return NotebookLmMarkdownDocument(
      transcript: transcript,
      sourceTitle: sourceTitle,
      creatorChannel: creatorChannel,
      sourceUrl: sourceUrl,
      sourceVideoId: metadata['youtube video id']?.replaceAll('`', '').trim(),
    );
  }

  static Map<String, String> _readMetadata(List<String> lines) {
    final values = <String, String>{};
    for (final line in lines) {
      final match = _metadataMatch(line);
      if (match == null) continue;
      final key = (match.group(1) ?? '').trim().toLowerCase();
      final value = (match.group(2) ?? '').trim();
      if (key.isNotEmpty && value.isNotEmpty) values[key] = value;
    }
    return values;
  }

  static RegExpMatch? _metadataMatch(String line) {
    return _boldMetadata.firstMatch(line) ??
        _plainMetadata.firstMatch(line) ??
        _standaloneBoldMetadata.firstMatch(line);
  }

  static String? _readDocumentTitle(List<String> lines) {
    for (final line in lines) {
      final match = _documentTitle.firstMatch(line.trim());
      final title = match?.group(1)?.trim();
      if (title != null && title.isNotEmpty) return title;
    }
    return null;
  }

  static int _compactTranscriptStart(List<String> lines) {
    var sawMetadata = false;
    for (var index = 0; index < lines.length; index++) {
      final line = lines[index];
      if (_isBlankOrRule(line)) continue;
      if (index == 0 && _documentTitle.hasMatch(line.trim())) continue;
      if (_metadataMatch(line) != null) {
        sawMetadata = true;
        continue;
      }
      return sawMetadata ? index : -1;
    }
    return -1;
  }

  static String? _urlFrom(String? value) {
    if (value == null) return null;
    final match = RegExp(r'https?://[^\s\])}>]+').firstMatch(value);
    return match?.group(0);
  }

  static String? _urlFromLines(List<String> lines) {
    for (final line in lines) {
      final url = _urlFrom(line);
      if (url != null &&
          (url.contains('youtube.com/') || url.contains('youtu.be/'))) {
        return url;
      }
    }
    return null;
  }

  static void _trimBlankAndRuleLines(List<String> lines) {
    while (lines.isNotEmpty && _isBlankOrRule(lines.first)) {
      lines.removeAt(0);
    }
    while (lines.isNotEmpty && _isBlankOrRule(lines.last)) {
      lines.removeLast();
    }
  }

  static bool _isBlankOrRule(String value) {
    final trimmed = value.trim();
    return trimmed.isEmpty ||
        RegExp(r'^(-{3,}|\*{3,}|_{3,})$').hasMatch(trimmed);
  }
}
