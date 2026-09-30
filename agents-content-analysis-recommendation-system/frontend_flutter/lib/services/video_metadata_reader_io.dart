import 'dart:io';
import 'dart:typed_data';

import 'package:video_player/video_player.dart';

Future<Duration?> readVideoDuration({
  required String fileName,
  String? filePath,
  Uint8List? fileBytes,
}) async {
  if (filePath == null || filePath.isEmpty) return null;

  final controller = VideoPlayerController.file(File(filePath));
  try {
    await controller.initialize().timeout(const Duration(seconds: 20));
    final duration = controller.value.duration;
    return duration > Duration.zero ? duration : null;
  } finally {
    await controller.dispose();
  }
}
