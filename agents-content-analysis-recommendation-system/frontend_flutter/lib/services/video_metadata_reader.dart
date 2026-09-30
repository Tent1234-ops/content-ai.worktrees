import 'dart:typed_data';

import 'video_metadata_reader_stub.dart'
    if (dart.library.html) 'video_metadata_reader_web.dart'
    if (dart.library.io) 'video_metadata_reader_io.dart' as platform;

Future<Duration?> readVideoDuration({
  required String fileName,
  String? filePath,
  Uint8List? fileBytes,
}) {
  return platform.readVideoDuration(
    fileName: fileName,
    filePath: filePath,
    fileBytes: fileBytes,
  );
}
