// ignore_for_file: avoid_web_libraries_in_flutter, deprecated_member_use

import 'dart:html' as html;
import 'dart:typed_data';

import 'package:video_player/video_player.dart';

Future<Duration?> readVideoDuration({
  required String fileName,
  String? filePath,
  Uint8List? fileBytes,
}) async {
  if (fileBytes == null || fileBytes.isEmpty) return null;

  final blob = html.Blob(<Object>[fileBytes], _mimeTypeFor(fileName));
  final objectUrl = html.Url.createObjectUrlFromBlob(blob);
  final controller = VideoPlayerController.networkUrl(Uri.parse(objectUrl));
  try {
    await controller.initialize().timeout(const Duration(seconds: 20));
    final duration = controller.value.duration;
    return duration > Duration.zero ? duration : null;
  } finally {
    await controller.dispose();
    html.Url.revokeObjectUrl(objectUrl);
  }
}

String _mimeTypeFor(String fileName) {
  final extension = fileName.split('.').last.toLowerCase();
  switch (extension) {
    case 'webm':
      return 'video/webm';
    case 'mov':
      return 'video/quicktime';
    case 'm4v':
      return 'video/x-m4v';
    default:
      return 'video/mp4';
  }
}
