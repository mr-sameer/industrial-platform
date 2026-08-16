import type { CompanySearchResult, VerificationScorePublic } from "@platform/shared-types";
import { VERIFICATION_LEVEL_LABELS } from "@platform/shared-types";

import { searchCompanies } from "@/lib/companies";
import { getPublicVerification } from "@/lib/company-verification";

/**
 * The AI-assisted discovery "reasoning" engine — real and deterministic,
 * not a fabricated LLM explanation. There is no NLP/intent backend (see
 * docs/frontend/backend-enhancements.md, item 1) — GET /companies/search
 * only does independent substring matches per field (name/industry/
 * city/country; confirmed directly against
 * app/services/company_service.py). Rather than pretend to parse intent
 * we don't have, this runs the same query text against every field in
 * parallel (four real, unmodified API calls) and, for each result,
 * determines — from the real returned field values, not a guess —
 * exactly which field(s) the query matched. Every "why" shown to the
 * user traces to a real, checkable fact.
 */

export type MatchField = "name" | "industry" | "city" | "country";

export interface DiscoveryMatch {
  company: CompanySearchResult;
  matchedFields: MatchField[];
  verification: VerificationScorePublic | null; // null while loading or if the fetch failed
}

const FIELD_LABELS: Record<MatchField, string> = {
  name: "Company name",
  industry: "Industry",
  city: "City",
  country: "Country",
};

export { FIELD_LABELS };

function normalizedIncludes(haystack: string | null, needle: string): boolean {
  if (!haystack) return false;
  return haystack.toLowerCase().includes(needle.toLowerCase());
}

/**
 * Runs the query against all four searchable fields in parallel and
 * merges the results, deduping by company id. Each merged result's
 * `matchedFields` is computed from its own real field values — never
 * assumed from which query variant returned it (a company could
 * legitimately match on more than one field at once, e.g. "Pune" in
 * both its city and, coincidentally, its name).
 */
export async function discoverCompanies(
  query: string,
  page: number,
  pageSize: number
): Promise<{ results: DiscoveryMatch[]; total: number }> {
  const trimmed = query.trim();
  if (trimmed.length < 2) return { results: [], total: 0 };

  const [byName, byIndustry, byCity, byCountry] = await Promise.all([
    searchCompanies({ name: trimmed, page: 1, page_size: 50 }),
    searchCompanies({ industry: trimmed, page: 1, page_size: 50 }),
    searchCompanies({ city: trimmed, page: 1, page_size: 50 }),
    searchCompanies({ country: trimmed, page: 1, page_size: 50 }),
  ]);

  const merged = new Map<string, CompanySearchResult>();
  for (const result of [byName, byIndustry, byCity, byCountry]) {
    if (!result.success) continue;
    for (const company of result.data.items) merged.set(company.id, company);
  }

  const allMatches: DiscoveryMatch[] = Array.from(merged.values()).map((company) => {
    const matchedFields: MatchField[] = [];
    if (normalizedIncludes(company.name, trimmed) || normalizedIncludes(company.slug, trimmed)) {
      matchedFields.push("name");
    }
    if (normalizedIncludes(company.industry, trimmed)) matchedFields.push("industry");
    if (normalizedIncludes(company.city, trimmed)) matchedFields.push("city");
    if (normalizedIncludes(company.country, trimmed)) matchedFields.push("country");
    return { company, matchedFields, verification: null };
  });

  // Real companies with more matched fields are a stronger match — a
  // deterministic, explainable ranking (not a black-box AI score).
  allMatches.sort((a, b) => b.matchedFields.length - a.matchedFields.length);

  const total = allMatches.length;
  const start = (page - 1) * pageSize;
  const results = allMatches.slice(start, start + pageSize);
  return { results, total };
}

/**
 * Enriches a page of results with real, public trust data
 * (GET /companies/slug/{slug}/verification — unauthenticated, unmodified
 * Module 3B endpoint). Called separately from discoverCompanies so
 * result cards can render immediately and have their trust signal
 * fill in progressively, rather than blocking the whole page on N
 * extra requests.
 */
export async function enrichWithVerification(matches: DiscoveryMatch[]): Promise<DiscoveryMatch[]> {
  const enriched = await Promise.all(
    matches.map(async (match) => {
      const result = await getPublicVerification(match.company.slug);
      return { ...match, verification: result.success ? result.data : null };
    })
  );
  return enriched;
}

export function verificationLevelLabel(verification: VerificationScorePublic | null): string | null {
  if (!verification) return null;
  return VERIFICATION_LEVEL_LABELS[verification.level];
}
