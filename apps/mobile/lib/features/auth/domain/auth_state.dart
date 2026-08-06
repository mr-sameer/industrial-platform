import 'package:flutter/foundation.dart';

import '../data/auth_repository.dart';
import '../../../core/network/api_client.dart';
import 'user.dart';

enum AuthStatus { loading, authenticated, unauthenticated }

/// App-wide auth state, exposed via `provider` (see main.dart). Mirrors
/// the role AuthContext plays on web, adapted for a native app with no
/// bootstrap-on-every-page-load concept — restoration happens once, at
/// launch, in `restore()`.
class AuthState extends ChangeNotifier {
  AuthState({AuthRepository? repository}) : _repository = repository ?? AuthRepository();

  final AuthRepository _repository;

  AuthStatus status = AuthStatus.loading;
  AppUser? user;

  Future<void> restore() async {
    final restoredUser = await _repository.tryRestoreSession();
    user = restoredUser;
    status = restoredUser != null ? AuthStatus.authenticated : AuthStatus.unauthenticated;
    notifyListeners();
  }

  Future<String?> login({required String email, required String password}) async {
    final result = await _repository.login(email: email, password: password);
    return switch (result) {
      ApiOk(:final data) => _onAuthenticated(data),
      ApiErr(:final message) => message,
    };
  }

  Future<String?> register({
    required String email,
    required String password,
    required String fullName,
  }) async {
    final result = await _repository.register(email: email, password: password, fullName: fullName);
    return switch (result) {
      ApiOk(:final data) => _onAuthenticated(data),
      ApiErr(:final message) => message,
    };
  }

  Future<void> logout() async {
    await _repository.logout();
    user = null;
    status = AuthStatus.unauthenticated;
    notifyListeners();
  }

  /// "Log out everywhere" — revokes every session for this user, not just this device.
  Future<void> logoutAll() async {
    await _repository.logoutAll();
    user = null;
    status = AuthStatus.unauthenticated;
    notifyListeners();
  }

  Future<List<Map<String, dynamic>>> listSessions() => _repository.listSessions();

  Future<bool> revokeSession(String sessionId) => _repository.revokeSession(sessionId);

  String? _onAuthenticated(AppUser authenticatedUser) {
    user = authenticatedUser;
    status = AuthStatus.authenticated;
    notifyListeners();
    return null; // null == no error, matching the login()/register() return contract
  }
}
