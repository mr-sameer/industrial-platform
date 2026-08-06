import '../../../core/network/api_client.dart';
import '../../../core/storage/secure_token_storage.dart';
import '../domain/user.dart';

/// Talks to the FastAPI auth endpoints directly (see
/// docs/adr/0012-web-session-strategy.md for why mobile — unlike web —
/// does this without a BFF) and persists tokens via SecureTokenStorage.
class AuthRepository {
  AuthRepository({ApiClient? apiClient, SecureTokenStorage? storage})
      : _api = apiClient ?? ApiClient(),
        _storage = storage ?? SecureTokenStorage();

  final ApiClient _api;
  final SecureTokenStorage _storage;

  Future<ApiResult<AppUser>> register({
    required String email,
    required String password,
    required String fullName,
    String? deviceName,
  }) async {
    final result = await _api.postJson(
      '/api/v1/auth/register',
      body: {
        'email': email,
        'password': password,
        'full_name': fullName,
        if (deviceName != null) 'device_name': deviceName,
      },
    );
    return _handleTokenPair(result);
  }

  Future<ApiResult<AppUser>> login({
    required String email,
    required String password,
    String? deviceName,
  }) async {
    final result = await _api.postJson(
      '/api/v1/auth/login',
      body: {
        'email': email,
        'password': password,
        if (deviceName != null) 'device_name': deviceName,
      },
    );
    return _handleTokenPair(result);
  }

  /// Attempts to restore a session from stored tokens on app launch.
  /// Returns null (not an ApiErr) if there's simply no stored session yet.
  Future<AppUser?> tryRestoreSession() async {
    final refreshToken = await _storage.readRefreshToken();
    if (refreshToken == null) return null;

    final result = await _api.postJson(
      '/api/v1/auth/refresh',
      body: {'refresh_token': refreshToken},
    );
    final handled = await _handleTokenPair(result);
    return switch (handled) {
      ApiOk(:final data) => data,
      ApiErr() => null,
    };
  }

  /// Logs out *this device only*. The API's /auth/logout requires the
  /// refresh token in the request body to know which session to revoke
  /// (see docs/adr/0014-refresh-token-and-session-model.md) — it must be
  /// read from storage *before* clearing it below.
  Future<void> logout() async {
    final refreshToken = await _storage.readRefreshToken();
    if (refreshToken != null) {
      await _api.postJson('/api/v1/auth/logout', body: {'refresh_token': refreshToken});
    }
    await _storage.clear();
  }

  /// "Log out everywhere" — revokes every session for this user, not just this device.
  Future<void> logoutAll() async {
    final accessToken = await _storage.readAccessToken();
    if (accessToken != null) {
      await _api.postJson(
        '/api/v1/auth/logout-all',
        headers: {'Authorization': 'Bearer $accessToken'},
      );
    }
    await _storage.clear();
  }

  /// "Your active sessions" — see docs/adr/0014. Returns an empty list on
  /// failure rather than surfacing an ApiErr, since this is a
  /// secondary/settings-screen feature, not a blocking flow.
  Future<List<Map<String, dynamic>>> listSessions() async {
    final accessToken = await _storage.readAccessToken();
    if (accessToken == null) return [];
    final result = await _api.getJsonList(
      '/api/v1/auth/sessions',
      headers: {'Authorization': 'Bearer $accessToken'},
    );
    return switch (result) {
      ApiOk(:final data) => data.cast<Map<String, dynamic>>(),
      ApiErr() => [],
    };
  }

  Future<bool> revokeSession(String sessionId) async {
    final accessToken = await _storage.readAccessToken();
    if (accessToken == null) return false;
    final result = await _api.deleteJson(
      '/api/v1/auth/sessions/$sessionId',
      headers: {'Authorization': 'Bearer $accessToken'},
    );
    return result is ApiOk;
  }

  Future<ApiResult<AppUser>> _handleTokenPair(ApiResult<Map<String, dynamic>> result) async {
    switch (result) {
      case ApiOk(:final data):
        await _storage.saveTokens(
          accessToken: data['access_token'] as String,
          refreshToken: data['refresh_token'] as String,
        );
        return ApiOk(AppUser.fromJson(data['user'] as Map<String, dynamic>));
      case ApiErr(:final code, :final message):
        return ApiErr(code, message);
    }
  }
}
