"use client";

import type { CompanySearchResult } from "@platform/shared-types";
import { Building2 } from "lucide-react";
import { useEffect, useState } from "react";


import { searchCompanies } from "@/lib/companies";

/**
 * Reframed as a trust signal, not a directory invitation — a tight
 * row of real companies (GET /companies/search, real backend data),
 * no "browse all" link, no grid of cards begging to be clicked through.
 * The job of this section is credibility ("this is real"), not
 * navigation — AI Search is the only way to actually explore.
 */
export function FeaturedCompanies() {
  const [companies, setCompanies] = useState<CompanySearchResult[] | null>(null);

  useEffect(() => {
    searchCompanies({ page: 1, page_size: 5, sort_by: "created_at", sort_order: "desc" }).then(
      (result) => {
        if (result.success) setCompanies(result.data.items);
      }
    );
  }, []);

  if (companies !== null && companies.length === 0) return null;

  return (
    <section className="border-t border-border bg-canvas px-4 py-16 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-3xl text-center">
        <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">Trusted by real companies</p>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          {companies === null &&
            Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-10 w-36 animate-pulse rounded-full border border-border bg-surface" />
            ))}
          {companies?.map((company) => (
            <span
              key={company.id}
              className="flex items-center gap-2 rounded-full border border-border bg-canvas px-4 py-2"
            >
              <Building2 size={14} className="text-ink-faint" aria-hidden />
              <span className="text-sm font-medium text-ink">{company.name}</span>
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
