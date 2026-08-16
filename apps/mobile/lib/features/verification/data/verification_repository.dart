import '../../../core/network/api_client.dart';
import '../../../core/storage/secure_token_storage.dart';
import '../domain/verification.dart';

/// Module 3B repository — follows the same per-call token-read pattern
/// as CompanyRepository (Module 3A).
class VerificationRepository {
  VerificationRepository({ApiClient? apiClient, SecureTokenStorage? storage})
      : _api = apiClient ?? ApiClient(),
        _storage = storage ?? SecureTokenStorage();

  final ApiClient _api;
  final SecureTokenStorage _storage;

  Future<Map<String, String>?> _authHeaders() async {
    final token = await _storage.readAccessToken();
    if (token == null) return null;
    return {'Authorization': 'Bearer $token'};
  }

  Future<ApiResult<VerificationScore>> getVerification(String companyId) async {
    final headers = await _authHeaders();
    if (headers == null) return const ApiErr('UNAUTHENTICATED', 'Not signed in.');
    final result = await _api.getJson('/api/v1/companies/$companyId/verification', headers: headers);
    return switch (result) {
      ApiOk(:final data) => ApiOk(VerificationScore.fromJson(data)),
      ApiErr(:final code, :final message) => ApiErr(code, message),
    };
  }

  Future<ApiResult<Map<String, dynamic>>> getBusinessInfo(String companyId) async {
    final headers = await _authHeaders();
    if (headers == null) return const ApiErr('UNAUTHENTICATED', 'Not signed in.');
    return _api.getJson('/api/v1/companies/$companyId/business-info', headers: headers);
  }

  Future<ApiResult<Map<String, dynamic>>> updateBusinessInfo(
    String companyId,
    Map<String, dynamic> payload,
  ) async {
    final headers = await _authHeaders();
    if (headers == null) return const ApiErr('UNAUTHENTICATED', 'Not signed in.');
    return _api.patchJson('/api/v1/companies/$companyId/business-info', body: payload, headers: headers);
  }

  Future<ApiResult<CompanyBranding>> getBranding(String companyId) async {
    final headers = await _authHeaders();
    if (headers == null) return const ApiErr('UNAUTHENTICATED', 'Not signed in.');
    final result = await _api.getJson('/api/v1/companies/$companyId/branding', headers: headers);
    return switch (result) {
      ApiOk(:final data) => ApiOk(CompanyBranding.fromJson(data)),
      ApiErr(:final code, :final message) => ApiErr(code, message),
    };
  }

  Future<ApiResult<CompanyBranding>> uploadLogo(String companyId, List<int> bytes, String fileName) async {
    final headers = await _authHeaders();
    if (headers == null) return const ApiErr('UNAUTHENTICATED', 'Not signed in.');
    final result = await _api.uploadMultipart(
      '/api/v1/companies/$companyId/logo',
      method: 'POST',
      fileField: 'file',
      fileBytes: bytes,
      fileName: fileName,
      headers: headers,
    );
    return switch (result) {
      ApiOk(:final data) => ApiOk(CompanyBranding.fromJson(data)),
      ApiErr(:final code, :final message) => ApiErr(code, message),
    };
  }

  Future<ApiResult<CompanyBranding>> uploadCoverImage(String companyId, List<int> bytes, String fileName) async {
    final headers = await _authHeaders();
    if (headers == null) return const ApiErr('UNAUTHENTICATED', 'Not signed in.');
    final result = await _api.uploadMultipart(
      '/api/v1/companies/$companyId/cover-image',
      method: 'POST',
      fileField: 'file',
      fileBytes: bytes,
      fileName: fileName,
      headers: headers,
    );
    return switch (result) {
      ApiOk(:final data) => ApiOk(CompanyBranding.fromJson(data)),
      ApiErr(:final code, :final message) => ApiErr(code, message),
    };
  }

  Future<List<VerificationDocument>> listDocuments(String companyId) async {
    final headers = await _authHeaders();
    if (headers == null) return [];
    final result = await _api.getJsonList('/api/v1/companies/$companyId/documents', headers: headers);
    return switch (result) {
      ApiOk(:final data) => data.map((e) => VerificationDocument.fromJson(e as Map<String, dynamic>)).toList(),
      ApiErr() => [],
    };
  }

  Future<ApiResult<VerificationDocument>> uploadDocument(
    String companyId,
    String documentType,
    List<int> bytes,
    String fileName,
  ) async {
    final headers = await _authHeaders();
    if (headers == null) return const ApiErr('UNAUTHENTICATED', 'Not signed in.');
    final result = await _api.uploadMultipart(
      '/api/v1/companies/$companyId/documents',
      method: 'POST',
      fileField: 'file',
      fileBytes: bytes,
      fileName: fileName,
      fields: {'document_type': documentType},
      headers: headers,
    );
    return switch (result) {
      ApiOk(:final data) => ApiOk(VerificationDocument.fromJson(data)),
      ApiErr(:final code, :final message) => ApiErr(code, message),
    };
  }

  Future<bool> deleteDocument(String companyId, String documentId) async {
    final headers = await _authHeaders();
    if (headers == null) return false;
    final result = await _api.deleteJson('/api/v1/companies/$companyId/documents/$documentId', headers: headers);
    return result is ApiOk;
  }
}
