import { searchCompanies } from "@/lib/companies";
import { enrichWithVerification, type DiscoveryMatch } from "@/lib/discover";

/**
 * The Requirement Object — per Phase 3B's own governing rule: "The
 * AI conversation is NOT the product. The user's REQUIREMENTS are the
 * product." Every conversation exists to produce this. It is designed
 * to outlive today's deterministic search: `unfulfillableToday` fields
 * (quantity/budget/timeline) are still captured and kept on the
 * object even though nothing in this phase can act on them, so a
 * future LLM, RFQ generator, analytics pipeline, or procurement
 * workspace has them available without this shape needing to change.
 *
 * No persistence: per Phase 3B's explicit scope, this object lives
 * only in this page's React state for the session. Nothing here is
 * sent to, or stored by, any backend — see docs/product/
 * phase-3a-ai-conversation-architecture.md Section 7 (Memory
 * Architecture): session/conversation memory is explicitly future work.
 */

export type IntentType =
  | "find_manufacturer"
  | "find_supplier"
  | "find_distributor"
  | "find_exporter"
  | "find_company";

export type FieldConfidence = "explicit" | "inferred" | "missing";

export interface RequirementField<T> {
  value: T | null;
  confidence: FieldConfidence;
}

export interface RequirementObject {
  id: string;
  createdAt: string;
  rawQuery: string;
  intent: { type: IntentType; confidence: FieldConfidence };
  productOrCategory: RequirementField<string>;
  country: RequirementField<string>;
  city: RequirementField<string>;
  certifications: RequirementField<string[]>;
  // Captured for completeness (the Requirement Object's whole purpose),
  // never used to filter search results — see docs/frontend/
  // backend-enhancements.md and Phase 3A Section 5/12: no pricing,
  // capacity, or lead-time data exists anywhere in the backend.
  quantity: RequirementField<string>;
  budget: RequirementField<string>;
  timeline: RequirementField<string>;
  overallConfidence: number; // 0-100, see computeConfidence()
}

const ROLE_KEYWORDS: Record<IntentType, string[]> = {
  find_manufacturer: ["manufacturer", "manufacture", "produce", "producer", "factory"],
  find_supplier: ["supplier", "supply"],
  find_distributor: ["distributor", "distribute", "distribution"],
  find_exporter: ["exporter", "export"],
  find_company: [],
};

// A small, honest, fixed lookup list — not a geo database, not NLP.
// Deliberately limited; see this file's extractCountry() docstring.
const KNOWN_COUNTRIES = [
  "india",
  "china",
  "germany",
  "usa",
  "united states",
  "japan",
  "italy",
  "france",
  "uk",
  "united kingdom",
  "south korea",
  "vietnam",
  "taiwan",
  "mexico",
  "brazil",
  "turkey",
  "spain",
  "poland",
  "thailand",
  "indonesia",
];

// Matches real VerificationDocument.document_type values (Module 3B) —
// only certifications ForgeX can actually check for are recognized.
// See app/models/verification_document.py's DocumentType enum.
const KNOWN_CERTIFICATIONS: Record<string, string> = {
  iso: "ISO",
  ce: "CE",
  bis: "BIS",
  gst: "GST Certificate",
  msme: "MSME",
};

/**
 * Applies an answer to the specific field that was just asked about —
 * used when the user responds to a clarifying question (via a chip or
 * free text typed in direct reply). More precise than routing through
 * extractFromText: here, unlike a fresh opening message, we already
 * know exactly which field the reply answers.
 */
export function applyClarifyingAnswer(
  req: RequirementObject,
  field: "intent" | "productOrCategory" | "country" | "certifications",
  answer: string
): RequirementObject {
  const next: RequirementObject = structuredClone(req);
  if (field === "intent") {
    const found = (Object.keys(ROLE_KEYWORDS) as IntentType[]).find(
      (type) => INTENT_DISPLAY[type].toLowerCase() === answer.toLowerCase()
    );
    next.intent = { type: found ?? "find_company", confidence: "explicit" };
  } else if (field === "productOrCategory") {
    next.productOrCategory = { value: answer.trim(), confidence: "explicit" };
  } else if (field === "country") {
    next.country =
      answer.toLowerCase() === "any" ? { value: null, confidence: "explicit" } : { value: answer.trim(), confidence: "explicit" };
  } else if (field === "certifications") {
    next.certifications =
      answer.toLowerCase() === "none"
        ? { value: [], confidence: "explicit" }
        : { value: [answer.trim()], confidence: "explicit" };
  }
  return next;
}

export const INTENT_DISPLAY: Record<IntentType, string> = {
  find_manufacturer: "Manufacturer",
  find_supplier: "Supplier",
  find_distributor: "Distributor",
  find_exporter: "Exporter",
  find_company: "Company",
};

export function newRequirementObject(rawQuery: string): RequirementObject {
  return {
    id: crypto.randomUUID(),
    createdAt: new Date().toISOString(),
    rawQuery,
    intent: { type: "find_company", confidence: "missing" },
    productOrCategory: { value: null, confidence: "missing" },
    country: { value: null, confidence: "missing" },
    city: { value: null, confidence: "missing" },
    certifications: { value: null, confidence: "missing" },
    quantity: { value: null, confidence: "missing" },
    budget: { value: null, confidence: "missing" },
    timeline: { value: null, confidence: "missing" },
    overallConfidence: 0,
  };
}

const FILLER_PREFIXES = [
  "i need",
  "i want",
  "need",
  "looking for",
  "i'm looking for",
  "im looking for",
  "find",
  "find me",
  "source",
  "sourcing",
];

/**
 * Deterministic, keyword-based extraction from free text — not NLP, not
 * an LLM. Every rule here is a simple, explainable, auditable check
 * (a keyword list, a number regex, a filler-word strip). Per Phase 3A's
 * "ask, don't guess" principle (Section 3): fields this function can't
 * confidently extract are left `missing` and asked for explicitly,
 * rather than guessed. This function only ever *narrows* — it never
 * overwrites a field the object already has.
 *
 * `isFirstMessage`: the opening message is treated specially for
 * `productOrCategory` — per the platform's own worked example ("Need
 * CNC machining" → product = "CNC machining", not a separate
 * question), the remaining text after stripping a recognized filler
 * prefix and any already-extracted role/country/number/certification
 * words is taken as the product/category description. This is a
 * simple text-stripping rule, not an understanding of the sentence —
 * marked `explicit` because the user did state it, verbatim.
 */
export function extractFromText(
  existing: RequirementObject,
  text: string,
  isFirstMessage = false
): RequirementObject {
  const next: RequirementObject = structuredClone(existing);
  const lower = text.toLowerCase();

  if (next.intent.confidence === "missing") {
    for (const [type, keywords] of Object.entries(ROLE_KEYWORDS) as [IntentType, string[]][]) {
      if (keywords.some((kw) => lower.includes(kw))) {
        next.intent = { type, confidence: "explicit" };
        break;
      }
    }
  }

  if (next.country.value === null) {
    const match = KNOWN_COUNTRIES.find((c) => lower.includes(c));
    if (match) {
      next.country = { value: titleCase(match), confidence: "explicit" };
    }
  }

  if (next.quantity.value === null) {
    // A number of 2+ digits, optionally with thousands separators —
    // deliberately simple; does not attempt to distinguish quantity
    // from e.g. a year or a budget figure beyond this.
    const numberMatch = text.match(/\b\d{1,3}(?:,\d{3})*\b/);
    if (numberMatch && numberMatch[0].replace(/,/g, "").length >= 2) {
      next.quantity = { value: numberMatch[0], confidence: "explicit" };
    }
  }

  if (next.certifications.value === null) {
    const found = Object.entries(KNOWN_CERTIFICATIONS)
      .filter(([key]) => new RegExp(`\\b${key}\\b`, "i").test(text))
      .map(([, label]) => label);
    if (found.length > 0) {
      next.certifications = { value: found, confidence: "explicit" };
    }
  }

  if (isFirstMessage && next.productOrCategory.value === null) {
    let remainder = text.trim();
    for (const prefix of FILLER_PREFIXES) {
      if (remainder.toLowerCase().startsWith(prefix)) {
        remainder = remainder.slice(prefix.length).trim();
        break;
      }
    }
    // Strip whatever this pass already recognized as a role keyword,
    // known country, or certification, so the remainder is just the
    // product/category description.
    for (const keywords of Object.values(ROLE_KEYWORDS)) {
      for (const kw of keywords) {
        remainder = remainder.replace(new RegExp(`\\b${kw}s?\\b`, "gi"), "").trim();
      }
    }
    if (next.country.value) {
      remainder = remainder.replace(new RegExp(`\\b${next.country.value}\\b`, "gi"), "").trim();
    }
    // Strip a preposition left dangling after removing the country
    // (e.g. "CNC machining in" once "India" is removed) — this isn't
    // cosmetic: a trailing word here would break the real ILIKE
    // substring match against the industry field once used in search.
    remainder = remainder.replace(/\s+(in|for|from|at|near)\s*$/i, "").trim();
    remainder = remainder.replace(/[.,!?]+$/, "").trim();
    if (remainder.length >= 2) {
      next.productOrCategory = { value: remainder, confidence: "explicit" };
    }
  }

  return next;
}

function titleCase(s: string): string {
  return s.replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Which required field to ask for next, or null if enough is known to
 * search. Order matches Phase 3A Section 3 (information value) and
 * Section 5 (per-intent required fields). Enforces the 4-question
 * ceiling (Phase 3A Section 3) via the caller tracking questionsAsked.
 */
export function nextClarifyingField(
  req: RequirementObject
): "intent" | "productOrCategory" | "country" | "certifications" | null {
  if (req.intent.confidence === "missing") return "intent";
  if (req.productOrCategory.confidence === "missing") return "productOrCategory";
  if (req.country.confidence === "missing") return "country";
  if (req.certifications.confidence === "missing") return "certifications";
  return null;
}

/**
 * A transparent, documented formula — not a black-box score. Required
 * fields (intent, product, country) carry more weight than fields that
 * don't affect search results today (quantity/budget/timeline,
 * captured only for the Requirement Object's completeness — see the
 * type's own docstring).
 */
export function computeConfidence(req: RequirementObject): number {
  const weights: Array<[FieldConfidence, number]> = [
    [req.intent.confidence, 25],
    [req.productOrCategory.confidence, 30],
    [req.country.confidence, 15],
    [req.certifications.confidence, 10],
    [req.quantity.confidence, 7],
    [req.budget.confidence, 7],
    [req.timeline.confidence, 6],
  ];
  let score = 0;
  for (const [confidence, weight] of weights) {
    if (confidence === "explicit") score += weight;
    else if (confidence === "inferred") score += weight * 0.6;
  }
  return Math.round(score);
}

export interface RequirementMatch extends DiscoveryMatch {
  matchedOnRequirement: Array<"productOrCategory" | "country" | "city">;
}

/**
 * "Transform structured requirements into the existing backend
 * search. Reuse current APIs." — per Phase 3B's explicit instruction.
 * Calls the real, unmodified GET /companies/search with the
 * Requirement Object's own structured fields as real filters (a more
 * precise use of that endpoint's multi-field support than any prior
 * phase made), then enriches with real, public verification data via
 * the same function the Discovery phase already built.
 *
 * Fallback (documented, not a backend change): a structured
 * `industry=<user's exact phrasing>` query is brittle — Phase 3A
 * Section 8 already documents that `industry` is free text, not a
 * controlled taxonomy, so a user's own words ("CNC machined parts")
 * won't substring-match a company's stored value ("CNC Machining")
 * even though a human would consider them related. Rather than accept
 * a worse result for a documented, known limitation, if the precise
 * query returns nothing, this retries once more using the same
 * product/category text against `name` as well (the same multi-field
 * technique the Discovery phase already established) before reporting
 * no results. Still zero fabrication: every returned result's
 * `matchedOnRequirement` is (re)computed from its own real field
 * values, so a fallback-found result is explained exactly as honestly
 * as a precise-match one.
 */
export async function searchFromRequirement(
  req: RequirementObject,
  page: number,
  pageSize: number
): Promise<{ results: RequirementMatch[]; total: number }> {
  const primary = await searchCompanies({
    industry: req.productOrCategory.value ?? undefined,
    country: req.country.value ?? undefined,
    city: req.city.value ?? undefined,
    page,
    page_size: pageSize,
  });

  let items = primary.success ? primary.data.items : [];
  let total = primary.success ? primary.data.total : 0;

  if (items.length === 0 && req.productOrCategory.value) {
    const fallback = await searchCompanies({
      name: req.productOrCategory.value,
      country: req.country.value ?? undefined,
      city: req.city.value ?? undefined,
      page,
      page_size: pageSize,
    });
    if (fallback.success) {
      items = fallback.data.items;
      total = fallback.data.total;
    }
  }

  const withReasons: RequirementMatch[] = items.map((company) => {
    const matchedOnRequirement: RequirementMatch["matchedOnRequirement"] = [];
    if (
      req.productOrCategory.value &&
      (company.industry?.toLowerCase().includes(req.productOrCategory.value.toLowerCase()) ||
        company.name.toLowerCase().includes(req.productOrCategory.value.toLowerCase()))
    ) {
      matchedOnRequirement.push("productOrCategory");
    }
    if (req.country.value && company.country?.toLowerCase() === req.country.value.toLowerCase()) {
      matchedOnRequirement.push("country");
    }
    if (req.city.value && company.city?.toLowerCase() === req.city.value.toLowerCase()) {
      matchedOnRequirement.push("city");
    }
    return { company, matchedFields: [], verification: null, matchedOnRequirement };
  });

  const enriched = await enrichWithVerification(withReasons);
  return { results: enriched as RequirementMatch[], total };
}
