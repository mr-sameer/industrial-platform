import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Wraps platform secure storage (Keychain on iOS, Keystore on Android)
/// for the access and refresh tokens. Unlike the web app (see
/// docs/adr/0012-web-session-strategy.md), mobile has no XSS threat model
/// and no cross-origin cookie problem, so both tokens are stored here
/// directly rather than needing a BFF split.
///
/// ## Biometric gating — architecture prepared, not implemented
/// Module 2.5 Phase 11 asked for the *architecture* to be ready for a
/// biometric gate (Face ID / fingerprint) on top of this storage, without
/// implementing it yet. The seam is here: `readAccessToken` /
/// `readRefreshToken` are the two chokepoints every token read already
/// goes through (AuthRepository never reads flutter_secure_storage
/// directly). A future `BiometricGate` service would sit in front of
/// these two methods — e.g. wrapping them so a read only succeeds after
/// `local_auth`'s `authenticate()` succeeds, with a short grace window
/// (e.g. re-prompt only if the app was backgrounded more than N minutes
/// ago) — without AuthRepository, AuthState, or any UI code needing to
/// change, since they only ever call through this class. Not built now
/// because it requires a UX decision (prompt every launch vs. only after
/// backgrounding vs. only for sensitive actions) that belongs with a
/// product/design pass, not a security-hardening one.
class SecureTokenStorage {
  SecureTokenStorage({FlutterSecureStorage? storage})
      : _storage = storage ?? const FlutterSecureStorage();

  static const _accessTokenKey = 'access_token';
  static const _refreshTokenKey = 'refresh_token';

  final FlutterSecureStorage _storage;

  Future<void> saveTokens({required String accessToken, required String refreshToken}) async {
    await _storage.write(key: _accessTokenKey, value: accessToken);
    await _storage.write(key: _refreshTokenKey, value: refreshToken);
  }

  Future<String?> readAccessToken() => _storage.read(key: _accessTokenKey);

  Future<String?> readRefreshToken() => _storage.read(key: _refreshTokenKey);

  Future<void> clear() async {
    await _storage.delete(key: _accessTokenKey);
    await _storage.delete(key: _refreshTokenKey);
  }
}
