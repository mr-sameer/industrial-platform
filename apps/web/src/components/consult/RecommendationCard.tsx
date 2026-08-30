import { Building2, CheckCircle2, ExternalLink, HelpCircle, ShieldCheck, XCircle } from "lucide-react";
import Link from "next/link";

import { VERIFICATION_LEVEL_LABELS, type VerificationLevel } from "@platform/shared-types";
import type { RequirementMatchCandidate, RequirementMatchEvidenceItem } from "@platform/shared-types";

const LEVEL_COLOR: Record<string, string> = {
  unverified: "text-level-unverified",
  email_verified: "text-level-email",
  business_verified: "text-level-business",
  factory_verified: "text-level-factory",
  premium_verified: "text-level-premium",
};

function verificationLevelLabel(level: string): string {
  return VERIFICATION_LEVEL_LABELS[level as VerificationLevel] ?? level;
}

function roleLabel(role: string): string {
  return role
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
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

/**
 * A single procurement fact (MOQ / lead time / capacity) straight from
 * the real Offering row — `null` is rendered as an honest "Unknown",
 * never a guessed or default value. A non-null value is always labeled
 * "OBSERVED", never "guaranteed" — Phase 4B's Offering fields are
 * seller-published facts ForgeX has not independently audited, and a
 * 2-day lead time claim is not a delivery promise this component may
 * imply.
 */
function ProcurementFact({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-ink-muted">{label}</span>
      {value === null ? (
        <span className="flex items-center gap-1 text-ink-faint">
          <HelpCircle size={11} aria-hidden />
          Unknown
        </span>
      ) : (
        <span className="flex items-center gap-1.5 font-medium text-ink">
          {value}
          <span className="rounded-full bg-accent-subtle px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-accent">
            Observed
          </span>
        </span>
      )}
    </div>
  );
}

/**
 * One cited source behind a real fact — `status` is rendered exactly
 * as ForgeX's own provenance rule defines it (never anything but
 * observed/extracted unless a real, separate verification action
 * actually happened — see RequirementMatchEvidenceItem's own
 * docstring). A VERIFIED badge here would only ever appear if the
 * backend itself reports status="verified"; nothing on this component
 * upgrades that value.
 */
function EvidenceRow({ item }: { item: RequirementMatchEvidenceItem }) {
  const isVerified = item.status === "verified";
  return (
    <div className="mt-1.5 text-xs">
      <div className="flex items-center gap-1.5">
        <span
          className={`rounded-full px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide ${
            isVerified ? "bg-success-subtle text-success" : "bg-accent-subtle text-accent"
          }`}
        >
          {isVerified ? "Verified" : "Observed"}
        </span>
        <span className="font-medium text-ink-muted">{evidenceFieldLabel(item.field_name)}</span>
      </div>
      <p className="mt-0.5 text-ink-muted">{item.value_observed}</p>
      {item.source_url && (
        <a
          href={item.source_url}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="mt-0.5 flex items-center gap-1 text-accent hover:text-accent-hover"
        >
          <ExternalLink size={10} aria-hidden />
          Source
        </a>
      )}
    </div>
  );
}

function SignalPoints({ label, earned, possible }: { label: string; earned: number; possible: number }) {
  if (possible === 0) {
    return (
      <div className="flex items-center justify-between text-xs text-ink-faint">
        <span className="flex items-center gap-1">
          <HelpCircle size={11} aria-hidden />
          {label}
        </span>
        <span>Not requested</span>
      </div>
    );
  }
  return (
    <div className="flex items-center justify-between text-xs text-ink-muted">
      <span>{label}</span>
      <span className="font-medium text-ink">
        {earned}/{possible} pts
      </span>
    </div>
  );
}

/**
 * Renders the real Module 7A-2 match contract — every line here traces
 * to a field on RequirementMatchCandidate returned by
 * GET /api/v1/requirements/{id}/matches, never a client-computed guess.
 * `candidate_value: null` (an unresolved criterion) and
 * `evidence_found: []` (no VERIFIED certification evidence) are always
 * rendered as an explicit "Unknown"/"No evidence found" state, never
 * silently dropped or treated as a match — mirrors the backend's own
 * "never a positive contribution without a citable row" rule.
 *
 * `offering.moq`/`.lead_time`/`.capacity` and `evidence` are additive
 * response fields (this iteration) surfacing real Offering/provenance
 * data that already existed in the database but was previously
 * invisible in Consult. Every value is labeled "Observed," never
 * "guaranteed" or "verified," unless the backend itself reports
 * status="verified" for that specific evidence row.
 */
export function RecommendationCard({ match }: { match: RequirementMatchCandidate }) {
  const { company, product, score, signals, score_breakdown, offering, evidence } = match;
  const levelLabel = verificationLevelLabel(company.verification_level);

  return (
    <div className="rounded-xl border border-border bg-canvas p-5">
      <Link href={`/company/${company.slug}`} className="block transition-colors hover:opacity-90">
        <div className="flex items-start gap-3.5">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-accent-subtle text-accent">
            <Building2 size={20} aria-hidden />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-medium text-ink">{company.name}</h3>
              <span className="rounded-full bg-accent-subtle px-2 py-0.5 text-[10px] font-medium text-accent">
                {score}% match
              </span>
              {/* Role is a claim from the seller-published profile, not
                  something ForgeX has independently checked (Offering.
                  verification_status is a real column with no admin-review
                  workflow behind it yet — see app.models.offering). Shown
                  with the same honest OBSERVED-not-VERIFIED weight as the
                  rest of this card, never as a confirmed fact. */}
              <span
                className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${
                  offering.verification_status === "verified"
                    ? "bg-success-subtle text-success"
                    : "border border-border-strong text-ink-muted"
                }`}
              >
                {offering.verification_status === "verified" ? (
                  <ShieldCheck size={10} aria-hidden />
                ) : (
                  <HelpCircle size={10} className="text-ink-faint" aria-hidden />
                )}
                {roleLabel(offering.role)}
                {offering.verification_status !== "verified" && (
                  <span className="text-ink-faint">(unverified)</span>
                )}
              </span>
            </div>
            <p className="mt-0.5 text-sm text-ink-muted">{product.name}</p>
          </div>
        </div>
      </Link>

      <div className="mt-3 flex items-center gap-2 text-xs text-ink-muted">
        <CheckCircle2 size={13} className={LEVEL_COLOR[company.verification_level]} aria-hidden />
        <span className={`font-medium ${LEVEL_COLOR[company.verification_level]}`}>{levelLabel}</span>
        {company.verification_level !== "unverified" && (
          <span className="flex items-center gap-1 text-success">
            <ShieldCheck size={11} aria-hidden />
          </span>
        )}
      </div>

      <div className="mt-3 space-y-1.5 border-t border-border pt-3">
        {score_breakdown.map((entry) => (
          <SignalPoints
            key={entry.signal}
            label={entry.signal.replace(/_/g, " ")}
            earned={entry.points_earned}
            possible={entry.weight}
          />
        ))}
      </div>

      <div className="mt-3 space-y-1 border-t border-border pt-3">
        <p className="text-xs font-medium text-ink-muted">Procurement details</p>
        <ProcurementFact label="Minimum order quantity" value={offering.moq} />
        <ProcurementFact label="Published lead time" value={offering.lead_time} />
        {offering.capacity !== null && <ProcurementFact label="Supply capacity" value={offering.capacity} />}
      </div>

      {signals.criteria.length > 0 && (
        <div className="mt-3 space-y-1 border-t border-border pt-3">
          <p className="text-xs font-medium text-ink-muted">Requested specifications</p>
          {signals.criteria.map((criterion) => (
            <div key={criterion.specification_id} className="flex items-center justify-between text-xs">
              <span className="text-ink-muted">{criterion.specification_name}</span>
              <span className="flex items-center gap-1 font-medium text-ink">
                {criterion.candidate_value === null ? (
                  <>
                    <HelpCircle size={11} className="text-ink-faint" aria-hidden />
                    Unknown
                  </>
                ) : (
                  <>
                    <CheckCircle2 size={11} className="text-success" aria-hidden />
                    {criterion.candidate_value}
                  </>
                )}
              </span>
            </div>
          ))}
        </div>
      )}

      {signals.certifications.requested.length > 0 && (
        <div className="mt-3 border-t border-border pt-3 text-xs">
          <p className="font-medium text-ink-muted">Certifications</p>
          {signals.certifications.requested.map((cert) => {
            const found = signals.certifications.evidence_found.includes(cert);
            return (
              <div key={cert} className="mt-1 flex items-center gap-1.5">
                {found ? (
                  <CheckCircle2 size={11} className="text-success" aria-hidden />
                ) : (
                  <XCircle size={11} className="text-ink-faint" aria-hidden />
                )}
                <span className={found ? "text-ink" : "text-ink-faint"}>
                  {cert}
                  {!found && " — no VERIFIED evidence found"}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {signals.location.points_possible > 0 && (
        <p className="mt-3 border-t border-border pt-3 text-xs text-ink-muted">
          Location: {[signals.location.candidate.city, signals.location.candidate.state, signals.location.candidate.country]
            .filter(Boolean)
            .join(", ") || "Unknown"}
        </p>
      )}

      {evidence.length > 0 ? (
        <div className="mt-3 border-t border-border pt-3">
          <p className="text-xs font-medium text-ink-muted">Evidence &amp; sources</p>
          {evidence.map((item, i) => (
            <EvidenceRow key={`${item.field_name}-${i}`} item={item} />
          ))}
        </div>
      ) : (
        <p className="mt-3 border-t border-border pt-3 text-xs text-ink-faint">
          No cited evidence on file for this product yet.
        </p>
      )}
    </div>
  );
}
