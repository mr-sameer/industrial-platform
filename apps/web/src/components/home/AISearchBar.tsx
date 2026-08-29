"use client";

import type { CompanySearchResult } from "@platform/shared-types";
import { ArrowRight, Building2, Loader2, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ChangeEvent } from "react";


import { cn } from "@/lib/cn";
import { searchCompanies } from "@/lib/companies";
import { autoGrowTextarea, COMPOSER_CONTAINER_CLASSNAME, COMPOSER_TEXTAREA_CLASSNAME, isComposerSubmitKey } from "@/lib/composer";

// Cycled one at a time as a rotating placeholder — communicates the
// range of things ForgeX can be asked without a static chip row
// cluttering the page (removed per explicit product direction: no
// browsing affordances next to the search box). Every example here
// must actually be answerable by where Enter/Search routes it
// (/consult's real requirement extraction + matching engine, see
// lib/requirement.ts) — "Compare ABB and Siemens" was dropped for
// exactly that reason: it's a comparison request, not a sourcing
// requirement, and the extractor has nothing to do with it.
const ROTATING_PROMPTS = [
  "Find a CNC manufacturer in Germany",
  "Need 5,000 hydraulic cylinders",
  "Find a room heater manufacturer",
  "Find FDA-certified packaging suppliers",
  "Source lithium battery manufacturers",
];

/**
 * The product's primary navigation (per product direction: companies,
 * manufacturers, suppliers, products, categories, and industries are
 * all discovered through this, not a navbar). Visually framed as a
 * conversational AI input.
 *
 * Two real, distinct backends live behind it, not one: as-you-type
 * results below the box are a live, honest company-*name* lookup (the
 * public GET /companies/search endpoint — unchanged from before).
 * Pressing Enter or Search, though, hands the typed text to the real
 * Consult requirement flow (routes to /consult?q=..., see its own
 * docstring) rather than that same name-only search — the rotating
 * placeholders above are sourcing requirements ("Need 5,000 hydraulic
 * cylinders"), not company names, and Consult's deterministic
 * extraction + the real Module 7A-2 matching engine is what can
 * actually answer them. Previously both paths went to the name-only
 * search, which meant every placeholder example above returned zero
 * results for a real visitor who typed it.
 */
export function AISearchBar() {
  const [query, setQuery] = useState("");
  const [placeholderIndex, setPlaceholderIndex] = useState(0);
  const [results, setResults] = useState<CompanySearchResult[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const pendingFrameRef = useRef<number | null>(null);
  // Always in sync with the DOM on every keystroke, even while a `query`
  // state update is still coalescing to the next frame — Enter/Search must
  // act on what's actually in the box, not on a state value that can lag
  // behind by up to one animation frame.
  const liveValueRef = useRef("");
  const router = useRouter();

  // Depends on the empty/non-empty boundary only (not the raw string) so this
  // effect doesn't tear down and rebuild on every keystroke.
  const hasQuery = query.length > 0;
  useEffect(() => {
    if (hasQuery) return; // stop rotating once the user starts typing
    const interval = setInterval(() => {
      setPlaceholderIndex((i) => (i + 1) % ROTATING_PROMPTS.length);
    }, 2800);
    return () => clearInterval(interval);
  }, [hasQuery]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    if (query.trim().length < 2) {
      setResults([]);
      setTotal(null);
      return;
    }
    setLoading(true);
    const timeout = setTimeout(async () => {
      const result = await searchCompanies({ name: query, page: 1, page_size: 6 });
      setLoading(false);
      if (result.success) {
        setResults(result.data.items);
        setTotal(result.data.total);
      }
    }, 300);
    return () => clearTimeout(timeout);
  }, [query]);

  // Coalesces a burst of same-frame input events (e.g. a fast scripted/
  // automated fill, which can dispatch many keystrokes with no yield in
  // between) into a single trailing state update per frame instead of one
  // per keystroke — enough synchronous per-keystroke setState calls in a
  // zero-yield burst was previously enough to trip React's "Maximum update
  // depth exceeded" safeguard. A real typist never notices: the textarea
  // itself still reflects every keystroke immediately via imperative DOM
  // resize below, regardless of React's render timing.
  function handleQueryChange(e: ChangeEvent<HTMLTextAreaElement>) {
    const value = e.target.value;
    autoGrowTextarea(e.target);
    liveValueRef.current = value;
    if (pendingFrameRef.current !== null) cancelAnimationFrame(pendingFrameRef.current);
    pendingFrameRef.current = requestAnimationFrame(() => {
      pendingFrameRef.current = null;
      setQuery(value);
    });
  }

  function goToCompany(slug: string) {
    setOpen(false);
    router.push(`/company/${slug}`);
  }

  function submitToConsult() {
    const trimmed = liveValueRef.current.trim();
    if (trimmed.length < 2) return;
    setOpen(false);
    router.push(`/consult?q=${encodeURIComponent(trimmed)}`);
  }

  return (
    <div ref={containerRef} className="relative mx-auto w-full max-w-2xl">
      <div className={cn(COMPOSER_CONTAINER_CLASSNAME, "px-5")}>
        <Sparkles size={20} className="mt-2.5 shrink-0 self-start text-accent" aria-hidden />
        <textarea
          defaultValue={query}
          onChange={handleQueryChange}
          onKeyDown={(e) => {
            if (isComposerSubmitKey(e)) {
              e.preventDefault();
              submitToConsult();
            }
          }}
          onFocus={() => setOpen(true)}
          placeholder={ROTATING_PROMPTS[placeholderIndex]}
          aria-label="Ask ForgeX AI"
          rows={1}
          className={COMPOSER_TEXTAREA_CLASSNAME}
        />
        {loading ? (
          <Loader2 size={18} className="mb-1.5 shrink-0 animate-spin text-ink-faint" aria-hidden />
        ) : (
          <button
            type="button"
            onClick={submitToConsult}
            disabled={query.trim().length < 2}
            aria-label="Search"
            className="mb-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
          >
            <ArrowRight size={16} aria-hidden />
          </button>
        )}
      </div>

      {open && query.trim().length >= 2 && (
        <div className="absolute left-0 right-0 top-full z-30 mt-2 overflow-hidden rounded-xl border border-border bg-canvas shadow-dialog animate-slide-up">
          {!loading && results.length === 0 && (
            <p className="px-5 py-8 text-center text-sm text-ink-muted">
              No companies match “{query}” yet — the platform is growing daily.
            </p>
          )}
          {results.map((company) => (
            <button
              key={company.id}
              onClick={() => goToCompany(company.slug)}
              className="flex w-full items-center gap-3 border-b border-border px-5 py-3 text-left last:border-b-0 hover:bg-surface"
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-accent-subtle text-accent">
                <Building2 size={16} aria-hidden />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-ink">{company.name}</p>
                <p className="truncate text-xs text-ink-muted">
                  {[company.industry, company.city, company.country].filter(Boolean).join(" · ") || "Details coming soon"}
                </p>
              </div>
              {company.verification_status === "verified" && (
                <span className="shrink-0 rounded-full bg-success-subtle px-2 py-0.5 text-[10px] font-medium text-success">
                  Verified
                </span>
              )}
            </button>
          ))}
          {results.length > 0 && total !== null && total > results.length && (
            <button
              type="button"
              onClick={() => router.push(`/discover?q=${encodeURIComponent(query.trim())}`)}
              className="block w-full bg-surface px-5 py-2.5 text-center text-xs text-ink-muted hover:text-accent"
            >
              +{total - results.length} more companies match this search
            </button>
          )}
        </div>
      )}
    </div>
  );
}
