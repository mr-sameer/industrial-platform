"use client";

import type { CompanySearchPage, CompanySearchParams } from "@platform/shared-types";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { searchCompanies } from "@/lib/companies";

const PAGE_SIZE = 12;

/** Company Search — Module 3A, GET /companies/search. Public, no authentication required. */
export default function CompanySearchPage() {
  const [filters, setFilters] = useState({ name: "", industry: "", country: "", city: "" });
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState<NonNullable<CompanySearchParams["sort_by"]>>("created_at");
  const [sortOrder, setSortOrder] = useState<NonNullable<CompanySearchParams["sort_order"]>>("desc");
  const [result, setResult] = useState<CompanySearchPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    const timeout = setTimeout(() => {
      searchCompanies({ ...filters, page, page_size: PAGE_SIZE, sort_by: sortBy, sort_order: sortOrder }).then(
        (res) => {
          setLoading(false);
          if (res.success) {
            setResult(res.data);
          } else {
            setError(res.error.message);
          }
        }
      );
    }, 300); // debounce — avoids firing a request on every keystroke
    return () => clearTimeout(timeout);
  }, [filters, page, sortBy, sortOrder]);

  function updateFilter(key: keyof typeof filters, value: string) {
    setPage(1);
    setFilters((f) => ({ ...f, [key]: value }));
  }

  return (
    <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <h1 className="font-display text-xl font-semibold text-ink">Find suppliers</h1>

      <div className="mt-6 grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-3">
        <Input
          label="Company name"
          placeholder="Company name"
          value={filters.name}
          onChange={(e) => updateFilter("name", e.target.value)}
        />
        <Input
          label="Industry"
          placeholder="Industry"
          value={filters.industry}
          onChange={(e) => updateFilter("industry", e.target.value)}
        />
        <Input
          label="Country"
          placeholder="Country"
          value={filters.country}
          onChange={(e) => updateFilter("country", e.target.value)}
        />
        <Input
          label="City"
          placeholder="City"
          value={filters.city}
          onChange={(e) => updateFilter("city", e.target.value)}
        />
      </div>

      <div className="mt-4 flex items-end gap-3">
        <Select
          label="Sort by"
          className="w-40"
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
        >
          <option value="created_at">Newest</option>
          <option value="name">Name</option>
          <option value="city">City</option>
          <option value="country">Country</option>
        </Select>
        <Button type="button" variant="secondary" onClick={() => setSortOrder((o) => (o === "asc" ? "desc" : "asc"))}>
          {sortOrder === "asc" ? "↑ Ascending" : "↓ Descending"}
        </Button>
      </div>

      {error && <p className="mt-4 text-sm text-danger">{error}</p>}
      {loading && <p className="mt-4 text-sm text-ink-muted">Searching…</p>}

      {!loading && result && result.items.length === 0 && (
        <div className="mt-6 rounded-lg border border-border bg-canvas p-12 text-center">
          <p className="text-sm text-ink-muted">No companies match your search.</p>
        </div>
      )}

      {!loading && result && result.items.length > 0 && (
        <>
          <div className="mt-6 grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-4">
            {result.items.map((c) => (
              <Link
                key={c.id}
                href={`/company/${c.slug}`}
                className="rounded-lg border border-border bg-canvas p-5 transition-colors hover:bg-surface"
              >
                <h3 className="text-sm font-semibold text-ink">{c.name}</h3>
                <p className="mt-1 text-sm text-ink-muted">
                  {c.industry ?? "Industry not set"}
                  {c.city ? ` · ${c.city}` : ""}
                  {c.country ? `, ${c.country}` : ""}
                </p>
                <Badge variant={c.verification_status === "verified" ? "success" : "neutral"} className="mt-3">
                  {c.verification_status === "verified" ? "Verified" : "Unverified"}
                </Badge>
              </Link>
            ))}
          </div>

          <div className="mt-6 flex items-center gap-3">
            <Button type="button" variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Previous
            </Button>
            <span className="text-sm text-ink-muted">
              Page {result.page} of {result.total_pages} ({result.total} total)
            </span>
            <Button
              type="button"
              variant="secondary"
              disabled={page >= result.total_pages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </>
      )}
    </main>
  );
}
