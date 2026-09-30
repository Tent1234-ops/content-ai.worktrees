import 'dart:convert';
import 'dart:io';

import 'package:content_ai_web/utils/notebooklm_markdown_parser.dart';

// Use the web import parser so a local batch and the UI extract identical text.
void main(List<String> arguments) {
  if (arguments.length < 2) {
    stderr.writeln('Usage: dart run tool/export_notebooklm_batch.dart '
        '<new-output.json> <leaf=directory> [leaf=directory ...]');
    exitCode = 64;
    return;
  }
  final output = File(arguments.first);
  if (output.existsSync()) {
    throw FileSystemException(
        'Refusing to overwrite an existing export', output.path);
  }
  final rows = <Map<String, Object?>>[];
  for (final input in arguments.skip(1)) {
    final separator = input.indexOf('=');
    if (separator <= 0) throw ArgumentError('Expected leaf=directory');
    final leaf = input.substring(0, separator);
    if (!{'phone', 'camera', 'laptop', 'unknown'}.contains(leaf)) {
      throw ArgumentError('Unsupported leaf: $leaf');
    }
    final directory = Directory(input.substring(separator + 1));
    final files = directory
        .listSync()
        .whereType<File>()
        .where((file) => file.path.toLowerCase().endsWith('.md'))
        .toList()
      ..sort((a, b) => a.path.compareTo(b.path));
    for (final file in files) {
      final row = <String, Object?>{
        'path': file.absolute.path,
        'leaf_key': leaf,
      };
      try {
        final doc = NotebookLmMarkdownParser.parse(file.readAsStringSync());
        row.addAll({
          'status': 'parsed',
          'title': doc.sourceTitle,
          'source_url': doc.sourceUrl,
          'declared_video_id': doc.sourceVideoId,
          'transcript': doc.transcript,
        });
      } on FormatException catch (error) {
        row.addAll({'status': 'invalid', 'error': error.message});
      }
      rows.add(row);
    }
  }
  output.parent.createSync(recursive: true);
  output.writeAsStringSync(const JsonEncoder.withIndent('  ').convert({
    'schema_version': 'notebooklm-local-batch-v1',
    'items': rows,
  }));
  stdout.writeln(jsonEncode({
    'output': output.path,
    'files': rows.length,
    'parsed': rows.where((row) => row['status'] == 'parsed').length,
    'invalid': rows.where((row) => row['status'] == 'invalid').length,
  }));
}
