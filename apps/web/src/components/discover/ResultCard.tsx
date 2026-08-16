import { Building2, CheckCircle2, ShieldCheck, Sparkles } from "lucide-react";
import Link from "next/link";

import { FIELD_LABELS, type DiscoveryMatch, verificationLevelLabel } from "@/lib/discover";

const LEVEL_COLOR: Record<string, string> = {
  unverified: "text-level-unverified",
  email_verified: "text-level-email",
  business_verified: "text-level-business",
  factory_verified: "text-level-factory",
  premium_verified: "text-level-premium",
};

/**
 * The core "AI explains why" unit. Every line here traces to a real
 * fact: matchedFields comes from real substring checks against the
 * company's actual field values (lib/discover.ts); the verification
 * summary comes from the real, public GET /companies/slug/{slug}/verification
 * endpoint (Module 3B, unmodified). Nothing here is generated text.
 */
export function ResultCard({ match, query }: { match: DiscoveryMatch; query: string }) {
  const { company, matchedFields, verification } = match;
  const levelLabel = verificationLevelLabel(verification);

  return (
    <Link
      href={`/company/${company.slug}`}
      className="block rounded-xl border border-border bg-canvas p-5 transition-colors hover:border-accent"
    >
      <div className="flex items-start gap-3.5">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-accent-subtle text-accent">
          <Building2 size={20} aria-hidden />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-medium text-ink">{company.name}</h3>
            {company.verification_status === "verified" && (
              <span className="flex items-center gap-1 rounded-full bg-success-subtle px-2 py-0.5 text-[10px] font-medium text-success">
                <ShieldCheck size={10} aria-hidden />
                Verified
              </span>
            )}
          </div>
          <p className="mt-0.5 text-sm text-ink-muted">
            {[company.industry, company.city, company.country].filter(Boolean).join(" · ") || "Details not yet provided"}
          </p>
        </div>
      </div>

      {/* Why this result — the section this whole page exists for. */}
      {matchedFields.length > 0 && (
        <div className="mt-4 flex items-start gap-2 rounded-lg bg-accent-subtle/60 px-3.5 py-2.5">
          <Sparkles size={14} className="mt-0.5 shrink-0 text-accent" aria-hidden />
          <p className="text-sm text-ink">
            <span className="font-medium">Matches “{query}”</span> on{" "}
            {matchedFields.map((field, i) => (
              <span key={field}>
                {i > 0 && (i === matchedFields.length - 1 ? " and " : ", ")}
                <span className="font-medium">{FIELD_LABELS[field].toLowerCase()}</span>
              </span>
            ))}
            .
          </p>
        </div>
      )}

      {/* Trust signal — real Module 3B verification data, progressively loaded. */}
      <div className="mt-3 flex items-center gap-2 text-xs text-ink-muted">
        {verification === null ? (
          <span className="h-4 w-32 animate-pulse rounded bg-surface" aria-hidden />
        ) : (
          <>
            <CheckCircle2 size={13} className={LEVEL_COLOR[verification.level]} aria-hidden />
            <span>
              <span className={`font-medium ${LEVEL_COLOR[verification.level]}`}>{levelLabel}</span>
              {" · "}
              {verification.percentage}% complete
            </span>
          </>
        )}
      </div>
    </Link>
  );
}
