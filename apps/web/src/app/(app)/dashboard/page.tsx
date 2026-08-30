"use client";

import Link from "next/link";

import { useRequireAuth } from "@/hooks/useRequireAuth";
import * as ui from "@/lib/ui-styles";

/**
 * First-session Dashboard — Module 2's original placeholder ("Real
 * dashboard content arrives with the first business-feature module")
 * replaced per the ForgeX Product Audit's P0 #3: a brand-new user's
 * very first authenticated screen was unstyled debug text. This stays
 * deliberately small — a welcome, the one honest signal worth
 * surfacing this early (email verification, since it gates company
 * creation), and a path into the two things that actually exist today
 * (Consult, Companies) — not a dashboard with invented metrics.
 */
export default function DashboardPage() {
  const auth = useRequireAuth("/dashboard");

  if (auth.status === "loading") return <main style={ui.page}>Loading…</main>;
  if (auth.status === "unauthenticated" || !auth.user) return null;

  const { user } = auth;

  return (
    <main style={ui.page}>
      <h1 style={{ marginBottom: "0.35rem" }}>Welcome, {user.full_name}</h1>
      <p style={ui.mutedText}>
        {user.email} · {user.role}
      </p>

      {!user.is_email_verified && (
        <p style={{ ...ui.mutedText, marginTop: "1rem" }}>
          Your email isn&apos;t verified yet — check your inbox for the verification link.
          Creating a company requires a verified email.
        </p>
      )}

      <div style={{ ...ui.cardGrid, marginTop: "1.75rem" }}>
        <Link href="/consult" style={{ ...ui.card, textDecoration: "none", color: "inherit" }}>
          <h3 style={{ margin: "0 0 0.35rem" }}>Ask ForgeX</h3>
          <p style={ui.mutedText}>Describe what your business needs and find matching suppliers.</p>
        </Link>
        <Link href="/companies" style={{ ...ui.card, textDecoration: "none", color: "inherit" }}>
          <h3 style={{ margin: "0 0 0.35rem" }}>Your companies</h3>
          <p style={ui.mutedText}>Set up your company profile and start building trust with buyers.</p>
        </Link>
      </div>
    </main>
  );
}
