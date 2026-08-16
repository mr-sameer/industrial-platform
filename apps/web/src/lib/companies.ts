/**
 * Company Core API client functions — Module 3A. Calls the FastAPI
 * service directly (not through a BFF route, unlike auth — see
 * docs/adr/0012-web-session-strategy.md for why auth needs the BFF split
 * and companies don't: these endpoints take a plain
 * `Authorization: Bearer` header, no ambient cookie is involved, so
 * there's no CSRF surface a BFF would need to protect). The access
 * token comes from AuthContext (in-memory), passed in explicitly by
 * every call site — this module never reads it itself.
 */
import type {
  ApiResponse,
  CompanyCreateRequest,
  CompanyDetail,
  CompanyMemberCreateRequest,
  CompanyMemberPublic,
  CompanyMemberUpdateRequest,
  CompanyPublic,
  CompanySearchPage,
  CompanySearchParams,
  CompanyUpdateRequest,
} from "@platform/shared-types";

import { apiFetch } from "@/lib/api-client";

function authHeaders(accessToken: string): HeadersInit {
  return { Authorization: `Bearer ${accessToken}` };
}

export function createCompany(payload: CompanyCreateRequest, accessToken: string) {
  return apiFetch<CompanyDetail>("/api/v1/companies", {
    method: "POST",
    headers: authHeaders(accessToken),
    body: JSON.stringify(payload),
  });
}

export function listMyCompanies(accessToken: string) {
  return apiFetch<CompanyPublic[]>("/api/v1/companies", { headers: authHeaders(accessToken) });
}

export function getCompany(companyId: string, accessToken: string) {
  return apiFetch<CompanyDetail>(`/api/v1/companies/${companyId}`, {
    headers: authHeaders(accessToken),
  });
}

export function updateCompany(companyId: string, payload: CompanyUpdateRequest, accessToken: string) {
  return apiFetch<CompanyDetail>(`/api/v1/companies/${companyId}`, {
    method: "PATCH",
    headers: authHeaders(accessToken),
    body: JSON.stringify(payload),
  });
}

export async function deleteCompany(companyId: string, accessToken: string): Promise<ApiResponse<null>> {
  return apiFetch<null>(`/api/v1/companies/${companyId}`, {
    method: "DELETE",
    headers: authHeaders(accessToken),
  });
}

export function getCompanyBySlug(slug: string) {
  return apiFetch<CompanyPublic>(`/api/v1/companies/slug/${encodeURIComponent(slug)}`);
}

export function searchCompanies(params: CompanySearchParams) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") query.set(key, String(value));
  }
  const qs = query.toString();
  return apiFetch<CompanySearchPage>(`/api/v1/companies/search${qs ? `?${qs}` : ""}`);
}

export function listMembers(companyId: string, accessToken: string) {
  return apiFetch<CompanyMemberPublic[]>(`/api/v1/companies/${companyId}/members`, {
    headers: authHeaders(accessToken),
  });
}

export function addMember(companyId: string, payload: CompanyMemberCreateRequest, accessToken: string) {
  return apiFetch<CompanyMemberPublic>(`/api/v1/companies/${companyId}/members`, {
    method: "POST",
    headers: authHeaders(accessToken),
    body: JSON.stringify(payload),
  });
}

export function updateMember(
  companyId: string,
  memberId: string,
  payload: CompanyMemberUpdateRequest,
  accessToken: string
) {
  return apiFetch<CompanyMemberPublic>(`/api/v1/companies/${companyId}/members/${memberId}`, {
    method: "PATCH",
    headers: authHeaders(accessToken),
    body: JSON.stringify(payload),
  });
}

export async function removeMember(
  companyId: string,
  memberId: string,
  accessToken: string
): Promise<ApiResponse<null>> {
  return apiFetch<null>(`/api/v1/companies/${companyId}/members/${memberId}`, {
    method: "DELETE",
    headers: authHeaders(accessToken),
  });
}
