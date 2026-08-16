/**
 * Company Verification & Industrial Identity types — Module 3B. Mirrors
 * app/schemas/company_verification.py exactly. See
 * docs/adr/0029-module-3b-verification-and-identity.md.
 */

export type LegalEntityType =
  | "private_limited"
  | "llp"
  | "proprietorship"
  | "partnership"
  | "public_limited"
  | "government"
  | "ngo"
  | "other";

export type BusinessType = "manufacturer" | "trader" | "both";
export type SocialPlatform = "linkedin" | "youtube" | "facebook" | "instagram" | "x";
export type DocumentType =
  | "gst_certificate"
  | "msme"
  | "iso"
  | "ce"
  | "bis"
  | "factory_license"
  | "import_export_code"
  | "business_registration"
  | "other";
export type DocumentFileType = "pdf" | "image";
export type DocumentStatus = "pending" | "verified" | "rejected" | "expired";
export type VerificationLevel =
  | "unverified"
  | "email_verified"
  | "business_verified"
  | "factory_verified"
  | "premium_verified";

export interface BusinessInfoUpdateRequest {
  legal_entity_type?: LegalEntityType;
  business_type?: BusinessType;
  export_capable?: boolean;
  gst_number?: string;
  pan?: string;
  cin?: string;
  msme_number?: string;
  iec_number?: string;
  tax_registration?: string;
  business_registration_date?: string; // ISO date
  short_description?: string;
  description?: string;
  mission?: string;
  vision?: string;
  core_values?: string[];
  capabilities?: string[];
  manufacturing_expertise?: string[];
  secondary_industries?: string[];
  product_categories?: string[];
  manufacturing_categories?: string[];
  export_categories?: string[];
  naics_sic_code?: string;
}

export interface SocialLinkPublic {
  platform: SocialPlatform;
  url: string;
}

export interface VerificationDocumentPublic {
  id: string;
  document_type: DocumentType;
  file_type: DocumentFileType;
  file_url: string;
  status: DocumentStatus;
  uploaded_at: string;
  verified_at: string | null;
  expiry_date: string | null;
  version: number;
  is_expired: boolean;
}

export interface MissingRequirementPublic {
  key: string;
  label: string;
  weight: number;
  level: VerificationLevel;
}

export interface VerificationScorePublic {
  percentage: number;
  level: VerificationLevel;
  readiness_score: number;
  next_level: VerificationLevel | null;
  missing_requirements: MissingRequirementPublic[];
  satisfied_requirement_keys: string[];
}

export interface CompanyBrandingPublic {
  logo_url: string | null;
  logo_thumbnail_url: string | null;
  cover_image_url: string | null;
}

export const VERIFICATION_LEVEL_LABELS: Record<VerificationLevel, string> = {
  unverified: "Unverified",
  email_verified: "Email Verified",
  business_verified: "Business Verified",
  factory_verified: "Factory Verified",
  premium_verified: "Premium Verified",
};

export const DOCUMENT_TYPE_LABELS: Record<DocumentType, string> = {
  gst_certificate: "GST Certificate",
  msme: "MSME Certificate",
  iso: "ISO Certificate",
  ce: "CE Certificate",
  bis: "BIS Certificate",
  factory_license: "Factory License",
  import_export_code: "Import Export Code",
  business_registration: "Business Registration",
  other: "Other",
};
