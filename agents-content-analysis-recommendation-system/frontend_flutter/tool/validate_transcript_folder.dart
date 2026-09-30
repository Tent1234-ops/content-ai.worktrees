import 'dart:io';

import 'package:content_ai_web/utils/notebooklm_markdown_parser.dart';

final RegExp _youtubeIdPattern = RegExp(
  r'(?:youtu\.be/|youtube\.com/(?:watch\?(?:[^\s#]*&)?v=|shorts/))'
  r'([A-Za-z0-9_-]{11})',
  caseSensitive: false,
);

void main(List<String> args) {
  if (args.length != 1) {
    stderr.writeln(
        'Usage: dart run tool/validate_transcript_folder.dart <folder>');
    exitCode = 64;
    return;
  }

  final directory = Directory(args.single);
  if (!directory.existsSync()) {
    stderr.writeln('Folder not found: ${directory.path}');
    exitCode = 66;
    return;
  }

  final files = directory
      .listSync()
      .whereType<File>()
      .where((file) => file.path.toLowerCase().endsWith('.md'))
      .toList()
    ..sort((left, right) => left.path.compareTo(right.path));
  final videoIds = <String, String>{};
  final transcripts = <String, String>{};
  var passed = 0;
  var failed = 0;

  for (final file in files) {
    final name = file.uri.pathSegments.last;
    try {
      final document = NotebookLmMarkdownParser.parse(file.readAsStringSync());
      final problems = <String>[];
      final warnings = <String>[];
      if ((document.sourceTitle ?? '').trim().isEmpty) {
        problems.add('missing title');
      }
      if ((document.creatorChannel ?? '').trim().isEmpty) {
        warnings.add('channel will be fetched from YouTube during import');
      }
      final sourceUrl = (document.sourceUrl ?? '').trim();
      final idMatch = _youtubeIdPattern.firstMatch(sourceUrl);
      final videoId = idMatch?.group(1);
      if (videoId == null) {
        problems.add('invalid YouTube URL');
      } else if (videoIds.containsKey(videoId)) {
        problems.add('duplicate Video ID with ${videoIds[videoId]}');
      }
      final existingTranscript = transcripts[document.transcript];
      if (existingTranscript != null) {
        problems.add('duplicate transcript with $existingTranscript');
      }

      if (problems.isNotEmpty) {
        failed++;
        stdout.writeln('FAIL $name: ${problems.join(', ')}');
        continue;
      }

      videoIds[videoId!] = name;
      transcripts[document.transcript] = name;
      passed++;
      stdout.writeln(
        'PASS $name | $videoId | ${document.transcript.length} chars'
        '${warnings.isEmpty ? '' : ' | WARN ${warnings.join(', ')}'}',
      );
    } on FormatException catch (error) {
      failed++;
      stdout.writeln('FAIL $name: ${error.message}');
    } on Object catch (error) {
      failed++;
      stdout.writeln('FAIL $name: $error');
    }
  }

  stdout.writeln(
    'SUMMARY files=${files.length} passed=$passed failed=$failed '
    'unique_video_ids=${videoIds.length}',
  );
  if (failed > 0) exitCode = 1;
}
