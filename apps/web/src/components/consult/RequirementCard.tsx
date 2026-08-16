import { CheckCircle2, HelpCircle } from "lucide-react";

import { INTENT_DISPLAY, type FieldConfidence, type RequirementObject } from "@/lib/requirement";

function ConfidenceIcon({ confidence }: { confidence: FieldConfidence }) {
  if (confidence === "missing") return <HelpCircle size={13} className="text-ink-faint" aria-hidden />;
  return (
    <CheckCircle2
      size={13}
      className={confidence === "explicit" ? "text-success" : "text-accent"}
      aria-hidden
    />
  );
}

function Row({ label, value, confidence }: { label: string; value: string | null; confidence: FieldConfidence }) {
  return (
    <div className="flex items-center justify-between border-b border-border py-2.5 last:border-b-0">
      <span className="flex items-center gap-1.5 text-sm text-ink-muted">
        <ConfidenceIcon confidence={confidence} />
        {label}
      </span>
      <span className="text-sm font-medium text-ink">{value ?? "Unknown"}</span>
    </div>
  );
}

/**
 * "Users should always see what ForgeX understood." The Requirement
 * Object (lib/requirement.ts) made visible — every row here is a
 * direct field on that object, nothing summarized or paraphrased.
 * Green check = explicit (user said it), blue check = inferred, gray
 * question mark = missing — this distinction matters (Phase 3A
 * Section 5): an inferred field is a guess the user hasn't confirmed.
 */
export function RequirementCard({ requirement }: { requirement: RequirementObject }) {
  return (
    <div className="rounded-xl border border-border bg-canvas p-5 shadow-popover">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-ink">What ForgeX understood</h3>
        <span className="rounded-full bg-accent-subtle px-2.5 py-0.5 text-xs font-medium text-accent">
          {requirement.overallConfidence}% confidence
        </span>
      </div>
      <div className="flex flex-col">
        <Row label="Looking for" value={INTENT_DISPLAY[requirement.intent.type]} confidence={requirement.intent.confidence} />
        <Row label="Product / category" value={requirement.productOrCategory.value} confidence={requirement.productOrCategory.confidence} />
        <Row label="Country" value={requirement.country.value} confidence={requirement.country.confidence} />
        <Row
          label="Certifications"
          value={requirement.certifications.value?.join(", ") ?? null}
          confidence={requirement.certifications.confidence}
        />
        <Row label="Quantity" value={requirement.quantity.value} confidence={requirement.quantity.confidence} />
        <Row label="Budget" value={requirement.budget.value} confidence={requirement.budget.confidence} />
        <Row label="Timeline" value={requirement.timeline.value} confidence={requirement.timeline.confidence} />
      </div>
      <p className="mt-3 text-xs text-ink-faint">
        Quantity, budget, and timeline aren&apos;t used to filter results yet — ForgeX doesn&apos;t have
        pricing or capacity data today.
      </p>
    </div>
  );
}
