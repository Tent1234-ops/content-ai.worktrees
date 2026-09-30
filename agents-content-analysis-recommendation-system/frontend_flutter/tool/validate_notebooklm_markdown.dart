import 'dart:io';

import 'package:content_ai_web/utils/notebooklm_markdown_parser.dart';

void main(List<String> arguments) {
  if (arguments.length != 1) {
    stderr.writeln(
      'Usage: dart run tool/validate_notebooklm_markdown.dart <directory>',
    );
    exitCode = 64;
    return;
  }

  final directory = Directory(arguments.single);
  if (!directory.existsSync()) {
    stderr.writeln('Directory not found: ${directory.path}');
    exitCode = 66;
    return;
  }

  final files = directory
      .listSync()
      .whereType<File>()
      .where((file) => file.path.toLowerCase().endsWith('.md'))
      .toList()
    ..sort((left, right) => left.path.compareTo(right.path));

  var passed = 0;
  var totalCharacters = 0;
  final failures = <String>[];
  for (final file in files) {
    try {
      final document = NotebookLmMarkdownParser.parse(file.readAsStringSync());
      passed += 1;
      totalCharacters += document.transcript.length;
      stdout.writeln(
        'PASS | ${_fileName(file.path)} | '
        '${document.transcript.length} characters',
      );
    } on Object catch (error) {
      failures.add('${_fileName(file.path)}: $error');
      stdout.writeln('FAIL | ${_fileName(file.path)} | $error');
    }
  }

  stdout.writeln(
    'SUMMARY | files=${files.length} | passed=$passed | '
    'failed=${failures.length} | transcript_characters=$totalCharacters',
  );
  if (failures.isNotEmpty) exitCode = 1;
}

String _fileName(String path) => path.split(Platform.pathSeparator).last;
