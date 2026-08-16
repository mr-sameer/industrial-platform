import { Sparkles } from "lucide-react";

/**
 * Per Phase 3A Section 13: no full-page spinner (breaks the
 * conversational feel), and no visual distinction between "loading
 * data" vs "generating a response" — both are just "ForgeX is
 * working." A subtle typing indicator, same visual language as every
 * other ForgeX sparkle-icon touchpoint (homepage, /discover).
 */
export function ThinkingIndicator() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent-subtle text-accent">
        <Sparkles size={13} aria-hidden />
      </div>
      <div className="flex items-center gap-1 rounded-2xl rounded-tl-sm border border-border bg-surface px-4 py-3">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ink-faint [animation-delay:0ms]" />
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ink-faint [animation-delay:150ms]" />
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ink-faint [animation-delay:300ms]" />
      </div>
    </div>
  );
}
