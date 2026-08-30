"use client";

import type { VerificationScorePublic } from "@platform/shared-types";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { VerificationProgress } from "@/components/VerificationProgress";
import { useRequireAuth } from "@/hooks/useRequireAuth";
import { getVerification } from "@/lib/company-verification";

/** Verification Dashboard — Module 3B. */
export default function VerificationDashboardPage() {
  const params = useParams<{ id: string }>();
  const auth = useRequireAuth(`/companies/${params.id}/verification`);
  const [score, setScore] = useState<VerificationScorePublic | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchScore = useCallback(async () => {
    if (!auth.accessToken) return;
    setLoading(true);
    const result = await getVerification(params.id, auth.accessToken);
    if (result.success) {
      setScore(result.data);
    } else {
      setError(result.error.message);
    }
    setLoading(false);
  }, [auth.accessToken, params.id]);

  useEffect(() => {
    if (auth.status === "authenticated") fetchScore();
  }, [auth.status, fetchScore]);

  if (auth.status === "loading" || loading) return <main className="p-8 text-sm text-ink-muted">Loading…</main>;
  if (auth.status === "unauthenticated") return null;

  return (
    <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <p>
        <Link href={`/companies/${params.id}`} className="text-sm text-accent hover:text-accent-hover">
          &larr; Back to dashboard
        </Link>
      </p>
      <h1 className="mt-2 font-display text-xl font-semibold text-ink">Verification</h1>

      {error && <p className="mt-4 text-sm text-danger">{error}</p>}
      {!error && !score && <p className="mt-4 text-sm text-ink-muted">Loading verification status…</p>}
      {score && (
        <div className="mt-4">
          <VerificationProgress score={score} />
        </div>
      )}

      <div className="mt-6 grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-4">
        <Link
          href={`/companies/${params.id}/business-info`}
          className="rounded-lg border border-border bg-canvas p-5 transition-colors hover:bg-surface"
        >
          <h4 className="text-sm font-semibold text-ink">Business Information</h4>
          <p className="mt-1 text-sm text-ink-muted">Legal entity, registration numbers, description</p>
        </Link>
        <Link
          href={`/companies/${params.id}/documents`}
          className="rounded-lg border border-border bg-canvas p-5 transition-colors hover:bg-surface"
        >
          <h4 className="text-sm font-semibold text-ink">Documents</h4>
          <p className="mt-1 text-sm text-ink-muted">Certificates and registration evidence</p>
        </Link>
        <Link
          href={`/companies/${params.id}/branding`}
          className="rounded-lg border border-border bg-canvas p-5 transition-colors hover:bg-surface"
        >
          <h4 className="text-sm font-semibold text-ink">Branding</h4>
          <p className="mt-1 text-sm text-ink-muted">Logo and cover image</p>
        </Link>
        <Link
          href={`/companies/${params.id}/social-links`}
          className="rounded-lg border border-border bg-canvas p-5 transition-colors hover:bg-surface"
        >
          <h4 className="text-sm font-semibold text-ink">Social Links</h4>
          <p className="mt-1 text-sm text-ink-muted">LinkedIn, YouTube, Facebook, Instagram, X</p>
        </Link>
      </div>
    </main>
  );
}
