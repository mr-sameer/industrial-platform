/**
 * Company Core types — Module 3A. Mirrors app/schemas/company.py exactly
 * (field names, optionality) so the web and mobile clients consume the
 * same shape the API actually returns, with no silent renaming at the
 * boundary. See docs/domain/03-core-entities.md for the business
 * definitions.
 */

export type CompanyRole = "owner" | "admin" | "editor" | "viewer";
export type CompanyMemberStatus = "pending" | "active" | "suspended";
export type CompanyStatus = "draft" | "active" | "suspended" | "archived";
export type CompanySize = "1-10" | "11-50" | "51-200" | "201-1000" | "1000+";
export type VerificationStatus = "unverified" | "verified";

export interface CompanyCreateRequest {
  name: string;
  legal_name: string;
  description?: string | null;
  industry?: string | null;
  website?: string | null;
  email?: string | null;
  phone?: string | null;
  year_established?: number | null;
  company_size?: CompanySize | null;
  gst_number?: string | null;
  country?: string | null;
  state?: string | null;
  city?: string | null;
}

export type CompanyUpdateRequest = Partial<CompanyCreateRequest>;

export interface CompanyPublic {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  industry: string | null;
  website: string | null;
  country: string | null;
  city: string | null;
  verification_status: VerificationStatus;
  member_count: number;
  created_at: string;
}

export interface CompanyDetail {
  id: string;
  name: string;
  legal_name: string;
  slug: string;
  description: string | null;
  industry: string | null;
  website: string | null;
  email: string | null;
  phone: string | null;
  year_established: number | null;
  company_size: CompanySize | null;
  gst_number: string | null;
  country: string | null;
  state: string | null;
  city: string | null;
  status: CompanyStatus;
  verification_status: VerificationStatus;
  member_count: number;
  my_role: CompanyRole;
  created_at: string;
  updated_at: string;
}

export interface CompanySearchResult {
  id: string;
  name: string;
  slug: string;
  industry: string | null;
  country: string | null;
  city: string | null;
  verification_status: VerificationStatus;
}

export interface CompanySearchPage {
  items: CompanySearchResult[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface CompanySearchParams {
  name?: string;
  industry?: string;
  country?: string;
  city?: string;
  page?: number;
  page_size?: number;
  sort_by?: "name" | "created_at" | "city" | "country";
  sort_order?: "asc" | "desc";
}

export interface CompanyMemberCreateRequest {
  user_id: string;
  role: Exclude<CompanyRole, "owner">;
}

export interface CompanyMemberUpdateRequest {
  role?: CompanyRole;
  status?: CompanyMemberStatus;
}

export interface CompanyMemberPublic {
  id: string;
  user_id: string;
  full_name: string;
  email: string;
  role: CompanyRole;
  status: CompanyMemberStatus;
  joined_at: string | null;
  created_at: string;
}
