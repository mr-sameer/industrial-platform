import 'package:flutter/material.dart';

import '../../../core/network/api_client.dart';
import '../../verification/presentation/verification_dashboard_screen.dart';
import '../data/company_repository.dart';
import '../domain/company.dart';
import 'edit_company_screen.dart';

/// Company Dashboard — Module 3A. Displays company name, logo
/// placeholder, industry, location, member count, verification status,
/// and created date, per this module's brief — mirrors
/// apps/web/src/app/companies/[id]/page.tsx.
class CompanyDashboardScreen extends StatefulWidget {
  const CompanyDashboardScreen({super.key, required this.companyId});

  final String companyId;

  @override
  State<CompanyDashboardScreen> createState() => _CompanyDashboardScreenState();
}

class _CompanyDashboardScreenState extends State<CompanyDashboardScreen> {
  final _repository = CompanyRepository();
  CompanyDetail? _company;
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
    final result = await _repository.getCompany(widget.companyId);
    if (!mounted) return;
    setState(() {
      _loading = false;
      switch (result) {
        case ApiOk(:final data):
          _company = data;
        case ApiErr(:final code, :final message):
          _errorCode = code;
          _errorMessage = message;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final company = _company;
    return Scaffold(
      appBar: AppBar(
        title: Text(company?.name ?? 'Company'),
        actions: [
          if (company != null)
            IconButton(
              icon: const Icon(Icons.verified_outlined),
              tooltip: 'Verification',
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => VerificationDashboardScreen(companyId: company.id)),
              ),
            ),
          if (company != null && company.canEdit)
            IconButton(
              icon: const Icon(Icons.settings),
              tooltip: 'Settings',
              onPressed: () async {
                final updated = await Navigator.of(context).push<bool>(
                  MaterialPageRoute(builder: (_) => EditCompanyScreen(company: company)),
                );
                if (updated == true) _load();
              },
            ),
        ],
      ),
      body: RefreshIndicator(onRefresh: _load, child: _buildBody()),
    );
  }

  Widget _buildBody() {
    if (_loading && _company == null) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_errorCode == 'NETWORK_ERROR') {
      return ListView(
        children: [
          const SizedBox(height: 80),
          const Icon(Icons.cloud_off, size: 48, color: Colors.grey),
          const Center(child: Text("You're offline.")),
          Center(child: TextButton(onPressed: _load, child: const Text('Try again'))),
        ],
      );
    }
    if (_errorCode != null) {
      return ListView(
        children: [
          const SizedBox(height: 80),
          Center(child: Text(_errorMessage ?? 'Something went wrong.')),
          Center(child: TextButton(onPressed: _load, child: const Text('Try again'))),
        ],
      );
    }

    final company = _company;
    if (company == null) return const SizedBox.shrink();

    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Row(
          children: [
            CircleAvatar(
              radius: 32,
              backgroundColor: Colors.grey.shade200,
              child: Text(
                company.name.isNotEmpty ? company.name[0].toUpperCase() : '?',
                style: TextStyle(fontSize: 24, color: Colors.grey.shade600, fontWeight: FontWeight.bold),
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(company.name, style: Theme.of(context).textTheme.titleLarge),
                  Text(company.industry ?? 'Industry not set', style: Theme.of(context).textTheme.bodySmall),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: 20),
        _InfoCard(
          label: 'Location',
          value: [company.city, company.state, company.country].where((s) => s != null && s!.isNotEmpty).join(', '),
        ),
        _InfoCard(label: 'Members', value: '${company.memberCount}'),
        _InfoCard(
          label: 'Verification status',
          value: company.verificationStatus == 'verified' ? 'Verified' : 'Unverified',
          valueColor: company.verificationStatus == 'verified' ? Colors.green.shade700 : Colors.grey.shade600,
        ),
        _InfoCard(label: 'Created', value: DateTime.tryParse(company.createdAt)?.toLocal().toString().split(' ').first ?? company.createdAt),
        if (company.description != null && company.description!.isNotEmpty) ...[
          const SizedBox(height: 12),
          Text('About', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 4),
          Text(company.description!),
        ],
        const SizedBox(height: 20),
        Text('Your role here: ${company.myRole}', style: Theme.of(context).textTheme.bodySmall),
      ],
    );
  }
}

class _InfoCard extends StatelessWidget {
  const _InfoCard({required this.label, required this.value, this.valueColor});

  final String label;
  final String value;
  final Color? valueColor;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: ListTile(
        title: Text(label, style: Theme.of(context).textTheme.bodySmall),
        subtitle: Text(
          value.isEmpty ? 'Not set' : value,
          style: TextStyle(color: valueColor, fontWeight: FontWeight.w600),
        ),
      ),
    );
  }
}
