/**
 * Admin Verification Queue API client — Phase 2B-1. Same direct-to-FastAPI
 * pattern as lib/company-verification.ts (see that file's docstring for
 * why no BFF is needed here) — a new file rather than adding to
 * company-verification.ts, since these two calls are platform-admin-only
 * and cross-company, unlike everything else in that file (always scoped
 * to a single, already-known company_id).
 */
import type { DocumentStatus, PendingVerificationDocumentPage, VerificationDocumentPublic } from "@platform/shared-types";

import { apiFetch } from "@/lib/api-client";

function authHeaders(accessToken: string): HeadersInit {
  return { Authorization: `Bearer ${accessToken}` };
}

/**
 * GET /companies/documents/pending — the queue's data source (Phase 2A).
 * `status` defaults to "pending" on the backend when omitted; passed
 * explicitly here whenever the caller wants a specific queue view
 * (e.g. reviewing what's already been decided).
 */
export function listPendingDocuments(
  accessToken: string,
  options: { page?: number; pageSize?: number; status?: DocumentStatus } = {}
) {
  const { page = 1, pageSize = 20, status } = options;
  const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (status) query.set("status", status);
  return apiFetch<PendingVerificationDocumentPage>(`/api/v1/companies/documents/pending?${query.toString()}`, {
    headers: authHeaders(accessToken),
  });
}

/**
 * POST /companies/{company_id}/documents/{document_id}/review — approve
 * or reject a pending document. Requires both company_id and document_id
 * (the backend resolves the document by that pair together — see
 * document_service.get_document_or_none — so a mismatched company_id
 * 404s rather than acting on/leaking a different company's document).
 * `note` is only meaningful on "reject" — the backend always clears
 * review_note to null on "approve" regardless of what's sent.
 */
export function reviewDocument(
  companyId: string,
  documentId: string,
  decision: "approve" | "reject",
  accessToken: string,
  note?: string
) {
  return apiFetch<VerificationDocumentPublic>(`/api/v1/companies/${companyId}/documents/${documentId}/review`, {
    method: "POST",
    headers: authHeaders(accessToken),
    body: JSON.stringify(note !== undefined ? { decision, note } : { decision }),
  });
}
