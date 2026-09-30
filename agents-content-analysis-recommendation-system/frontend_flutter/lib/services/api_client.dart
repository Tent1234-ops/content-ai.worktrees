import "dart:convert";
import "dart:typed_data";

import "package:http/http.dart" as http;
import "package:shared_preferences/shared_preferences.dart";

class ApiClient {
  ApiClient({String? baseUrl})
      : baseUrl =
            (baseUrl ?? _configuredBaseUrl).replaceFirst(RegExp(r'/$'), '');

  static const String _configuredBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://127.0.0.1:8000',
  );

  final String baseUrl;

  Future<Map<String, String>> _headers({bool json = true}) async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString("access_token");
    final sessionKey = prefs.getString("trend_session_key");
    final headers = <String, String>{};
    if (json) {
      headers["Content-Type"] = "application/json";
    }
    if (token != null && token.isNotEmpty) {
      headers["Authorization"] =
          "Bearer " + token; // ignore: prefer_interpolation_to_compose_strings
    }
    if (sessionKey != null && sessionKey.isNotEmpty) {
      headers["X-Trend-Session-Key"] = sessionKey;
    }
    return headers;
  }

  Future<dynamic> get(String path) async {
    final response = await http.get(
      Uri.parse(baseUrl + path),
      headers: await _headers(json: false),
    );
    return _decode(response);
  }

  Future<dynamic> post(String path, Map<String, dynamic> body) async {
    final response = await http.post(
      Uri.parse(baseUrl + path),
      headers: await _headers(),
      body: jsonEncode(body),
    );
    return _decode(response);
  }

  Future<dynamic> put(String path, Map<String, dynamic> body) async {
    final response = await http.put(
      Uri.parse(baseUrl + path),
      headers: await _headers(),
      body: jsonEncode(body),
    );
    return _decode(response);
  }

  Future<dynamic> delete(String path, {Map<String, dynamic>? body}) async {
    final response = await http.delete(
      Uri.parse(baseUrl + path),
      headers: await _headers(json: body != null),
      body: body == null ? null : jsonEncode(body),
    );
    return _decode(response);
  }

  Future<dynamic> postMultipart(
    String path, {
    String? filePath,
    Uint8List? fileBytes,
    Stream<List<int>>? fileStream,
    int? fileSize,
    required String fileName,
    Map<String, String> fields = const {},
  }) async {
    final request = http.MultipartRequest('POST', Uri.parse(baseUrl + path));
    final headers = await _headers(json: false);
    request.headers.addAll(headers);
    request.fields.addAll(fields);
    if (fileBytes != null) {
      request.files.add(
          http.MultipartFile.fromBytes("file", fileBytes, filename: fileName));
    } else if (filePath != null) {
      request.files.add(await http.MultipartFile.fromPath("file", filePath,
          filename: fileName));
    } else if (fileStream != null && fileSize != null) {
      request.files.add(
          http.MultipartFile("file", fileStream, fileSize, filename: fileName));
    } else {
      throw ArgumentError(
          "Either filePath, fileBytes, or fileStream must be provided for multipart upload.");
    }
    final streamed = await request.send();
    final response = await http.Response.fromStream(streamed);
    return _decode(response);
  }

  dynamic _decode(http.Response response) {
    final rawBody = response.body;
    dynamic body;
    if (rawBody.isEmpty) {
      body = {};
    } else {
      try {
        body = jsonDecode(rawBody);
      } catch (_) {
        body = rawBody;
      }
    }

    if (response.statusCode >= 400) {
      if (body is Map<String, dynamic>) {
        throw Exception(body['detail'] ?? body['message'] ?? body.toString());
      }
      if (rawBody.isNotEmpty) {
        throw Exception('HTTP ${response.statusCode}: $rawBody');
      }
      throw Exception(
        'HTTP ${response.statusCode}: ${response.reasonPhrase ?? 'Unknown error'}',
      );
    }
    return body;
  }
}
