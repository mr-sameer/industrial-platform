"use client";

import type { CompanyPublic } from "@platform/shared-types";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useRequireAuth } from "@/hooks/useRequireAuth";
import { listMyCompanies } from "@/lib/companies";

/** "Company List" — Module 3A. The dashboard entry point: every company the current user belongs to. */
export default function CompanyListPage() {
  const auth = useRequireAuth("/companies");
  const [companies, setCompanies] = useState<CompanyPublic[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (auth.status !== "authenticated" || !auth.accessToken) return;
    listMyCompanies(auth.accessToken).then((result) => {
      if (result.success) {
        setCompanies(result.data);
      } else {
        setError(result.error.message);
      }
    });
  }, [auth.status, auth.accessToken]);

  if (auth.status === "loading") return <main className="p-8 text-sm text-ink-muted">Loading…</main>;
  if (auth.status === "unauthenticated") return null;

  return (
    <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="font-display text-xl font-semibold text-ink">Your companies</h1>
        <Button asChild>
          <Link href="/companies/new">+ New company</Link>
        </Button>
      </div>

      {error && <p className="text-sm text-danger">{error}</p>}

      {companies === null && !error && <p className="text-sm text-ink-muted">Loading your companies…</p>}

      {companies !== null && companies.length === 0 && (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-border bg-canvas p-12 text-center">
          <p className="text-sm text-ink-muted">You&apos;re not part of any company yet.</p>
          {/* ForgeX Product Audit P1 #10: the empty state previously said
              nothing about why a company matters — buyers discover and
              evaluate companies through Consult, and trust_tier (a real,
              scored match signal) weighs verified companies more heavily
              than unverified ones, so this is a factual benefit, not a
              marketing claim. */}
          <p className="max-w-sm text-sm text-ink-muted">
            Buyers find and evaluate companies through ForgeX Consult — verified details are weighted more heavily
            in every match.
          </p>
          <Button asChild>
            <Link href="/companies/new">Create your first company</Link>
          </Button>
        </div>
      )}

      {companies !== null && companies.length > 0 && (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-4">
          {companies.map((c) => (
            <Link
              key={c.id}
              href={`/companies/${c.id}`}
              className="rounded-lg border border-border bg-canvas p-5 transition-colors hover:bg-surface"
            >
              <h3 className="text-sm font-semibold text-ink">{c.name}</h3>
              <p className="mt-1 text-sm text-ink-muted">
                {c.industry ?? "Industry not set"}
                {c.city ? ` · ${c.city}` : ""}
                {c.country ? `, ${c.country}` : ""}
              </p>
              <Badge className="mt-3">
                {c.member_count} member{c.member_count === 1 ? "" : "s"}
              </Badge>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}
