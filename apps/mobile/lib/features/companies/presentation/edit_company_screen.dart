import 'package:flutter/material.dart';

import '../../../core/network/api_client.dart';
import '../data/company_repository.dart';
import '../domain/company.dart';

/// "Edit Company" — Module 3A's Company Settings, mobile side. Mirrors
/// apps/web/src/app/companies/[id]/settings/page.tsx: edit profile,
/// delete company, and a transfer-ownership placeholder (the real
/// mechanism already exists at the API level — see
/// docs/adr/0024-ownership-transfer-mechanism.md — a full member-picker
/// UI for it is out of Module 3A's scope on every client, not just web).
class EditCompanyScreen extends StatefulWidget {
  const EditCompanyScreen({super.key, required this.company});

  final CompanyDetail company;

  @override
  State<EditCompanyScreen> createState() => _EditCompanyScreenState();
}

class _EditCompanyScreenState extends State<EditCompanyScreen> {
  final _repository = CompanyRepository();
  late final TextEditingController _nameController;
  late final TextEditingController _legalNameController;
  late final TextEditingController _descriptionController;
  late final TextEditingController _industryController;

  String? _error;
  bool _saving = false;
  bool _deleting = false;

  bool get _canEditLegalName => widget.company.myRole == 'owner' || widget.company.myRole == 'admin';

  @override
  void initState() {
    super.initState();
    _nameController = TextEditingController(text: widget.company.name);
    _legalNameController = TextEditingController(text: widget.company.legalName);
    _descriptionController = TextEditingController(text: widget.company.description ?? '');
    _industryController = TextEditingController(text: widget.company.industry ?? '');
  }

  @override
  void dispose() {
    _nameController.dispose();
    _legalNameController.dispose();
    _descriptionController.dispose();
    _industryController.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    final payload = <String, dynamic>{
      'name': _nameController.text.trim(),
      'description': _descriptionController.text.trim(),
      'industry': _industryController.text.trim(),
      if (_canEditLegalName) 'legal_name': _legalNameController.text.trim(),
    };
    final result = await _repository.updateCompany(widget.company.id, payload);
    if (!mounted) return;
    setState(() => _saving = false);
    switch (result) {
      case ApiOk():
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Saved')));
        Navigator.of(context).pop(true);
      case ApiErr(:final message):
        setState(() => _error = message);
    }
  }

  Future<void> _confirmDelete() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete company?'),
        content: Text(
          'This archives "${widget.company.name}". It will no longer appear in search or be accessible '
          'via its public profile. This cannot be undone from the app.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(context).pop(false), child: const Text('Cancel')),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Delete', style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    setState(() => _deleting = true);
    final success = await _repository.deleteCompany(widget.company.id);
    if (!mounted) return;
    setState(() => _deleting = false);
    if (success) {
      Navigator.of(context)
        ..pop(true) // close edit screen
        ..pop(true); // close dashboard, back to the company list
    } else {
      setState(() => _error = 'Could not delete this company.');
    }
  }

  @override
  Widget build(BuildContext context) {
    final canEdit = widget.company.canEdit;
    final canDelete = widget.company.canDelete;

    return Scaffold(
      appBar: AppBar(title: const Text('Company settings')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          if (!canEdit)
            const Padding(
              padding: EdgeInsets.only(bottom: 16),
              child: Text('You have view-only access to this company.'),
            ),
          TextField(
            controller: _nameController,
            enabled: canEdit,
            decoration: const InputDecoration(labelText: 'Company name'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _legalNameController,
            enabled: canEdit && _canEditLegalName,
            decoration: InputDecoration(
              labelText: 'Legal name',
              helperText: !_canEditLegalName ? 'Admin/Owner only' : null,
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _descriptionController,
            enabled: canEdit,
            maxLines: 3,
            decoration: const InputDecoration(labelText: 'Description'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _industryController,
            enabled: canEdit,
            decoration: const InputDecoration(labelText: 'Industry'),
          ),
          if (_error != null) ...[
            const SizedBox(height: 12),
            Text(_error!, style: const TextStyle(color: Colors.red)),
          ],
          if (canEdit) ...[
            const SizedBox(height: 20),
            ElevatedButton(
              onPressed: _saving ? null : _save,
              child: Text(_saving ? 'Saving…' : 'Save changes'),
            ),
          ],
          const Divider(height: 48),
          Text('Transfer ownership', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          const Text(
            'Ownership transfer is available via the API. A full member-picker UI for this is out of '
            "Module 3A's scope on mobile — this placeholder confirms Settings has a home for it.",
          ),
          const SizedBox(height: 8),
          const OutlinedButton(onPressed: null, child: Text('Transfer ownership (coming soon)')),
          if (canDelete) ...[
            const Divider(height: 48),
            Text('Danger zone', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            ElevatedButton(
              style: ElevatedButton.styleFrom(backgroundColor: Colors.red.shade700, foregroundColor: Colors.white),
              onPressed: _deleting ? null : _confirmDelete,
              child: Text(_deleting ? 'Deleting…' : 'Delete company'),
            ),
          ],
        ],
      ),
    );
  }
}
