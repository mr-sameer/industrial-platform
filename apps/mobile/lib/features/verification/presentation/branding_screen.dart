import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../../../core/network/api_client.dart';
import '../data/verification_repository.dart';
import '../domain/verification.dart';

/// Branding — Module 3B. Mirrors apps/web/src/app/companies/[id]/branding/page.tsx.
class BrandingScreen extends StatefulWidget {
  const BrandingScreen({super.key, required this.companyId});

  final String companyId;

  @override
  State<BrandingScreen> createState() => _BrandingScreenState();
}

class _BrandingScreenState extends State<BrandingScreen> {
  final _repository = VerificationRepository();
  CompanyBranding? _branding;
  bool _loading = true;
  bool _logoUploading = false;
  bool _coverUploading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final result = await _repository.getBranding(widget.companyId);
    if (!mounted) return;
    switch (result) {
      case ApiOk(:final data):
        setState(() {
          _branding = data;
          _loading = false;
        });
      case ApiErr(:final message):
        setState(() {
          _error = message;
          _loading = false;
        });
    }
  }

  Future<void> _pickAndUploadLogo() async {
    final picked = await FilePicker.platform.pickFiles(type: FileType.image, withData: true);
    if (picked == null || picked.files.isEmpty) return;
    final file = picked.files.first;
    if (file.bytes == null) return;
    setState(() {
      _logoUploading = true;
      _error = null;
    });
    final result = await _repository.uploadLogo(widget.companyId, file.bytes!, file.name);
    if (!mounted) return;
    setState(() => _logoUploading = false);
    switch (result) {
      case ApiOk(:final data):
        setState(() => _branding = data);
      case ApiErr(:final message):
        setState(() => _error = message);
    }
  }

  Future<void> _pickAndUploadCover() async {
    final picked = await FilePicker.platform.pickFiles(type: FileType.image, withData: true);
    if (picked == null || picked.files.isEmpty) return;
    final file = picked.files.first;
    if (file.bytes == null) return;
    setState(() {
      _coverUploading = true;
      _error = null;
    });
    final result = await _repository.uploadCoverImage(widget.companyId, file.bytes!, file.name);
    if (!mounted) return;
    setState(() => _coverUploading = false);
    switch (result) {
      case ApiOk(:final data):
        setState(() => _branding = data);
      case ApiErr(:final message):
        setState(() => _error = message);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return Scaffold(
        appBar: AppBar(title: const Text('Branding')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }
    return Scaffold(
      appBar: AppBar(title: const Text('Branding')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (_error != null) ...[
            Text(_error!, style: const TextStyle(color: Colors.red)),
            const SizedBox(height: 12),
          ],
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Logo', style: TextStyle(fontWeight: FontWeight.bold)),
                  const SizedBox(height: 8),
                  if (_branding?.logoThumbnailUrl != null)
                    ClipRRect(
                      borderRadius: BorderRadius.circular(8),
                      child: Image.network(_branding!.logoThumbnailUrl!, width: 96, height: 96, fit: BoxFit.cover),
                    ),
                  const SizedBox(height: 8),
                  ElevatedButton(
                    onPressed: _logoUploading ? null : _pickAndUploadLogo,
                    child: Text(_logoUploading ? 'Uploading…' : 'Choose & upload logo'),
                  ),
                  const Text(
                    'JPEG, PNG, or WEBP, up to 5 MB. A 256×256 thumbnail is generated automatically.',
                    style: TextStyle(fontSize: 12, color: Colors.grey),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Cover image', style: TextStyle(fontWeight: FontWeight.bold)),
                  const SizedBox(height: 8),
                  if (_branding?.coverImageUrl != null)
                    ClipRRect(
                      borderRadius: BorderRadius.circular(8),
                      child: Image.network(_branding!.coverImageUrl!, height: 100, fit: BoxFit.cover),
                    ),
                  const SizedBox(height: 8),
                  ElevatedButton(
                    onPressed: _coverUploading ? null : _pickAndUploadCover,
                    child: Text(_coverUploading ? 'Uploading…' : 'Choose & upload cover image'),
                  ),
                  const Text(
                    'JPEG, PNG, or WEBP, up to 10 MB. Responsive variants are generated automatically.',
                    style: TextStyle(fontSize: 12, color: Colors.grey),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
