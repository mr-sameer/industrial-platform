import { AlertTriangle, CheckCircle2 } from "lucide-react";

export interface TechnicalUnderstanding {
  criteria: string[];
  ambiguous: string[];
  unsupported: string[];
  regionalPreference: string[];
}

export function hasTechnicalUnderstandingContent(u: TechnicalUnderstanding): boolean {
  return u.criteria.length > 0 || u.ambiguous.length > 0 || u.unsupported.length > 0 || u.regionalPreference.length > 0;
}

/**
 * The technical-criteria half of "what ForgeX understood" — see
 * RequirementCard for the intent/product/country/certification half.
 * Split into its own card because these fields are only knowable once
 * a category has resolved and its real specifications are fetched (see
 * consult/page.tsx's handleSearch), unlike RequirementCard's fields,
 * which are all known before "Search now" is ever clicked.
 *
 * Real buyer pilot finding this exists to fix: a buyer's explicit
 * "Flow rate: minimum 15 m3/hr" / "Head: at least 150 m" / "Motor
 * power: should not exceed 15 kW" were silently dropped by the old,
 * narrower extractor with zero indication anywhere in the UI — the
 * buyer had no way to know their stated hard requirements never
 * reached the matcher. Every row here is either a green check (a real
 * criterion that reached the backend) or an amber warning (something
 * the buyer said that did NOT reach the backend, and why) — never a
 * silent gap.
 */
export function TechnicalUnderstandingCard({ understanding }: { understanding: TechnicalUnderstanding }) {
  const { criteria, ambiguous, unsupported, regionalPreference } = understanding;
  if (!hasTechnicalUnderstandingContent(understanding)) return null;

  return (
    <div className="rounded-xl border border-border bg-canvas p-5 shadow-popover">
      <h3 className="mb-3 text-sm font-semibold text-ink">ForgeX understood</h3>
      <div className="flex flex-col gap-2">
        {criteria.map((line) => (
          <div key={line} className="flex items-start gap-1.5 text-sm text-ink">
            <CheckCircle2 size={13} className="mt-0.5 shrink-0 text-success" aria-hidden />
            <span>{line}</span>
          </div>
        ))}
        {regionalPreference.length > 0 && (
          <div className="flex items-start gap-1.5 text-sm text-ink-muted">
            <AlertTriangle size={13} className="mt-0.5 shrink-0 text-warning" aria-hidden />
            <span>
              Regional preference noted: {regionalPreference.join(", ")} — not applied as a filter yet, since ForgeX
              only matches on a single country/state/city today.
            </span>
          </div>
        )}
        {ambiguous.map((name) => (
          <div key={name} className="flex items-start gap-1.5 text-sm text-ink-muted">
            <AlertTriangle size={13} className="mt-0.5 shrink-0 text-warning" aria-hidden />
            <span>{name} was mentioned but couldn&apos;t be parsed with confidence — not applied as a requirement. Try restating it, e.g. &quot;at least&quot; / &quot;no more than&quot; a number and unit.</span>
          </div>
        ))}
        {unsupported.map((label) => (
          <div key={label} className="flex items-start gap-1.5 text-sm text-ink-muted">
            <AlertTriangle size={13} className="mt-0.5 shrink-0 text-warning" aria-hidden />
            <span>{label} requirement is not currently matchable — ForgeX doesn&apos;t track this yet.</span>
          </div>
        ))}
      </div>
    </div>
  );
}
