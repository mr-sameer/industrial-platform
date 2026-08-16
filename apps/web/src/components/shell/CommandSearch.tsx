"use client";

import type { CompanySearchResult } from "@platform/shared-types";
import * as Dialog from "@radix-ui/react-dialog";
import { Building2, Loader2, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";


import { cn } from "@/lib/cn";
import { searchCompanies } from "@/lib/companies";

/**
 * The signature interactive element of this design (see
 * docs/architecture/design-system.md) — a real ⌘K command palette
 * searching live companies via the existing, unmodified
 * GET /companies/search endpoint. Not decorative: this is the fastest
 * path to "find a company" anywhere in the app.
 */
export function CommandSearch() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CompanySearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function handleKeydown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", handleKeydown);
    return () => window.removeEventListener("keydown", handleKeydown);
  }, []);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setResults([]);
      return;
    }
    if (query.trim().length < 2) {
      setResults([]);
      return;
    }
    setLoading(true);
    const timeout = setTimeout(async () => {
      const result = await searchCompanies({ name: query, page: 1, page_size: 8 });
      setLoading(false);
      if (result.success) setResults(result.data.items);
    }, 250);
    return () => clearTimeout(timeout);
  }, [query, open]);

  function goTo(slug: string) {
    setOpen(false);
    router.push(`/company/${slug}`);
  }

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button
          className={cn(
            "flex h-9 w-full max-w-sm items-center gap-2 rounded-md border border-sidebar-border bg-sidebar-hover px-3",
            "text-sm text-ink-inverse-muted hover:border-border-strong hover:text-ink-inverse transition-colors"
          )}
        >
          <Search size={15} aria-hidden />
          <span className="flex-1 text-left">Search companies…</span>
          <kbd className="rounded border border-sidebar-border bg-sidebar px-1.5 py-0.5 font-mono text-[10px] text-ink-inverse-muted">
            ⌘K
          </kbd>
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-ink/40 backdrop-blur-[2px] animate-fade-in" />
        <Dialog.Content
          onOpenAutoFocus={(e) => {
            e.preventDefault();
            inputRef.current?.focus();
          }}
          className={cn(
            "fixed left-1/2 top-[18vh] z-50 w-[calc(100%-2rem)] max-w-lg -translate-x-1/2",
            "rounded-lg border border-border bg-canvas shadow-dialog animate-slide-up"
          )}
        >
          <Dialog.Title className="sr-only">Search companies</Dialog.Title>
          <Dialog.Description className="sr-only">
            Search for verified companies on the platform by name.
          </Dialog.Description>
          <div className="flex items-center gap-2.5 border-b border-border px-4 py-3">
            <Search size={16} className="text-ink-faint" aria-hidden />
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search companies by name…"
              className="flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-faint"
            />
            {loading && <Loader2 size={15} className="animate-spin text-ink-faint" aria-hidden />}
          </div>
          <div className="max-h-80 overflow-y-auto p-2">
            {query.trim().length >= 2 && !loading && results.length === 0 && (
              <p className="px-2 py-6 text-center text-sm text-ink-muted">No companies match &quot;{query}&quot;.</p>
            )}
            {query.trim().length < 2 && (
              <p className="px-2 py-6 text-center text-sm text-ink-faint">Type at least 2 characters to search.</p>
            )}
            {results.map((company) => (
              <button
                key={company.id}
                onClick={() => goTo(company.slug)}
                className="flex w-full items-center gap-3 rounded-md px-2.5 py-2.5 text-left hover:bg-surface"
              >
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-accent-subtle text-accent">
                  <Building2 size={15} aria-hidden />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-ink">{company.name}</p>
                  <p className="truncate text-xs text-ink-muted">
                    {[company.industry, company.city, company.country].filter(Boolean).join(" · ") || "No details yet"}
                  </p>
                </div>
              </button>
            ))}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
