import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../companies/presentation/company_list_screen.dart';
import '../../health/presentation/health_screen.dart';
import '../domain/auth_state.dart';
import 'login_screen.dart';
import 'sessions_screen.dart';

/// Root-level switch on AuthStatus. `main()` calls `AuthState.restore()`
/// once at launch; this widget just renders whatever that settles into.
class AuthGate extends StatelessWidget {
  const AuthGate({super.key});

  @override
  Widget build(BuildContext context) {
    final authState = context.watch<AuthState>();
    return switch (authState.status) {
      AuthStatus.loading => const Scaffold(body: Center(child: CircularProgressIndicator())),
      AuthStatus.unauthenticated => const LoginScreen(),
      AuthStatus.authenticated => const _AuthenticatedHome(),
    };
  }
}

class _AuthenticatedHome extends StatelessWidget {
  const _AuthenticatedHome();

  @override
  Widget build(BuildContext context) {
    final authState = context.watch<AuthState>();
    return HealthScreen(
      title: 'Hi, ${authState.user?.fullName ?? ''}',
      appBarActions: [
        IconButton(
          icon: const Icon(Icons.business_outlined),
          tooltip: 'Your companies',
          onPressed: () => Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => const CompanyListScreen()),
          ),
        ),
        IconButton(
          icon: const Icon(Icons.devices_other),
          tooltip: 'Active sessions',
          onPressed: () => Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => const SessionsScreen()),
          ),
        ),
        IconButton(
          icon: const Icon(Icons.logout),
          tooltip: 'Log out',
          onPressed: () => context.read<AuthState>().logout(),
        ),
      ],
    );
  }
}
