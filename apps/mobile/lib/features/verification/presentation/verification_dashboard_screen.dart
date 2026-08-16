import 'package:flutter/material.dart';

import '../../../core/network/api_client.dart';
import '../data/verification_repository.dart';
import '../domain/verification.dart';
import 'branding_screen.dart';
import 'business_info_screen.dart';
import 'document_upload_screen.dart';
import 'verification_progress_widget.dart';

/// Verification Dashboard — Module 3B. Mirrors
/// apps/web/src/app/companies/[id]/verification/page.tsx.
class VerificationDashboardScreen extends StatefulWidget {
  const VerificationDashboardScreen({super.key, required this.companyId});

  final String companyId;

  @override
  State<VerificationDashboardScreen> createState() => _VerificationDashboardScreenState();
}

class _VerificationDashboardScreenState extends State<VerificationDashboardScreen> {
  final _repository = VerificationRepository();
  VerificationScore? _score;
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
    final result = await _repository.getVerification(widget.companyId);
    if (!mounted) return;
    setState(() {
      _loading = false;
      switch (result) {
        case ApiOk(:final data):
          _score = data;
        case ApiErr(:final code, :final message):
          _errorCode = code;
          _errorMessage = message;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Verification')),
      body: RefreshIndicator(onRefresh: _load, child: _buildBody()),
    );
  }

  Widget _buildBody() {
    if (_loading && _score == null) {
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

    final score = _score;
    if (score == null) return const SizedBox.shrink();

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        VerificationProgressWidget(score: score),
        const SizedBox(height: 16),
        _NavCard(
          icon: Icons.business_outlined,
          title: 'Business Information',
          subtitle: 'Legal entity, registration numbers, description',
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => BusinessInfoScreen(companyId: widget.companyId)),
          ),
        ),
        _NavCard(
          icon: Icons.description_outlined,
          title: 'Documents',
          subtitle: 'Certificates and registration evidence',
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => DocumentUploadScreen(companyId: widget.companyId)),
          ),
        ),
        _NavCard(
          icon: Icons.image_outlined,
          title: 'Branding',
          subtitle: 'Logo and cover image',
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => BrandingScreen(companyId: widget.companyId)),
          ),
        ),
      ],
    );
  }
}

class _NavCard extends StatelessWidget {
  const _NavCard({required this.icon, required this.title, required this.subtitle, required this.onTap});

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: ListTile(
        leading: Icon(icon),
        title: Text(title),
        subtitle: Text(subtitle),
        trailing: const Icon(Icons.chevron_right),
        onTap: onTap,
      ),
    );
  }
}
