import '../../../core/network/api_client.dart';
import '../../../core/storage/secure_token_storage.dart';
import '../domain/company.dart';

/// Company Core repository — Module 3A. Follows the same pattern as
/// AuthRepository: reads the access token from secure storage per call
/// (not cached in memory here) so a screen never has to thread the
/// token through itself manually.
class CompanyRepository {
  CompanyRepository({ApiClient? apiClient, SecureTokenStorage? storage})
      : _api = apiClient ?? ApiClient(),
        _storage = storage ?? SecureTokenStorage();

  final ApiClient _api;
  final SecureTokenStorage _storage;

  Future<Map<String, String>?> _authHeaders() async {
    final token = await _storage.readAccessToken();
    if (token == null) return null;
    return {'Authorization': 'Bearer $token'};
  }

  Future<ApiResult<List<CompanySummary>>> listMyCompanies() async {
    final headers = await _authHeaders();
    if (headers == null) return const ApiErr('UNAUTHENTICATED', 'Not signed in.');
    final result = await _api.getJsonList('/api/v1/companies', headers: headers);
    return switch (result) {
      ApiOk(:final data) =>
        ApiOk(data.map((e) => CompanySummary.fromJson(e as Map<String, dynamic>)).toList()),
      ApiErr(:final code, :final message) => ApiErr(code, message),
    };
  }

  Future<ApiResult<CompanyDetail>> createCompany(Map<String, dynamic> payload) async {
    final headers = await _authHeaders();
    if (headers == null) return const ApiErr('UNAUTHENTICATED', 'Not signed in.');
    final result = await _api.postJson('/api/v1/companies', body: payload, headers: headers);
    return _mapToDetail(result);
  }

  Future<ApiResult<CompanyDetail>> getCompany(String companyId) async {
    final headers = await _authHeaders();
    if (headers == null) return const ApiErr('UNAUTHENTICATED', 'Not signed in.');
    final result = await _api.getJson('/api/v1/companies/$companyId', headers: headers);
    return _mapToDetail(result);
  }

  Future<ApiResult<CompanyDetail>> updateCompany(String companyId, Map<String, dynamic> payload) async {
    final headers = await _authHeaders();
    if (headers == null) return const ApiErr('UNAUTHENTICATED', 'Not signed in.');
    final result = await _api.patchJson('/api/v1/companies/$companyId', body: payload, headers: headers);
    return _mapToDetail(result);
  }

  /// Returns true on success. Matches the Future&lt;bool&gt; pattern already
  /// established by AuthRepository.revokeSession for delete operations,
  /// rather than ApiResult&lt;void&gt; (void is not a meaningful generic type
  /// argument for ApiOk&lt;T&gt;'s `final T data` field).
  Future<bool> deleteCompany(String companyId) async {
    final headers = await _authHeaders();
    if (headers == null) return false;
    final result = await _api.deleteJson('/api/v1/companies/$companyId', headers: headers);
    return result is ApiOk;
  }

  ApiResult<CompanyDetail> _mapToDetail(ApiResult<Map<String, dynamic>> result) {
    return switch (result) {
      ApiOk(:final data) => ApiOk(CompanyDetail.fromJson(data)),
      ApiErr(:final code, :final message) => ApiErr(code, message),
    };
  }
}
