"use client";

import { Search as SearchIcon, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { DiscoverySearchBar } from "@/components/discover/DiscoverySearchBar";
import { ResultCard } from "@/components/discover/ResultCard";
import { discoverCompanies, enrichWithVerification, type DiscoveryMatch } from "@/lib/discover";

const PAGE_SIZE = 10;

export default function DiscoverPage() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-canvas" />}>
      <DiscoverContent />
    </Suspense>
  );
}

function DiscoverContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const query = searchParams.get("q") ?? "";
  const page = Math.max(1, Number(searchParams.get("page") ?? "1") || 1);

  const [matches, setMatches] = useState<DiscoveryMatch[] | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (query.trim().length < 2) {
      setMatches([]);
      setTotal(0);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setMatches(null);

    discoverCompanies(query, page, PAGE_SIZE).then(async ({ results, total: resultTotal }) => {
      if (cancelled) return;
      setMatches(results); // render immediately with real search-match data
      setTotal(resultTotal);
      setLoading(false);

      // Trust signals fill in progressively — never block the page on them.
      const enriched = await enrichWithVerification(results);
      if (!cancelled) setMatches(enriched);
    });

    return () => {
      cancelled = true;
    };
  }, [query, page]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  function goToPage(nextPage: number) {
    router.push(`/discover?q=${encodeURIComponent(query)}&page=${nextPage}`);
  }

  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <header className="sticky top-0 z-40 border-b border-border bg-canvas/90 px-4 py-4 backdrop-blur-sm sm:px-6">
        <div className="mx-auto flex max-w-3xl items-center gap-4">
          <Link href="/" className="shrink-0 font-display text-lg font-semibold tracking-tight text-ink">
            Forge<span className="text-accent">X</span>
          </Link>
          <DiscoverySearchBar initialQuery={query} />
        </div>
      </header>

      <main className="flex-1 px-4 py-8 sm:px-6">
        <div className="mx-auto max-w-3xl">
          {query.trim().length < 2 && (
            <div className="flex flex-col items-center gap-3 py-24 text-center">
              <SearchIcon size={28} className="text-ink-faint" aria-hidden />
              <p className="text-ink-muted">Ask ForgeX something to get started.</p>
            </div>
          )}

          {query.trim().length >= 2 && (
            <>
              <div className="mb-6 flex items-center gap-2">
                <Sparkles size={16} className="text-accent" aria-hidden />
                <h1 className="text-sm text-ink-muted">
                  Results for <span className="font-medium text-ink">“{query}”</span>
                  {!loading && <span className="text-ink-faint"> · {total} found</span>}
                </h1>
              </div>

              {loading && (
                <div className="flex flex-col gap-3">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <div key={i} className="h-28 animate-pulse rounded-xl border border-border bg-surface" />
                  ))}
                </div>
              )}

              {!loading && matches !== null && matches.length === 0 && (
                <div className="flex flex-col items-center gap-2 py-16 text-center">
                  <p className="text-ink-muted">No companies match “{query}” yet.</p>
                  <p className="text-sm text-ink-faint">ForgeX is growing daily — try a different term.</p>
                </div>
              )}

              {!loading && matches !== null && matches.length > 0 && (
                <div className="flex flex-col gap-3">
                  {matches.map((match) => (
                    <ResultCard key={match.company.id} match={match} query={query} />
                  ))}
                </div>
              )}

              {!loading && totalPages > 1 && (
                <div className="mt-8 flex items-center justify-center gap-3">
                  <button
                    type="button"
                    disabled={page <= 1}
                    onClick={() => goToPage(page - 1)}
                    className="rounded-md border border-border-strong px-3 py-1.5 text-sm text-ink disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Previous
                  </button>
                  <span className="text-sm text-ink-muted">
                    Page {page} of {totalPages}
                  </span>
                  <button
                    type="button"
                    disabled={page >= totalPages}
                    onClick={() => goToPage(page + 1)}
                    className="rounded-md border border-border-strong px-3 py-1.5 text-sm text-ink disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Next
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}
