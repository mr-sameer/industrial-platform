/// Mirrors app/schemas/company_verification.py and
/// packages/shared-types/src/company-verification.ts — Module 3B.
library;

class MissingRequirement {
  final String key;
  final String label;
  final int weight;
  final String level;

  const MissingRequirement({
    required this.key,
    required this.label,
    required this.weight,
    required this.level,
  });

  factory MissingRequirement.fromJson(Map<String, dynamic> json) => MissingRequirement(
        key: json['key'] as String,
        label: json['label'] as String,
        weight: json['weight'] as int,
        level: json['level'] as String,
      );
}

class VerificationScore {
  final int percentage;
  final String level;
  final int readinessScore;
  final String? nextLevel;
  final List<MissingRequirement> missingRequirements;
  final List<String> satisfiedRequirementKeys;

  const VerificationScore({
    required this.percentage,
    required this.level,
    required this.readinessScore,
    required this.nextLevel,
    required this.missingRequirements,
    required this.satisfiedRequirementKeys,
  });

  factory VerificationScore.fromJson(Map<String, dynamic> json) => VerificationScore(
        percentage: json['percentage'] as int,
        level: json['level'] as String,
        readinessScore: json['readiness_score'] as int,
        nextLevel: json['next_level'] as String?,
        missingRequirements: ((json['missing_requirements'] as List?) ?? [])
            .map((e) => MissingRequirement.fromJson(e as Map<String, dynamic>))
            .toList(),
        satisfiedRequirementKeys:
            ((json['satisfied_requirement_keys'] as List?) ?? []).map((e) => e as String).toList(),
      );

  static const Map<String, String> levelLabels = {
    'unverified': 'Unverified',
    'email_verified': 'Email Verified',
    'business_verified': 'Business Verified',
    'factory_verified': 'Factory Verified',
    'premium_verified': 'Premium Verified',
  };
}

class CompanyBranding {
  final String? logoUrl;
  final String? logoThumbnailUrl;
  final String? coverImageUrl;

  const CompanyBranding({required this.logoUrl, required this.logoThumbnailUrl, required this.coverImageUrl});

  factory CompanyBranding.fromJson(Map<String, dynamic> json) => CompanyBranding(
        logoUrl: json['logo_url'] as String?,
        logoThumbnailUrl: json['logo_thumbnail_url'] as String?,
        coverImageUrl: json['cover_image_url'] as String?,
      );
}

class VerificationDocument {
  final String id;
  final String documentType;
  final String fileType;
  final String fileUrl;
  final String status;
  final int version;
  final bool isExpired;

  const VerificationDocument({
    required this.id,
    required this.documentType,
    required this.fileType,
    required this.fileUrl,
    required this.status,
    required this.version,
    required this.isExpired,
  });

  factory VerificationDocument.fromJson(Map<String, dynamic> json) => VerificationDocument(
        id: json['id'] as String,
        documentType: json['document_type'] as String,
        fileType: json['file_type'] as String,
        fileUrl: json['file_url'] as String,
        status: json['status'] as String,
        version: json['version'] as int,
        isExpired: json['is_expired'] as bool,
      );

  static const Map<String, String> typeLabels = {
    'gst_certificate': 'GST Certificate',
    'msme': 'MSME Certificate',
    'iso': 'ISO Certificate',
    'ce': 'CE Certificate',
    'bis': 'BIS Certificate',
    'factory_license': 'Factory License',
    'import_export_code': 'Import Export Code',
    'business_registration': 'Business Registration',
    'other': 'Other',
  };
}
