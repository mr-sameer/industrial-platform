import { HelpCircle } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { serverEnv } from "@/config/server-env";
import { getCompanyBySlug } from "@/lib/companies";
import { parseMatchContext } from "@/lib/company-match-context";
import * as ui from "@/lib/ui-styles";

/**
 * Public Company Profile — Module 3A, GET /company/{slug}. A Server
 * Component (no "use client") since it needs no authentication and
 * benefits from server rendering for a public, shareable, SEO-relevant
 * page — unlike the authenticated dashboard pages, which need client-side
 * AuthContext state.
 *
 * P0 #2 (Buyer UX Audit): this runs inside the web container (Server
 * Component), so it must call the API over the Compose network
 * (serverEnv.apiBaseUrl / API_INTERNAL_BASE_URL), not the browser-facing
 * NEXT_PUBLIC_API_BASE_URL that getCompanyBySlug's other, client-side
 * call sites correctly default to — see getCompanyBySlug's own comment
 * and docker-compose.yml.
 */
export default async function PublicCompanyProfilePage({
  params,
  searchParams,
}: {
  params: { slug: string };
  searchParams: { [key: string]: string | string[] | undefined };
}) {
  const result = await getCompanyBySlug(params.slug, serverEnv.apiBaseUrl);
  const matchContext = parseMatchContext(searchParams.match);

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

      {matchContext && (
        <div style={{ ...ui.card, marginTop: "1.5rem" }}>
          <h4 style={{ marginTop: 0 }}>Procurement details from your search</h4>
          <p style={ui.mutedText}>
            {matchContext.productName} &middot; {roleLabel(matchContext.role)} — carried over from the ForgeX Consult
            match you followed here; not shown to other visitors of this page.
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem", marginTop: "0.75rem" }}>
            <ProcurementFact label="Minimum order quantity" value={matchContext.moq} />
            <ProcurementFact label="Published lead time" value={matchContext.leadTime} />
            {matchContext.capacity !== null && <ProcurementFact label="Supply capacity" value={matchContext.capacity} />}
          </div>

          {matchContext.certificationsRequested.length > 0 && (
            <div style={{ marginTop: "0.9rem" }}>
              <p style={{ ...ui.mutedText, fontWeight: 600, marginBottom: "0.35rem" }}>Certifications</p>
              {matchContext.certificationsRequested.map((cert) => {
                const found = matchContext.certificationsEvidenceFound.includes(cert);
                return (
                  <p key={cert} style={{ ...ui.mutedText, margin: "0.15rem 0" }}>
                    {found ? "✓" : "○"} {cert}
                    {!found && " — no VERIFIED evidence found"}
                  </p>
                );
              })}
            </div>
          )}

          {matchContext.evidence.length > 0 ? (
            <div style={{ marginTop: "0.9rem" }}>
              <p style={{ ...ui.mutedText, fontWeight: 600, marginBottom: "0.35rem" }}>Evidence &amp; sources</p>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                {matchContext.evidence.map((item, i) => (
                  <div key={`${item.fieldName}-${i}`} style={ui.evidenceCard}>
                    <span style={item.status === "verified" ? ui.badgeVerified : ui.badgeObserved}>
                      {item.status === "verified" ? "Verified" : "Observed"}
                    </span>{" "}
                    <span style={{ fontWeight: 600 }}>{evidenceFieldLabel(item.fieldName)}</span>
                    <p style={{ margin: "0.3rem 0 0" }}>{item.valueObserved}</p>
                    {item.sourceUrl && (
                      <a href={item.sourceUrl} target="_blank" rel="noopener noreferrer" style={ui.link}>
                        Source
                      </a>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p style={{ ...ui.mutedText, marginTop: "0.9rem" }}>No cited evidence on file for this product yet.</p>
          )}
        </div>
      )}

      <p style={{ marginTop: "2rem" }}>
        <Link href="/companies/search">&larr; Back to search</Link>
      </p>
    </main>
  );
}

const EVIDENCE_FIELD_LABELS: Record<string, string> = {
  product_line: "Product line",
  certification_claim: "Certification claim",
  moq: "MOQ",
  lead_time: "Lead time",
  gst_number: "GST number",
  nature_of_business: "Nature of business",
};

function evidenceFieldLabel(fieldName: string): string {
  return EVIDENCE_FIELD_LABELS[fieldName] ?? roleLabel(fieldName);
}

function roleLabel(value: string): string {
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

/**
 * Same honest-unknown convention as components/consult/RecommendationCard.tsx's
 * ProcurementFact: `null` always renders as "Unknown", never a guessed
 * default, and a real value is always labeled "Observed" — these are
 * seller-published Offering facts ForgeX has not independently audited.
 */
function ProcurementFact({ label, value }: { label: string; value: string | null }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: "0.85rem" }}>
      <span style={ui.mutedText}>{label}</span>
      {value === null ? (
        <span style={{ ...ui.mutedText, display: "flex", alignItems: "center", gap: "0.25rem" }}>
          <HelpCircle size={12} aria-hidden />
          Unknown
        </span>
      ) : (
        <span style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontWeight: 600 }}>
          {value}
          <span style={ui.badgeObserved}>Observed</span>
        </span>
      )}
    </div>
  );
}
