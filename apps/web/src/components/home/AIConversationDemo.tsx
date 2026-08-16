import { Sparkles } from "lucide-react";

const FOLLOW_UP_OPTIONS = ["Manufacturer", "Supplier", "Distributor"];
const FOLLOW_UP_FIELDS = ["Quantity", "Budget", "Country", "Timeline"];

/**
 * Shows, rather than explains, the conversational experience ForgeX is
 * building toward. A static, honestly-labeled preview — not wired to a
 * real AI/NLP backend, because none exists yet (see
 * docs/frontend/backend-enhancements.md, item 1). The "Preview" badge
 * is deliberate and permanent in this version, not a bug to fix later:
 * it must never look like a live, working conversation.
 */
export function AIConversationDemo() {
  return (
    <section className="border-t border-border bg-surface px-4 py-20 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-2xl">
        <div className="text-center">
          <h2 className="font-display text-2xl font-semibold text-ink sm:text-3xl">
            It understands what you need
          </h2>
          <p className="mt-2 text-sm text-ink-muted">
            Not a keyword search. A conversation that narrows down to the right match.
          </p>
        </div>

        <div className="mt-10 rounded-2xl border border-border bg-canvas p-6 shadow-popover sm:p-8">
          <div className="mb-2 flex justify-end">
            <span className="rounded-full bg-surface px-2.5 py-1 text-[10px] font-medium uppercase tracking-wide text-ink-faint">
              Preview
            </span>
          </div>

          {/* User message */}
          <div className="flex justify-end">
            <p className="max-w-xs rounded-2xl rounded-br-sm bg-accent px-4 py-2.5 text-sm text-white">
              I need stainless steel valves
            </p>
          </div>

          {/* ForgeX response */}
          <div className="mt-4 flex items-start gap-2.5">
            <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent-subtle text-accent">
              <Sparkles size={13} aria-hidden />
            </div>
            <div className="flex-1 rounded-2xl rounded-tl-sm border border-border bg-surface px-4 py-3.5">
              <p className="text-sm text-ink">Looking for:</p>
              <div className="mt-2.5 flex flex-wrap gap-2">
                {FOLLOW_UP_OPTIONS.map((option, i) => (
                  <span
                    key={option}
                    className="flex items-center gap-1.5 rounded-full border border-border-strong bg-canvas px-3 py-1 text-xs font-medium text-ink"
                  >
                    <span
                      className={`h-2.5 w-2.5 rounded-full border ${i === 0 ? "border-accent bg-accent" : "border-border-strong"}`}
                    />
                    {option}
                  </span>
                ))}
              </div>
              <div className="mt-4 grid grid-cols-2 gap-2.5">
                {FOLLOW_UP_FIELDS.map((field) => (
                  <div key={field} className="rounded-lg border border-border bg-canvas px-3 py-2">
                    <p className="text-[10px] font-medium uppercase tracking-wide text-ink-faint">{field}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
