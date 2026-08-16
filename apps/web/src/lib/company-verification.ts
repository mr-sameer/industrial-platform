/**
 * Company Verification & Industrial Identity API client — Module 3B.
 * A new file (not modifying apps/web/src/lib/companies.ts, Module 3A) —
 * same direct-to-FastAPI pattern (see that file's docstring for why no
 * BFF is needed here).
 *
 * File uploads use a separate `uploadFetch` helper, not the shared
 * `apiFetch` — `apiFetch` always sets `Content-Type: application/json`,
 * which breaks multipart/form-data uploads (the browser must set that
 * header itself, including the multipart boundary, when the body is a
 * FormData instance).
 */
import type {
  ApiResponse,
  BusinessInfoUpdateRequest,
  CompanyBrandingPublic,
  DocumentType,
  SocialLinkPublic,
  SocialPlatform,
  VerificationDocumentPublic,
  VerificationScorePublic,
} from "@platform/shared-types";

import { env } from "@/config/env";
import { apiFetch } from "@/lib/api-client";
import { logger } from "@/lib/logger";

function authHeaders(accessToken: string): HeadersInit {
  return { Authorization: `Bearer ${accessToken}` };
}

async function uploadFetch<T>(
  path: string,
  init: { method: "POST" | "PATCH"; body: FormData; accessToken: string }
): Promise<ApiResponse<T>> {
  const url = `${env.apiBaseUrl}${path}`;
  try {
    const res = await fetch(url, {
      method: init.method,
      headers: { Authorization: `Bearer ${init.accessToken}` }, // no Content-Type — browser sets it for FormData
      body: init.body,
      cache: "no-store",
    });
    if (res.status === 204) {
      return { success: true, data: null as T, meta: { requestId: "n/a", timestamp: new Date().toISOString() } };
    }
    return (await res.json()) as ApiResponse<T>;
  } catch (err) {
    logger.error({ err, url }, "upload_fetch_failed");
    return {
      success: false,
      error: { code: "NETWORK_ERROR", message: "Unable to reach the API service." },
      meta: { requestId: "n/a", timestamp: new Date().toISOString() },
    };
  }
}

// ---- Verification score ----

export function getVerification(companyId: string, accessToken: string) {
  return apiFetch<VerificationScorePublic>(`/api/v1/companies/${companyId}/verification`, {
    headers: authHeaders(accessToken),
  });
}

export function getPublicVerification(slug: string) {
  return apiFetch<VerificationScorePublic>(`/api/v1/companies/slug/${encodeURIComponent(slug)}/verification`);
}

// ---- Business information ----

export function getBusinessInfo(companyId: string, accessToken: string) {
  return apiFetch<BusinessInfoUpdateRequest & { export_capable: boolean }>(
    `/api/v1/companies/${companyId}/business-info`,
    { headers: authHeaders(accessToken) }
  );
}

export function updateBusinessInfo(companyId: string, payload: BusinessInfoUpdateRequest, accessToken: string) {
  return apiFetch<{ updated_fields: string[] }>(`/api/v1/companies/${companyId}/business-info`, {
    method: "PATCH",
    headers: authHeaders(accessToken),
    body: JSON.stringify(payload),
  });
}

// ---- Branding ----

export function getBranding(companyId: string, accessToken: string) {
  return apiFetch<CompanyBrandingPublic>(`/api/v1/companies/${companyId}/branding`, {
    headers: authHeaders(accessToken),
  });
}

export function uploadLogo(companyId: string, file: File, accessToken: string) {
  const form = new FormData();
  form.append("file", file);
  return uploadFetch<CompanyBrandingPublic>(`/api/v1/companies/${companyId}/logo`, {
    method: "POST",
    body: form,
    accessToken,
  });
}

export async function deleteLogo(companyId: string, accessToken: string): Promise<ApiResponse<null>> {
  return apiFetch<null>(`/api/v1/companies/${companyId}/logo`, {
    method: "DELETE",
    headers: authHeaders(accessToken),
  });
}

export function uploadCoverImage(companyId: string, file: File, accessToken: string) {
  const form = new FormData();
  form.append("file", file);
  return uploadFetch<CompanyBrandingPublic>(`/api/v1/companies/${companyId}/cover-image`, {
    method: "POST",
    body: form,
    accessToken,
  });
}

export async function deleteCoverImage(companyId: string, accessToken: string): Promise<ApiResponse<null>> {
  return apiFetch<null>(`/api/v1/companies/${companyId}/cover-image`, {
    method: "DELETE",
    headers: authHeaders(accessToken),
  });
}

// ---- Social links ----

export function listSocialLinks(companyId: string, accessToken: string) {
  return apiFetch<SocialLinkPublic[]>(`/api/v1/companies/${companyId}/social-links`, {
    headers: authHeaders(accessToken),
  });
}

export function upsertSocialLink(companyId: string, platform: SocialPlatform, url: string, accessToken: string) {
  return apiFetch<SocialLinkPublic>(`/api/v1/companies/${companyId}/social-links`, {
    method: "PUT",
    headers: authHeaders(accessToken),
    body: JSON.stringify({ platform, url }),
  });
}

export async function deleteSocialLink(
  companyId: string,
  platform: SocialPlatform,
  accessToken: string
): Promise<ApiResponse<null>> {
  return apiFetch<null>(`/api/v1/companies/${companyId}/social-links/${platform}`, {
    method: "DELETE",
    headers: authHeaders(accessToken),
  });
}

// ---- Verification documents ----

export function listDocuments(companyId: string, accessToken: string) {
  return apiFetch<VerificationDocumentPublic[]>(`/api/v1/companies/${companyId}/documents`, {
    headers: authHeaders(accessToken),
  });
}

export function uploadDocument(companyId: string, documentType: DocumentType, file: File, accessToken: string) {
  const form = new FormData();
  form.append("document_type", documentType);
  form.append("file", file);
  return uploadFetch<VerificationDocumentPublic>(`/api/v1/companies/${companyId}/documents`, {
    method: "POST",
    body: form,
    accessToken,
  });
}

export function replaceDocument(companyId: string, documentId: string, file: File, accessToken: string) {
  const form = new FormData();
  form.append("file", file);
  return uploadFetch<VerificationDocumentPublic>(
    `/api/v1/companies/${companyId}/documents/${documentId}/replace`,
    { method: "PATCH", body: form, accessToken }
  );
}

export async function deleteDocument(
  companyId: string,
  documentId: string,
  accessToken: string
): Promise<ApiResponse<null>> {
  return apiFetch<null>(`/api/v1/companies/${companyId}/documents/${documentId}`, {
    method: "DELETE",
    headers: authHeaders(accessToken),
  });
}
