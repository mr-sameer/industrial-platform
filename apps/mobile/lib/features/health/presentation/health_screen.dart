import 'package:flutter/material.dart';

import '../../../core/network/api_client.dart';

class HealthScreen extends StatefulWidget {
  const HealthScreen({super.key, this.title = 'System Health', this.appBarActions});

  final String title;
  final List<Widget>? appBarActions;

  @override
  State<HealthScreen> createState() => _HealthScreenState();
}

class _HealthScreenState extends State<HealthScreen> {
  final _apiClient = ApiClient();
  ApiResult<Map<String, dynamic>>? _result;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _fetchHealth();
  }

  Future<void> _fetchHealth() async {
    setState(() => _loading = true);
    final result = await _apiClient.getJson('/health');
    if (!mounted) return;
    setState(() {
      _result = result;
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.title), actions: widget.appBarActions),
      body: RefreshIndicator(
        onRefresh: _fetchHealth,
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            if (_loading) const Center(child: CircularProgressIndicator()),
            if (!_loading && _result is ApiOk<Map<String, dynamic>>)
              _buildHealthyView(_result as ApiOk<Map<String, dynamic>>),
            if (!_loading && _result is ApiErr<Map<String, dynamic>>)
              _buildErrorView(_result as ApiErr<Map<String, dynamic>>),
          ],
        ),
      ),
    );
  }

  Widget _buildHealthyView(ApiOk<Map<String, dynamic>> ok) {
    final status = ok.data['status'] as String? ?? 'unknown';
    final deps = ok.data['dependencies'] as Map<String, dynamic>? ?? {};
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('API status: $status', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 12),
        for (final entry in deps.entries)
          Text('${entry.key}: ${(entry.value as Map)['status']}'),
      ],
    );
  }

  Widget _buildErrorView(ApiErr<Map<String, dynamic>> err) {
    return Text(
      'Could not reach API: ${err.message}',
      style: const TextStyle(color: Colors.red),
    );
  }
}
