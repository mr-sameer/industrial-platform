import Link from "next/link";
import { notFound } from "next/navigation";

import { getCompanyBySlug } from "@/lib/companies";
import * as ui from "@/lib/ui-styles";

/**
 * Public Company Profile — Module 3A, GET /company/{slug}. A Server
 * Component (no "use client") since it needs no authentication and
 * benefits from server rendering for a public, shareable, SEO-relevant
 * page — unlike the authenticated dashboard pages, which need client-side
 * AuthContext state.
 */
export default async function PublicCompanyProfilePage({ params }: { params: { slug: string } }) {
  const result = await getCompanyBySlug(params.slug);

  if (!result.success) {
    if (result.error.code === "COMPANY_NOT_FOUND") notFound();
    return (
      <main style={ui.page}>
        <p style={ui.errorText}>{result.error.message}</p>
      </main>
    );
  }

  const company = result.data;

  return (
    <main style={ui.page}>
      <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
        <div
          style={{
            width: 72,
            height: 72,
            borderRadius: 8,
            background: "#f0f0f0",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "1.75rem",
            fontWeight: 700,
            color: "#999",
          }}
          aria-hidden
        >
          {company.name.charAt(0).toUpperCase()}
        </div>
        <div>
          <h1 style={{ margin: 0 }}>{company.name}</h1>
          <span style={ui.badgeForVerification(company.verification_status)}>
            {company.verification_status === "verified" ? "Verified" : "Unverified"}
          </span>
        </div>
      </div>

      {company.description && <p style={{ marginTop: "1.5rem" }}>{company.description}</p>}

      <div style={{ ...ui.cardGrid, marginTop: "1.5rem" }}>
        <div style={ui.card}>
          <h4 style={{ marginTop: 0 }}>Industry</h4>
          <p>{company.industry ?? "Not specified"}</p>
        </div>
        <div style={ui.card}>
          <h4 style={{ marginTop: 0 }}>Location</h4>
          <p>{[company.city, company.country].filter(Boolean).join(", ") || "Not specified"}</p>
        </div>
        <div style={ui.card}>
          <h4 style={{ marginTop: 0 }}>Members</h4>
          <p>{company.member_count}</p>
        </div>
        {company.website && (
          <div style={ui.card}>
            <h4 style={{ marginTop: 0 }}>Website</h4>
            <a href={company.website} target="_blank" rel="noreferrer">
              {company.website}
            </a>
          </div>
        )}
      </div>

      <p style={{ marginTop: "2rem" }}>
        <Link href="/companies/search">&larr; Back to search</Link>
      </p>
    </main>
  );
}
