import { Building2, CheckCircle2, ShieldCheck, Sparkles } from "lucide-react";
import Link from "next/link";

import { verificationLevelLabel } from "@/lib/discover";
import type { RequirementMatch } from "@/lib/requirement";

const LEVEL_COLOR: Record<string, string> = {
  unverified: "text-level-unverified",
  email_verified: "text-level-email",
  business_verified: "text-level-business",
  factory_verified: "text-level-factory",
  premium_verified: "text-level-premium",
};

const REQUIREMENT_FIELD_LABELS: Record<string, string> = {
  productOrCategory: "product/category",
  country: "country",
  city: "city",
};

/**
 * Per Phase 3B's explicit rule: "Why this company? Matched industry.
 * Matched location. Verification. Trust. Known limitations.
 * Confidence. Never fabricate." Every line below traces to a real
 * fact: matchedOnRequirement is computed from real field comparisons
 * (lib/requirement.ts), verification is the real, public Module 3B
 * endpoint. The "known limitations" line is always shown, not
 * conditionally — quantity/budget/timeline never affect these
 * results, and hiding that fact would be exactly the kind of
 * overselling Phase 3A Section 1 rules out.
 */
export function RecommendationCard({ match }: { match: RequirementMatch }) {
  const { company, matchedOnRequirement, verification } = match;
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

      {matchedOnRequirement.length > 0 && (
        <div className="mt-4 flex items-start gap-2 rounded-lg bg-accent-subtle/60 px-3.5 py-2.5">
          <Sparkles size={14} className="mt-0.5 shrink-0 text-accent" aria-hidden />
          <p className="text-sm text-ink">
            <span className="font-medium">Matches your requirement</span> on{" "}
            {matchedOnRequirement.map((field, i) => (
              <span key={field}>
                {i > 0 && (i === matchedOnRequirement.length - 1 ? " and " : ", ")}
                <span className="font-medium">{REQUIREMENT_FIELD_LABELS[field]}</span>
              </span>
            ))}
            .
          </p>
        </div>
      )}

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

      <p className="mt-3 border-t border-border pt-3 text-xs text-ink-faint">
        Quantity, budget, and timeline weren&apos;t used to rank this result — that data isn&apos;t
        available yet.
      </p>
    </Link>
  );
}
