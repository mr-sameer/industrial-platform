"use client";

import type { PendingVerificationDocumentPage } from "@platform/shared-types";
import { DOCUMENT_TYPE_LABELS } from "@platform/shared-types";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { PageLoading } from "@/components/ui/Spinner";
import { useRequirePlatformAdmin } from "@/hooks/useRequirePlatformAdmin";
import { listPendingDocuments } from "@/lib/admin-verification";

const PAGE_SIZE = 20;

/**
 * Verification Queue — Phase 2B-2. Platform-admin-only view of every
 * VerificationDocument awaiting review, across every company (Phase 2A's
 * GET /companies/documents/pending). Read-only: the Review CTA below just
 * navigates to /admin/verification/[documentId] — approve/reject is a
 * later workstream, not implemented here.
 */
export default function AdminVerificationQueuePage() {
  const auth = useRequirePlatformAdmin("/admin/verification");
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<PendingVerificationDocumentPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchQueue = useCallback(async () => {
    if (!auth.accessToken) return;
    setLoading(true);
    setError(null);
    const res = await listPendingDocuments(auth.accessToken, { page, pageSize: PAGE_SIZE, status: "pending" });
    setLoading(false);
    if (res.success) {
      setResult(res.data);
    } else {
      setError(res.error.message);
    }
  }, [auth.accessToken, page]);

  useEffect(() => {
    if (auth.status === "authenticated" && auth.user?.role === "admin") fetchQueue();
  }, [auth.status, auth.user, fetchQueue]);

  if (auth.status === "loading") return <PageLoading />;
  // Non-admins never see this render: useRequirePlatformAdmin's effect
  // above is already pushing them to /dashboard by the time this runs.
  if (auth.status !== "authenticated" || auth.user?.role !== "admin") return null;

  return (
    <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <h1 className="font-display text-xl font-semibold text-ink">Verification Queue</h1>
      <p className="mt-1 text-sm text-ink-muted">
        Documents companies have submitted for verification, awaiting platform review.
        {!error && result && ` ${result.total} pending.`}
      </p>

      {loading && <PageLoading />}

      {!loading && error && (
        <div className="mt-6 flex flex-wrap items-center gap-3 rounded-lg border border-border bg-canvas p-4">
          <p className="text-sm text-danger">{error}</p>
          <Button type="button" variant="secondary" size="sm" onClick={fetchQueue}>
            Retry
          </Button>
        </div>
      )}

      {!loading && !error && result && result.items.length === 0 && (
        <div className="mt-6 rounded-lg border border-border bg-canvas p-12 text-center">
          <p className="text-sm text-ink-muted">No documents awaiting review</p>
        </div>
      )}

      {!loading && !error && result && result.items.length > 0 && (
        <>
          <div className="mt-6 flex flex-col gap-3">
            {result.items.map((doc) => (
              <div
                key={doc.id}
                className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-border bg-canvas p-5"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-sm font-semibold text-ink">{doc.company_name}</h3>
                    <Badge variant="warning">PENDING</Badge>
                  </div>
                  <p className="mt-1 text-sm text-ink-muted">{DOCUMENT_TYPE_LABELS[doc.document_type]}</p>
                  <p className="mt-1 text-xs text-ink-muted">
                    Uploaded {new Date(doc.uploaded_at).toLocaleDateString()}
                    {doc.expiry_date && ` · Expires ${new Date(doc.expiry_date).toLocaleDateString()}`}
                  </p>
                </div>
                <Button asChild variant="secondary" size="sm">
                  <Link href={`/admin/verification/${doc.id}?companyId=${doc.company_id}`}>Review</Link>
                </Button>
              </div>
            ))}
          </div>

          <div className="mt-6 flex items-center gap-3">
            <Button type="button" variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Previous
            </Button>
            <span className="text-sm text-ink-muted">
              Page {result.page} of {result.total_pages} ({result.total} total)
            </span>
            <Button
              type="button"
              variant="secondary"
              disabled={page >= result.total_pages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </>
      )}
    </main>
  );
}
