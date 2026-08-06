import 'package:flutter/material.dart';

import '../../../core/network/api_client.dart';
import '../data/company_repository.dart';
import '../domain/company.dart';
import 'company_dashboard_screen.dart';
import 'create_company_screen.dart';

/// "Company List" — Module 3A. Every company the current user belongs
/// to; the mobile equivalent of apps/web/src/app/companies/page.tsx.
class CompanyListScreen extends StatefulWidget {
  const CompanyListScreen({super.key});

  @override
  State<CompanyListScreen> createState() => _CompanyListScreenState();
}

class _CompanyListScreenState extends State<CompanyListScreen> {
  final _repository = CompanyRepository();
  List<CompanySummary>? _companies;
  String? _errorCode;
  String? _errorMessage;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _errorCode = null;
    });
    final result = await _repository.listMyCompanies();
    if (!mounted) return;
    setState(() {
      _loading = false;
      switch (result) {
        case ApiOk(:final data):
          _companies = data;
        case ApiErr(:final code, :final message):
          _errorCode = code;
          _errorMessage = message;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Your companies'),
        actions: [
          IconButton(
            icon: const Icon(Icons.add),
            tooltip: 'New company',
            onPressed: () async {
              final created = await Navigator.of(context).push<bool>(
                MaterialPageRoute(builder: (_) => const CreateCompanyScreen()),
              );
              if (created == true) _load();
            },
          ),
        ],
      ),
      body: RefreshIndicator(onRefresh: _load, child: _buildBody()),
    );
  }

  Widget _buildBody() {
    if (_loading && _companies == null) {
      return const Center(child: CircularProgressIndicator());
    }

    // Offline state: this repository's ApiClient methods catch network
    // failures and surface them as ApiErr('NETWORK_ERROR', ...) — see
    // core/network/api_client.dart. No dedicated connectivity package is
    // used (a deliberate Module 3A scope simplification, documented in
    // the module's final report); this is the practical "you're offline"
    // signal available without adding one.
    if (_errorCode == 'NETWORK_ERROR') {
      return ListView(
        children: [
          const SizedBox(height: 80),
          const Icon(Icons.cloud_off, size: 48, color: Colors.grey),
          const SizedBox(height: 12),
          const Center(child: Text('You appear to be offline.')),
          const SizedBox(height: 12),
          Center(
            child: TextButton(onPressed: _load, child: const Text('Try again')),
          ),
        ],
      );
    }

    if (_errorCode != null) {
      return ListView(
        children: [
          const SizedBox(height: 80),
          Center(child: Text(_errorMessage ?? 'Something went wrong.', textAlign: TextAlign.center)),
          const SizedBox(height: 12),
          Center(child: TextButton(onPressed: _load, child: const Text('Try again'))),
        ],
      );
    }

    final companies = _companies ?? [];
    if (companies.isEmpty) {
      return ListView(
        children: [
          const SizedBox(height: 80),
          const Center(child: Text("You're not part of any company yet.")),
          const SizedBox(height: 12),
          Center(
            child: ElevatedButton(
              onPressed: () async {
                final created = await Navigator.of(context).push<bool>(
                  MaterialPageRoute(builder: (_) => const CreateCompanyScreen()),
                );
                if (created == true) _load();
              },
              child: const Text('Create your first company'),
            ),
          ),
        ],
      );
    }

    return ListView.builder(
      itemCount: companies.length,
      itemBuilder: (context, index) {
        final company = companies[index];
        return ListTile(
          title: Text(company.name),
          subtitle: Text(
            [company.industry, company.city, company.country].where((s) => s != null && s.isNotEmpty).join(' · '),
          ),
          trailing: Chip(
            label: Text('${company.memberCount}'),
            avatar: const Icon(Icons.people_outline, size: 16),
          ),
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => CompanyDashboardScreen(companyId: company.id)),
          ),
        );
      },
    );
  }
}
