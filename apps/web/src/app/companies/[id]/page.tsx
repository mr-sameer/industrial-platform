"use client";

import type { CompanyDetail } from "@platform/shared-types";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";


import { useRequireAuth } from "@/hooks/useRequireAuth";
import { getCompany } from "@/lib/companies";
import * as ui from "@/lib/ui-styles";

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

  if (auth.status === "loading" || loading) return <main style={ui.page}>Loading…</main>;
  if (auth.status === "unauthenticated") return null;

  if (error) {
    return (
      <main style={ui.page}>
        <p style={ui.errorText}>{error}</p>
        <Link href="/companies">Back to your companies</Link>
      </main>
    );
  }

  if (!company) return null;

  return (
    <main style={ui.page}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
        <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
          {/* Logo placeholder — no logo upload exists yet (a future module); this is the
              "Logo Placeholder" the brief's Dashboard spec asks for. */}
          <div
            style={{
              width: 64,
              height: 64,
              borderRadius: 8,
              background: "#f0f0f0",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: "1.5rem",
              fontWeight: 700,
              color: "#999",
            }}
            aria-hidden
          >
            {company.name.charAt(0).toUpperCase()}
          </div>
          <div>
            <h1 style={{ margin: 0 }}>{company.name}</h1>
            <p style={ui.mutedText}>{company.industry ?? "Industry not set"}</p>
          </div>
        </div>
        <Link href={`/companies/${company.id}/settings`} style={ui.buttonSecondary}>
          Settings
        </Link>
      </div>

      <div style={{ ...ui.cardGrid, marginTop: "1.5rem" }}>
        <div style={ui.card}>
          <h4 style={{ marginTop: 0 }}>Location</h4>
          <p>
            {[company.city, company.state, company.country].filter(Boolean).join(", ") || "Not set"}
          </p>
        </div>
        <div style={ui.card}>
          <h4 style={{ marginTop: 0 }}>Members</h4>
          <p>{company.member_count}</p>
        </div>
        <div style={ui.card}>
          <h4 style={{ marginTop: 0 }}>Verification status</h4>
          <span style={ui.badgeForVerification(company.verification_status)}>
            {company.verification_status === "verified" ? "Verified" : "Unverified"}
          </span>
        </div>
        <div style={ui.card}>
          <h4 style={{ marginTop: 0 }}>Created</h4>
          <p>{new Date(company.created_at).toLocaleDateString()}</p>
        </div>
      </div>

      {company.description && (
        <div style={{ marginTop: "1.5rem" }}>
          <h3>About</h3>
          <p>{company.description}</p>
        </div>
      )}

      <p style={{ ...ui.mutedText, marginTop: "2rem" }}>
        Your role here: <strong>{company.my_role}</strong> · Public profile:{" "}
        <Link href={`/company/${company.slug}`}>/company/{company.slug}</Link>
      </p>
    </main>
  );
}
