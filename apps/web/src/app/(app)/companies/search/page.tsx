"use client";

import type { CompanySearchPage, CompanySearchParams } from "@platform/shared-types";
import Link from "next/link";
import { useEffect, useState } from "react";


import { searchCompanies } from "@/lib/companies";
import * as ui from "@/lib/ui-styles";

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
    <main style={ui.page}>
      <h1>Find suppliers</h1>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "0.75rem", marginBottom: "1rem" }}>
        <input
          style={ui.input}
          placeholder="Company name"
          value={filters.name}
          onChange={(e) => updateFilter("name", e.target.value)}
        />
        <input
          style={ui.input}
          placeholder="Industry"
          value={filters.industry}
          onChange={(e) => updateFilter("industry", e.target.value)}
        />
        <input
          style={ui.input}
          placeholder="Country"
          value={filters.country}
          onChange={(e) => updateFilter("country", e.target.value)}
        />
        <input
          style={ui.input}
          placeholder="City"
          value={filters.city}
          onChange={(e) => updateFilter("city", e.target.value)}
        />
      </div>

      <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1.5rem", alignItems: "center" }}>
        <label style={ui.mutedText}>
          Sort by{" "}
          <select
            style={{ ...ui.input, display: "inline-block" }}
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
          >
            <option value="created_at">Newest</option>
            <option value="name">Name</option>
            <option value="city">City</option>
            <option value="country">Country</option>
          </select>
        </label>
        <button
          type="button"
          style={ui.buttonSecondary}
          onClick={() => setSortOrder((o) => (o === "asc" ? "desc" : "asc"))}
        >
          {sortOrder === "asc" ? "↑ Ascending" : "↓ Descending"}
        </button>
      </div>

      {error && <p style={ui.errorText}>{error}</p>}
      {loading && <p style={ui.mutedText}>Searching…</p>}

      {!loading && result && result.items.length === 0 && (
        <div style={{ ...ui.card, textAlign: "center", padding: "3rem" }}>
          <p>No companies match your search.</p>
        </div>
      )}

      {!loading && result && result.items.length > 0 && (
        <>
          <div style={ui.cardGrid}>
            {result.items.map((c) => (
              <Link
                key={c.id}
                href={`/company/${c.slug}`}
                style={{ ...ui.card, textDecoration: "none", color: "inherit" }}
              >
                <h3 style={{ margin: "0 0 0.35rem" }}>{c.name}</h3>
                <p style={ui.mutedText}>
                  {c.industry ?? "Industry not set"}
                  {c.city ? ` · ${c.city}` : ""}
                  {c.country ? `, ${c.country}` : ""}
                </p>
                <span style={ui.badgeForVerification(c.verification_status)}>
                  {c.verification_status === "verified" ? "Verified" : "Unverified"}
                </span>
              </Link>
            ))}
          </div>

          <div style={{ display: "flex", gap: "0.75rem", marginTop: "1.5rem", alignItems: "center" }}>
            <button
              type="button"
              style={ui.buttonSecondary}
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </button>
            <span style={ui.mutedText}>
              Page {result.page} of {result.total_pages} ({result.total} total)
            </span>
            <button
              type="button"
              style={ui.buttonSecondary}
              disabled={page >= result.total_pages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
          </div>
        </>
      )}
    </main>
  );
}
