"use client";

import type { CompanyDetail } from "@platform/shared-types";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { PageLoading } from "@/components/ui/Spinner";
import { useRequireAuth } from "@/hooks/useRequireAuth";
import { getCompany } from "@/lib/companies";

/**
 * Company Dashboard — Module 3A. Displays company name, logo placeholder,
 * industry, location, member count, verification status, and created
 * date, per this module's brief.
 */
export default function CompanyDashboardPage() {
  const params = useParams<{ id: string }>();
  const auth = useRequireAuth(`/companies/${params.id}`);
  const [company, setCompany] = useState<CompanyDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchCompany = useCallback(async () => {
    if (!auth.accessToken) return;
    setLoading(true);
    const result = await getCompany(params.id, auth.accessToken);
    if (result.success) {
      setCompany(result.data);
    } else {
      setError(result.error.message);
    }
    setLoading(false);
  }, [auth.accessToken, params.id]);

  useEffect(() => {
    if (auth.status === "authenticated") fetchCompany();
  }, [auth.status, fetchCompany]);

  if (auth.status === "loading" || loading) return <PageLoading />;
  if (auth.status === "unauthenticated") return null;

  if (error) {
    return (
      <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
        <p className="text-sm text-danger">{error}</p>
        <Link href="/companies" className="text-sm text-accent hover:text-accent-hover">
          Back to your companies
        </Link>
      </main>
    );
  }

  if (!company) return null;

  return (
    <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-4">
          {/* Logo placeholder — no logo upload exists yet (a future module); this is the
              "Logo Placeholder" the brief's Dashboard spec asks for. */}
          <div
            className="flex h-16 w-16 shrink-0 items-center justify-center rounded-lg bg-surface text-2xl font-bold text-ink-faint"
            aria-hidden
          >
            {company.name.charAt(0).toUpperCase()}
          </div>
          <div>
            <h1 className="font-display text-xl font-semibold text-ink">{company.name}</h1>
            <p className="text-sm text-ink-muted">{company.industry ?? "Industry not set"}</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="secondary">
            <Link href={`/companies/${company.id}/verification`}>Verification</Link>
          </Button>
          <Button asChild variant="secondary">
            <Link href={`/companies/${company.id}/settings`}>Settings</Link>
          </Button>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-4">
        <div className="rounded-lg border border-border bg-canvas p-5">
          <h4 className="text-sm font-semibold text-ink">Location</h4>
          <p className="mt-1 text-sm text-ink-muted">
            {[company.city, company.state, company.country].filter(Boolean).join(", ") || "Not set"}
          </p>
        </div>
        <div className="rounded-lg border border-border bg-canvas p-5">
          <h4 className="text-sm font-semibold text-ink">Members</h4>
          <p className="mt-1 text-sm text-ink-muted">{company.member_count}</p>
        </div>
        <div className="rounded-lg border border-border bg-canvas p-5">
          <h4 className="text-sm font-semibold text-ink">Verification status</h4>
          <Badge variant={company.verification_status === "verified" ? "success" : "neutral"} className="mt-2">
            {company.verification_status === "verified" ? "Verified" : "Unverified"}
          </Badge>
        </div>
        <div className="rounded-lg border border-border bg-canvas p-5">
          <h4 className="text-sm font-semibold text-ink">Created</h4>
          <p className="mt-1 text-sm text-ink-muted">{new Date(company.created_at).toLocaleDateString()}</p>
        </div>
      </div>

      {company.description && (
        <div className="mt-6">
          <h3 className="text-sm font-semibold text-ink">About</h3>
          <p className="mt-1 text-sm text-ink-muted">{company.description}</p>
        </div>
      )}

      <p className="mt-8 text-sm text-ink-muted">
        Your role here: <strong className="text-ink">{company.my_role}</strong> · Public profile:{" "}
        <Link href={`/company/${company.slug}`} className="text-accent hover:text-accent-hover">
          /company/{company.slug}
        </Link>
      </p>
    </main>
  );
}
