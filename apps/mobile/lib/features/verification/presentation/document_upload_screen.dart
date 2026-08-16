import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../../../core/network/api_client.dart';
import '../data/verification_repository.dart';
import '../domain/verification.dart';

/// Document Upload — Module 3B. Mirrors
/// apps/web/src/app/companies/[id]/documents/page.tsx.
class DocumentUploadScreen extends StatefulWidget {
  const DocumentUploadScreen({super.key, required this.companyId});

  final String companyId;

  @override
  State<DocumentUploadScreen> createState() => _DocumentUploadScreenState();
}

class _DocumentUploadScreenState extends State<DocumentUploadScreen> {
  final _repository = VerificationRepository();
  List<VerificationDocument> _documents = [];
  String _documentType = 'gst_certificate';
  bool _loading = true;
  bool _uploading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final documents = await _repository.listDocuments(widget.companyId);
    if (!mounted) return;
    setState(() {
      _documents = documents;
      _loading = false;
    });
  }

  Future<void> _pickAndUpload() async {
    final picked = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['pdf', 'jpg', 'jpeg', 'png', 'webp'],
      withData: true,
    );
    if (picked == null || picked.files.isEmpty) return;
    final file = picked.files.single;
    final bytes = file.bytes;
    if (bytes == null) return;

    setState(() {
      _uploading = true;
      _error = null;
    });
    final result = await _repository.uploadDocument(widget.companyId, _documentType, bytes, file.name);
    if (!mounted) return;
    setState(() => _uploading = false);
    switch (result) {
      case ApiOk():
        _load();
      case ApiErr(:final message):
        setState(() => _error = message);
    }
  }

  Future<void> _delete(String documentId) async {
    final success = await _repository.deleteDocument(widget.companyId, documentId);
    if (!success) return;
    _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Documents')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text('Upload a document', style: TextStyle(fontWeight: FontWeight.bold)),
                          const SizedBox(height: 8),
                          DropdownButtonFormField<String>(
                            value: _documentType,
                            items: VerificationDocument.typeLabels.entries
                                .map((e) => DropdownMenuItem(value: e.key, child: Text(e.value)))
                                .toList(),
                            onChanged: (v) => setState(() => _documentType = v ?? _documentType),
                          ),
                          const SizedBox(height: 8),
                          ElevatedButton.icon(
                            onPressed: _uploading ? null : _pickAndUpload,
                            icon: const Icon(Icons.upload_file),
                            label: Text(_uploading ? 'Uploading…' : 'Choose file & upload'),
                          ),
                          const Text('PDF or image, up to 15 MB.', style: TextStyle(fontSize: 12, color: Colors.grey)),
                        ],
                      ),
                    ),
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 8),
                    Text(_error!, style: const TextStyle(color: Colors.red)),
                  ],
                  const SizedBox(height: 16),
                  if (_documents.isEmpty) const Center(child: Text('No documents uploaded yet.')),
                  ..._documents.map(
                    (doc) => Card(
                      child: ListTile(
                        title: Text(VerificationDocument.typeLabels[doc.documentType] ?? doc.documentType),
                        subtitle: Text('Status: ${doc.status} · v${doc.version}${doc.isExpired ? ' · expired' : ''}'),
                        trailing: IconButton(
                          icon: const Icon(Icons.delete_outline),
                          onPressed: () => _delete(doc.id),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
      ),
    );
  }
}
