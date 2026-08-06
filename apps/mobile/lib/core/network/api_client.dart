import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:logger/logger.dart';

import '../config/env_config.dart';

/// Mirrors the ApiResponse<T> discriminated union from
/// packages/shared-types/src/api-response.ts and app/core/responses.py.
sealed class ApiResult<T> {
  const ApiResult();
}

class ApiOk<T> extends ApiResult<T> {
  final T data;
  const ApiOk(this.data);
}

class ApiErr<T> extends ApiResult<T> {
  final String code;
  final String message;
  const ApiErr(this.code, this.message);
}

/// Thin HTTP wrapper for calling the FastAPI backend. Centralizing this now
/// means auth headers (Module 2), retries, and tracing can be added in one
/// place later without touching call sites.
class ApiClient {
  ApiClient({http.Client? httpClient, Logger? logger})
      : _http = httpClient ?? http.Client(),
        _logger = logger ?? Logger();

  final http.Client _http;
  final Logger _logger;

  Future<ApiResult<Map<String, dynamic>>> getJson(
    String path, {
    Map<String, String>? headers,
  }) async {
    final uri = Uri.parse('${EnvConfig.apiBaseUrl}$path');
    try {
      final response = await _http.get(uri, headers: headers).timeout(const Duration(seconds: 10));
      return _parseEnvelope(response.body);
    } catch (e) {
      _logger.e('api_fetch_failed', error: e, stackTrace: StackTrace.current);
      return const ApiErr('NETWORK_ERROR', 'Unable to reach the API service.');
    }
  }

  Future<ApiResult<Map<String, dynamic>>> postJson(
    String path, {
    Object? body,
    Map<String, String>? headers,
  }) async {
    final uri = Uri.parse('${EnvConfig.apiBaseUrl}$path');
    try {
      final response = await _http
          .post(
            uri,
            headers: {'Content-Type': 'application/json', ...?headers},
            body: body != null ? jsonEncode(body) : null,
          )
          .timeout(const Duration(seconds: 10));
      if (response.statusCode == 204) return const ApiOk({});
      return _parseEnvelope(response.body);
    } catch (e) {
      _logger.e('api_post_failed', error: e, stackTrace: StackTrace.current);
      return const ApiErr('NETWORK_ERROR', 'Unable to reach the API service.');
    }
  }

  Future<ApiResult<Map<String, dynamic>>> patchJson(
    String path, {
    Object? body,
    Map<String, String>? headers,
  }) async {
    final uri = Uri.parse('${EnvConfig.apiBaseUrl}$path');
    try {
      final response = await _http
          .patch(
            uri,
            headers: {'Content-Type': 'application/json', ...?headers},
            body: body != null ? jsonEncode(body) : null,
          )
          .timeout(const Duration(seconds: 10));
      if (response.statusCode == 204) return const ApiOk({});
      return _parseEnvelope(response.body);
    } catch (e) {
      _logger.e('api_patch_failed', error: e, stackTrace: StackTrace.current);
      return const ApiErr('NETWORK_ERROR', 'Unable to reach the API service.');
    }
  }

  /// For endpoints whose envelope `data` field is a JSON array (e.g.
  /// GET /auth/sessions), not an object — getJson's _parseEnvelope
  /// assumes `data` is always a Map, which throws a cast error on a list.
  Future<ApiResult<List<dynamic>>> getJsonList(
    String path, {
    Map<String, String>? headers,
  }) async {
    final uri = Uri.parse('${EnvConfig.apiBaseUrl}$path');
    try {
      final response = await _http.get(uri, headers: headers).timeout(const Duration(seconds: 10));
      final body = jsonDecode(response.body) as Map<String, dynamic>;
      if (body['success'] == true) {
        return ApiOk(body['data'] as List<dynamic>);
      }
      final error = body['error'] as Map<String, dynamic>?;
      return ApiErr(
        error?['code'] as String? ?? 'UNKNOWN_ERROR',
        error?['message'] as String? ?? 'Unknown error',
      );
    } catch (e) {
      _logger.e('api_fetch_list_failed', error: e, stackTrace: StackTrace.current);
      return const ApiErr('NETWORK_ERROR', 'Unable to reach the API service.');
    }
  }

  Future<ApiResult<Map<String, dynamic>>> deleteJson(
    String path, {
    Map<String, String>? headers,
  }) async {
    final uri = Uri.parse('${EnvConfig.apiBaseUrl}$path');
    try {
      final response = await _http.delete(uri, headers: headers).timeout(const Duration(seconds: 10));
      if (response.statusCode == 204 || response.body.isEmpty) return const ApiOk({});
      return _parseEnvelope(response.body);
    } catch (e) {
      _logger.e('api_delete_failed', error: e, stackTrace: StackTrace.current);
      return const ApiErr('NETWORK_ERROR', 'Unable to reach the API service.');
    }
  }

  ApiResult<Map<String, dynamic>> _parseEnvelope(String responseBody) {
    final body = jsonDecode(responseBody) as Map<String, dynamic>;
    if (body['success'] == true) {
      return ApiOk(body['data'] as Map<String, dynamic>);
    }
    final error = body['error'] as Map<String, dynamic>?;
    return ApiErr(
      error?['code'] as String? ?? 'UNKNOWN_ERROR',
      error?['message'] as String? ?? 'Unknown error',
    );
  }
}
