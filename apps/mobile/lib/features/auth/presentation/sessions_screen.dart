import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../domain/auth_state.dart';

/// "Your active sessions" — Module 2.5 Phase 3's requirement that users
/// can see and revoke their own sessions, mirroring
/// apps/web/src/app/account/sessions/page.tsx.
class SessionsScreen extends StatefulWidget {
  const SessionsScreen({super.key});

  @override
  State<SessionsScreen> createState() => _SessionsScreenState();
}

class _SessionsScreenState extends State<SessionsScreen> {
  List<Map<String, dynamic>>? _sessions;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final sessions = await context.read<AuthState>().listSessions();
    if (!mounted) return;
    setState(() {
      _sessions = sessions;
      _loading = false;
    });
  }

  Future<void> _revoke(String sessionId) async {
    await context.read<AuthState>().revokeSession(sessionId);
    _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Active sessions')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : ListView.builder(
                itemCount: _sessions?.length ?? 0,
                itemBuilder: (context, index) {
                  final session = _sessions![index];
                  final isCurrent = session['is_current'] == true;
                  return ListTile(
                    title: Text(
                      (session['device_name'] as String?) ??
                          (session['browser'] as String?) ??
                          'Unknown device',
                    ),
                    subtitle: Text(
                      '${session['platform'] ?? 'Unknown platform'} · '
                      '${session['ip_address'] ?? 'unknown IP'}'
                      '${isCurrent ? ' (this device)' : ''}',
                    ),
                    trailing: isCurrent
                        ? null
                        : IconButton(
                            icon: const Icon(Icons.delete_outline),
                            tooltip: 'Revoke',
                            onPressed: () => _revoke(session['id'] as String),
                          ),
                  );
                },
              ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => context.read<AuthState>().logoutAll(),
        label: const Text('Log out everywhere'),
        icon: const Icon(Icons.logout),
      ),
    );
  }
}
