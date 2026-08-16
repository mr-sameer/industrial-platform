"use client";

import { ArrowRight, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

/**
 * A compact, persistent variant of the homepage's search input — same
 * visual language (Sparkles icon, rounded pill, accent focus ring) so
 * this page feels like it belongs to the same product, but not a reuse
 * of components/home/AISearchBar.tsx: that component is part of the
 * now-frozen homepage and owns its own hero-specific behavior (rotating
 * placeholder, inline dropdown). This one is simpler by design — it
 * always navigates (updates ?q=) rather than showing an inline
 * dropdown, since on this page the results ARE the page.
 */
export function DiscoverySearchBar({ initialQuery }: { initialQuery: string }) {
  const [value, setValue] = useState(initialQuery);
  const router = useRouter();

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = value.trim();
    if (trimmed.length < 2) return;
    router.push(`/discover?q=${encodeURIComponent(trimmed)}`);
  }

  return (
    <form onSubmit={handleSubmit} className="mx-auto w-full max-w-2xl">
      <div className="flex items-center gap-3 rounded-2xl border border-border-strong bg-canvas px-4 py-3 shadow-popover transition-shadow focus-within:border-accent focus-within:ring-4 focus-within:ring-accent/10">
        <Sparkles size={18} className="shrink-0 text-accent" aria-hidden />
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Ask ForgeX anything about industry…"
          aria-label="Ask ForgeX AI"
          className="flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-faint"
        />
        <button
          type="submit"
          disabled={value.trim().length < 2}
          aria-label="Search"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ArrowRight size={14} aria-hidden />
        </button>
      </div>
    </form>
  );
}
