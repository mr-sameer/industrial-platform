import 'package:flutter/material.dart';

import '../../../core/network/api_client.dart';
import '../data/verification_repository.dart';

/// Business Information — Module 3B. Mirrors
/// apps/web/src/app/companies/[id]/business-info/page.tsx (a subset of
/// fields, matching this screen's more constrained form-factor).
class BusinessInfoScreen extends StatefulWidget {
  const BusinessInfoScreen({super.key, required this.companyId});

  final String companyId;

  @override
  State<BusinessInfoScreen> createState() => _BusinessInfoScreenState();
}

class _BusinessInfoScreenState extends State<BusinessInfoScreen> {
  final _repository = VerificationRepository();
  final _gstController = TextEditingController();
  final _panController = TextEditingController();
  final _shortDescriptionController = TextEditingController();
  String? _legalEntityType;
  String? _businessType;
  bool _exportCapable = false;

  bool _loading = true;
  bool _saving = false;
  String? _error;

  static const _legalEntityTypes = [
    'private_limited',
    'llp',
    'proprietorship',
    'partnership',
    'public_limited',
    'government',
    'ngo',
    'other',
  ];
  static const _businessTypes = ['manufacturer', 'trader', 'both'];

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _gstController.dispose();
    _panController.dispose();
    _shortDescriptionController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final result = await _repository.getBusinessInfo(widget.companyId);
    if (!mounted) return;
    switch (result) {
      case ApiOk(:final data):
        setState(() {
          _legalEntityType = data['legal_entity_type'] as String?;
          _businessType = data['business_type'] as String?;
          _exportCapable = (data['export_capable'] as bool?) ?? false;
          _gstController.text = (data['gst_number'] as String?) ?? '';
          _panController.text = (data['pan'] as String?) ?? '';
          _shortDescriptionController.text = (data['short_description'] as String?) ?? '';
          _loading = false;
        });
      case ApiErr(:final message):
        setState(() {
          _error = message;
          _loading = false;
        });
    }
  }

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    final payload = <String, dynamic>{
      if (_legalEntityType != null) 'legal_entity_type': _legalEntityType,
      if (_businessType != null) 'business_type': _businessType,
      'export_capable': _exportCapable,
      if (_gstController.text.trim().isNotEmpty) 'gst_number': _gstController.text.trim(),
      if (_panController.text.trim().isNotEmpty) 'pan': _panController.text.trim(),
      if (_shortDescriptionController.text.trim().isNotEmpty)
        'short_description': _shortDescriptionController.text.trim(),
    };
    final result = await _repository.updateBusinessInfo(widget.companyId, payload);
    if (!mounted) return;
    setState(() => _saving = false);
    switch (result) {
      case ApiOk():
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Saved')));
      case ApiErr(:final message):
        setState(() => _error = message);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return Scaffold(
        appBar: AppBar(title: const Text('Business Information')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }
    return Scaffold(
      appBar: AppBar(title: const Text('Business Information')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          DropdownButtonFormField<String>(
            value: _legalEntityType,
            decoration: const InputDecoration(labelText: 'Legal entity type'),
            items: _legalEntityTypes
                .map((t) => DropdownMenuItem(value: t, child: Text(t.replaceAll('_', ' '))))
                .toList(),
            onChanged: (v) => setState(() => _legalEntityType = v),
          ),
          const SizedBox(height: 12),
          DropdownButtonFormField<String>(
            value: _businessType,
            decoration: const InputDecoration(labelText: 'Manufacturer or trader?'),
            items: _businessTypes.map((t) => DropdownMenuItem(value: t, child: Text(t))).toList(),
            onChanged: (v) => setState(() => _businessType = v),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Export capable'),
            value: _exportCapable,
            onChanged: (v) => setState(() => _exportCapable = v),
          ),
          const SizedBox(height: 4),
          TextField(controller: _gstController, decoration: const InputDecoration(labelText: 'GSTIN')),
          const SizedBox(height: 12),
          TextField(controller: _panController, decoration: const InputDecoration(labelText: 'PAN')),
          const SizedBox(height: 12),
          TextField(
            controller: _shortDescriptionController,
            maxLength: 500,
            decoration: const InputDecoration(labelText: 'Short description'),
          ),
          if (_error != null) ...[
            const SizedBox(height: 8),
            Text(_error!, style: const TextStyle(color: Colors.red)),
          ],
          const SizedBox(height: 16),
          ElevatedButton(
            onPressed: _saving ? null : _save,
            child: Text(_saving ? 'Saving…' : 'Save changes'),
          ),
        ],
      ),
    );
  }
}
