/// Mirrors app/schemas/company.py (CompanyPublic/CompanyDetail) and
/// packages/shared-types/src/company.ts — Module 3A. Kept as two
/// distinct classes (not one with nullable legal-only fields) because
/// that's exactly how the API itself distinguishes them: CompanyPublic
/// (search/public profile) never includes legal_name/gst_number/email/
/// phone at all, not just as null.
library;

class CompanySummary {
  final String id;
  final String name;
  final String slug;
  final String? industry;
  final String? country;
  final String? city;
  final String verificationStatus;
  final int memberCount;

  const CompanySummary({
    required this.id,
    required this.name,
    required this.slug,
    required this.industry,
    required this.country,
    required this.city,
    required this.verificationStatus,
    required this.memberCount,
  });

  factory CompanySummary.fromJson(Map<String, dynamic> json) => CompanySummary(
        id: json['id'] as String,
        name: json['name'] as String,
        slug: json['slug'] as String,
        industry: json['industry'] as String?,
        country: json['country'] as String?,
        city: json['city'] as String?,
        verificationStatus: json['verification_status'] as String,
        memberCount: json['member_count'] as int,
      );
}

class CompanyDetail {
  final String id;
  final String name;
  final String legalName;
  final String slug;
  final String? description;
  final String? industry;
  final String? website;
  final String? email;
  final String? phone;
  final int? yearEstablished;
  final String? companySize;
  final String? country;
  final String? state;
  final String? city;
  final String status;
  final String verificationStatus;
  final int memberCount;
  final String myRole;
  final String createdAt;

  const CompanyDetail({
    required this.id,
    required this.name,
    required this.legalName,
    required this.slug,
    required this.description,
    required this.industry,
    required this.website,
    required this.email,
    required this.phone,
    required this.yearEstablished,
    required this.companySize,
    required this.country,
    required this.state,
    required this.city,
    required this.status,
    required this.verificationStatus,
    required this.memberCount,
    required this.myRole,
    required this.createdAt,
  });

  factory CompanyDetail.fromJson(Map<String, dynamic> json) => CompanyDetail(
        id: json['id'] as String,
        name: json['name'] as String,
        legalName: json['legal_name'] as String,
        slug: json['slug'] as String,
        description: json['description'] as String?,
        industry: json['industry'] as String?,
        website: json['website'] as String?,
        email: json['email'] as String?,
        phone: json['phone'] as String?,
        yearEstablished: json['year_established'] as int?,
        companySize: json['company_size'] as String?,
        country: json['country'] as String?,
        state: json['state'] as String?,
        city: json['city'] as String?,
        status: json['status'] as String,
        verificationStatus: json['verification_status'] as String,
        memberCount: json['member_count'] as int,
        myRole: json['my_role'] as String,
        createdAt: json['created_at'] as String,
      );

  /// Editor/Admin/Owner can edit; Viewer cannot. Mirrors the API's own
  /// authorization (app.core.company_authorization) — this is a display
  /// convenience only, never a substitute for the server-side check.
  bool get canEdit => myRole == 'owner' || myRole == 'admin' || myRole == 'editor';
  bool get canDelete => myRole == 'owner';
}
