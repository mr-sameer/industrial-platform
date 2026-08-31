"use client";

import Link from "next/link";

import { useRequireAuth } from "@/hooks/useRequireAuth";

/**
 * First-session Dashboard — Module 2's original placeholder ("Real
 * dashboard content arrives with the first business-feature module")
 * replaced per the ForgeX Product Audit's P0 #3: a brand-new user's
 * very first authenticated screen was unstyled debug text. This stays
 * deliberately small — a welcome, the one honest signal worth
 * surfacing this early (email verification, since it gates company
 * creation), and a path into the two things that actually exist today
 * (Consult, Companies) — not a dashboard with invented metrics.
 *
 * Ported off `lib/ui-styles.ts` onto the real Tailwind design system
 * (P1 #14 — the audit's "three incompatible visual systems" finding;
 * ui-styles.ts was already retired from the ten Module 3A pages by
 * P1 #3, leaving this page as the only remaining committed holdout),
 * mirroring the same tokens/classes companies/page.tsx already uses.
 */
export default function DashboardPage() {
  const auth = useRequireAuth("/dashboard");

  if (auth.status === "loading") return <main className="p-8 text-sm text-ink-muted">Loading…</main>;
  if (auth.status === "unauthenticated" || !auth.user) return null;

  const { user } = auth;

  return (
    <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <h1 className="font-display text-xl font-semibold text-ink">Welcome, {user.full_name}</h1>
      <p className="mt-1 text-sm text-ink-muted">
        {user.email} · {user.role}
      </p>

      {!user.is_email_verified && (
        <p className="mt-4 text-sm text-ink-muted">
          Your email isn&apos;t verified yet — check your inbox for the verification link. Creating a company
          requires a verified email.
        </p>
      )}

      <div className="mt-7 grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-4">
        <Link
          href="/consult"
          className="rounded-lg border border-border bg-canvas p-5 transition-colors hover:bg-surface"
        >
          <h3 className="text-sm font-semibold text-ink">Ask ForgeX</h3>
          <p className="mt-1 text-sm text-ink-muted">
            Describe what your business needs and find matching suppliers.
          </p>
        </Link>
        <Link
          href="/companies"
          className="rounded-lg border border-border bg-canvas p-5 transition-colors hover:bg-surface"
        >
          <h3 className="text-sm font-semibold text-ink">Your companies</h3>
          <p className="mt-1 text-sm text-ink-muted">
            Set up your company profile and start building trust with buyers.
          </p>
        </Link>
      </div>
    </main>
  );
}
