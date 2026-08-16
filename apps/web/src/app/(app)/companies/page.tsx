"use client";

import type { CompanyPublic } from "@platform/shared-types";
import Link from "next/link";
import { useEffect, useState } from "react";


import { useRequireAuth } from "@/hooks/useRequireAuth";
import { listMyCompanies } from "@/lib/companies";
import * as ui from "@/lib/ui-styles";

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

  if (auth.status === "loading") return <main style={ui.page}>Loading…</main>;
  if (auth.status === "unauthenticated") return null;

  return (
    <main style={ui.page}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <h1>Your companies</h1>
        <Link href="/companies/new" style={ui.button}>
          + New company
        </Link>
      </div>

      {error && <p style={ui.errorText}>{error}</p>}

      {companies === null && !error && <p style={ui.mutedText}>Loading your companies…</p>}

      {companies !== null && companies.length === 0 && (
        <div style={{ ...ui.card, textAlign: "center", padding: "3rem" }}>
          <p>You&apos;re not part of any company yet.</p>
          <Link href="/companies/new" style={ui.button}>
            Create your first company
          </Link>
        </div>
      )}

      {companies !== null && companies.length > 0 && (
        <div style={ui.cardGrid}>
          {companies.map((c) => (
            <Link
              key={c.id}
              href={`/companies/${c.id}`}
              style={{ ...ui.card, textDecoration: "none", color: "inherit" }}
            >
              <h3 style={{ margin: "0 0 0.35rem" }}>{c.name}</h3>
              <p style={ui.mutedText}>
                {c.industry ?? "Industry not set"}
                {c.city ? ` · ${c.city}` : ""}
                {c.country ? `, ${c.country}` : ""}
              </p>
              <span style={{ ...ui.badge, background: "#f6f7f8", color: "#666" }}>
                {c.member_count} member{c.member_count === 1 ? "" : "s"}
              </span>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}
