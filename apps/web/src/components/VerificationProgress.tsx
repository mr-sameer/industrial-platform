import type { VerificationScorePublic } from "@platform/shared-types";
import { VERIFICATION_LEVEL_LABELS } from "@platform/shared-types";

/**
 * Shared "Verification Progress" display — Module 3B. Used by the
 * Verification Dashboard page and embeddable anywhere else a compact
 * progress view is useful (kept as one component per
 * docs/standards/coding-standards.md's "no duplicated logic").
 */
export function VerificationProgress({ score }: { score: VerificationScorePublic }) {
  return (
    <div className="rounded-lg border border-border bg-canvas p-5">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-ink">{VERIFICATION_LEVEL_LABELS[score.level]}</h3>
        <span className="text-2xl font-bold text-ink">{score.percentage}%</span>
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-surface">
        <div
          className="h-full rounded-full bg-success transition-[width] duration-300 ease-out"
          style={{ width: `${score.percentage}%` }}
        />
      </div>

      {score.next_level && (
        <p className="mt-3 text-sm text-ink-muted">
          Next level: <strong className="text-ink">{VERIFICATION_LEVEL_LABELS[score.next_level]}</strong>
        </p>
      )}

      {score.missing_requirements.length > 0 && (
        <div className="mt-4">
          <h4 className="text-sm font-semibold text-ink">Missing requirements</h4>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink">
            {score.missing_requirements.map((req) => (
              <li key={req.key}>
                {req.label} <span className="text-ink-muted">(+{req.weight}%)</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {score.missing_requirements.length === 0 && (
        <p className="mt-4 text-sm text-success">All requirements met — fully verified.</p>
      )}
    </div>
  );
}
