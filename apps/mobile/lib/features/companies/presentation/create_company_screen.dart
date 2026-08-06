import 'package:flutter/material.dart';

import '../../../core/network/api_client.dart';
import '../data/company_repository.dart';

/// "Create Company" — Module 3A. Pops with `true` on success so the
/// caller (CompanyListScreen) knows to refresh.
class CreateCompanyScreen extends StatefulWidget {
  const CreateCompanyScreen({super.key});

  @override
  State<CreateCompanyScreen> createState() => _CreateCompanyScreenState();
}

class _CreateCompanyScreenState extends State<CreateCompanyScreen> {
  final _formKey = GlobalKey<FormState>();
  final _repository = CompanyRepository();

  final _nameController = TextEditingController();
  final _legalNameController = TextEditingController();
  final _descriptionController = TextEditingController();
  final _industryController = TextEditingController();
  final _websiteController = TextEditingController();
  final _countryController = TextEditingController();
  final _stateController = TextEditingController();
  final _cityController = TextEditingController();

  String? _error;
  bool _submitting = false;

  @override
  void dispose() {
    _nameController.dispose();
    _legalNameController.dispose();
    _descriptionController.dispose();
    _industryController.dispose();
    _websiteController.dispose();
    _countryController.dispose();
    _stateController.dispose();
    _cityController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _submitting = true;
      _error = null;
    });

    final payload = <String, dynamic>{
      'name': _nameController.text.trim(),
      'legal_name': _legalNameController.text.trim(),
      if (_descriptionController.text.trim().isNotEmpty) 'description': _descriptionController.text.trim(),
      if (_industryController.text.trim().isNotEmpty) 'industry': _industryController.text.trim(),
      if (_websiteController.text.trim().isNotEmpty) 'website': _websiteController.text.trim(),
      if (_countryController.text.trim().isNotEmpty) 'country': _countryController.text.trim(),
      if (_stateController.text.trim().isNotEmpty) 'state': _stateController.text.trim(),
      if (_cityController.text.trim().isNotEmpty) 'city': _cityController.text.trim(),
    };

    final result = await _repository.createCompany(payload);
    if (!mounted) return;
    setState(() => _submitting = false);

    switch (result) {
      case ApiOk():
        Navigator.of(context).pop(true);
      case ApiErr(:final message):
        setState(() => _error = message);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Create a company')),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            TextFormField(
              controller: _nameController,
              decoration: const InputDecoration(labelText: 'Company name *'),
              validator: (v) => (v == null || v.trim().isEmpty) ? 'Required' : null,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _legalNameController,
              decoration: const InputDecoration(labelText: 'Legal name *'),
              validator: (v) => (v == null || v.trim().isEmpty) ? 'Required' : null,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _descriptionController,
              decoration: const InputDecoration(labelText: 'Description'),
              maxLines: 3,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _industryController,
              decoration: const InputDecoration(labelText: 'Industry'),
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _websiteController,
              decoration: const InputDecoration(labelText: 'Website'),
              keyboardType: TextInputType.url,
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: TextFormField(
                    controller: _countryController,
                    decoration: const InputDecoration(labelText: 'Country'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: TextFormField(
                    controller: _stateController,
                    decoration: const InputDecoration(labelText: 'State'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _cityController,
              decoration: const InputDecoration(labelText: 'City'),
            ),
            if (_error != null) ...[
              const SizedBox(height: 16),
              Text(_error!, style: const TextStyle(color: Colors.red)),
            ],
            const SizedBox(height: 24),
            ElevatedButton(
              onPressed: _submitting ? null : _submit,
              child: Text(_submitting ? 'Creating…' : 'Create company'),
            ),
          ],
        ),
      ),
    );
  }
}
