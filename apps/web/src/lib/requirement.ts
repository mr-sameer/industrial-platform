import type { ProductCategory } from "@platform/shared-types";

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
 * Object construction stays purely client-side/deterministic (no NLP,
 * no LLM) exactly as Phase 3B built it. What changed: once this object
 * is complete, the Consult flow now submits it to the real
 * Module 7A-1 backend (POST /api/v1/requirements) and reads ranked
 * matches from the real Module 7A-2 engine (see
 * lib/requirements-api.ts and app/consult/page.tsx) instead of the old
 * client-only GET /companies/search + keyword-explanation path.
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

// A small, honest, fixed lookup list — same "not a geo database, not
// NLP" philosophy as KNOWN_COUNTRIES above. Longer/more specific names
// listed first so "new delhi" wins over a bare "delhi" substring check
// when both would otherwise match.
const KNOWN_CITIES = [
  "new delhi",
  "delhi",
  "mumbai",
  "bengaluru",
  "bangalore",
  "pune",
  "chennai",
  "kolkata",
  "hyderabad",
  "ahmedabad",
  "gurugram",
  "gurgaon",
  "noida",
  "surat",
  "jaipur",
];

// Word-form cardinals a real buyer might type instead of a digit
// ("one unit" as well as "1 unit") — deliberately small and fixed,
// not a number-parsing library.
const WORD_NUMBERS: Record<string, string> = {
  one: "1",
  two: "2",
  three: "3",
  four: "4",
  five: "5",
  six: "6",
  seven: "7",
  eight: "8",
  nine: "9",
  ten: "10",
  eleven: "11",
  twelve: "12",
  fifteen: "15",
  twenty: "20",
};
// Comma-grouped ("20,000") tried first, then a plain digit run of any
// length ("20000") — quantity/timeline never exercised a bare number
// over 3 digits before (their real values are always small), but a
// budget legitimately can be. Without the plain-digit-run alternative,
// `\d{1,3}(?:,\d{3})*` alone can only ever match the first 1-3 digits
// of an uncommaed 4+-digit number (e.g. just "200" of "20000"), which
// then fails the pattern's own trailing `\b` boundary check since
// there's no word boundary between two consecutive digits — so the
// whole match silently fails instead of capturing the full number.
const NUMBER_WORD_PATTERN = `(?:\\d{1,3}(?:,\\d{3})*|\\d+|${Object.keys(WORD_NUMBERS).join("|")})`;

function numberTokenToDigits(token: string): string {
  const lower = token.toLowerCase();
  return WORD_NUMBERS[lower] ?? token;
}

// A small, honest, fixed lookup — same philosophy as KNOWN_COUNTRIES:
// only currency tokens a real buyer would actually type, not an
// exchange-rate-aware parser.
const CURRENCY_PATTERN = "(?:USD|INR|EUR|GBP|Rs\\.?|₹|\\$|€)";

// Referenced by QUANTITY_OPENING_PATTERN below as well as the
// productOrCategory remainder-stripping logic further down this file —
// declared here (rather than only where it's used later) so both can
// share the one list instead of drifting apart.
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

// Three independent, additive shapes for the same field — a bare
// "<number> <unit word>" (the original rule), a "<label> <number>"
// shape ("quantity 500", "qty: 500") a buyer stating several fields in
// one sentence tends to use instead, and a number sitting directly
// after the sentence's own opening phrase ("I need 500 room heaters",
// "Need 5,000 hydraulic cylinders" — the platform's own homepage
// example). All three stay strict/adjacent, never a bare unlabeled
// number anywhere in the sentence — that would risk grabbing an
// unrelated digit (a budget, a year, a phone number) as a quantity,
// which is exactly the false-positive risk this file's own docstring
// above warns against. QUANTITY_OPENING_PATTERN in particular only
// fires when the number is the very first thing after a recognized
// opening phrase, so "I need a manufacturer ... a few hundred pieces"
// (the number nowhere near the opening) still correctly falls through
// to missing rather than grabbing the wrong digit.
const QUANTITY_UNIT_PATTERN = new RegExp(`\\b(${NUMBER_WORD_PATTERN})\\s+(?:units?|pieces?|pcs?)\\b`, "i");
const QUANTITY_LABEL_PATTERN = new RegExp(`\\b(?:quantity|qty)\\s*(?:of|is|:)?\\s*(${NUMBER_WORD_PATTERN})\\b`, "i");
const QUANTITY_OPENING_PATTERN = new RegExp(
  `^(?:${FILLER_PREFIXES.join("|")})\\s+(${NUMBER_WORD_PATTERN})\\b`,
  "i"
);
// ForgeX Product Audit P0: covers a number sitting right after the verb
// that actually names the sourcing action ("who can produce 5,000 X",
// "can manufacture 500 X") rather than right after the sentence's own
// opening phrase — a real buyer sentence with a relative clause between
// the opening and the number ("I need a manufacturer near Delhi who can
// produce 5,000 X") previously matched none of the three patterns above,
// so the quantity fell through to Unknown *and* the "5,000" was never
// stripped out of productOrCategory's remainder either, since that strip
// is itself gated on a quantity having been found. Deliberately a short,
// specific verb list (same "adjacent, never a bare number" discipline as
// every other pattern in this file) — not a general "any verb near a
// number" rule, which would risk the same false-positive a bare-number
// rule elsewhere in this file already guards against.
const QUANTITY_VERB_PATTERN = new RegExp(
  `\\b(?:produce|manufacture|supply|deliver|provide|make)\\s+(${NUMBER_WORD_PATTERN})\\b`,
  "i"
);
// Mirrors QUANTITY_OPENING_PATTERN for the productOrCategory remainder
// (see below): by the time that code runs, the opening filler phrase
// itself has already been stripped off the front of the remainder, so
// what's left to strip is just the bare number sitting at the new start.
const QUANTITY_OPENING_STRIP_PATTERN = new RegExp(`^(?:${NUMBER_WORD_PATTERN})\\s+`, "i");

// "months"/"years" added alongside the original days/weeks/hours — a
// real buyer's timeline is at least as likely to be stated in months as
// in days. Same adjacency rule as before: only an explicit number
// directly next to a real time unit counts.
const TIMELINE_PATTERN = new RegExp(
  `\\b(?:within\\s+)?(${NUMBER_WORD_PATTERN})\\s+(days?|weeks?|months?|years?|hours?)\\b`,
  "i"
);

// Requires the word "budget" itself — never inferred from a bare number
// anywhere in the sentence (that number could just as easily be a
// quantity or a year). An optional currency token may sit on either
// side of the number ("budget 20000 USD", "budget: $20,000", "budget of
// ₹50000"); the field stores whichever one was actually present so
// nothing is invented that wasn't typed.
const BUDGET_PATTERN = new RegExp(
  `\\bbudget\\s*(?:of|is|:)?\\s*(${CURRENCY_PATTERN})?\\s*(${NUMBER_WORD_PATTERN})\\s*(${CURRENCY_PATTERN})?\\b`,
  "i"
);

function matchQuantity(text: string): RegExpMatchArray | null {
  return (
    text.match(QUANTITY_UNIT_PATTERN) ??
    text.match(QUANTITY_LABEL_PATTERN) ??
    text.match(QUANTITY_OPENING_PATTERN) ??
    text.match(QUANTITY_VERB_PATTERN)
  );
}

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
  // Set alongside next.quantity below, holding the exact substring that
  // matched (e.g. "5,000", not the normalized "5000"; or "five", not the
  // normalized "5") — the productOrCategory remainder-stripping logic
  // further down needs the literal text that's actually still sitting in
  // the sentence, not the normalized value, to find and remove it.
  let quantityRawToken: string | null = null;

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

  if (next.city.value === null) {
    const match = KNOWN_CITIES.find((c) => new RegExp(`\\b${c}\\b`, "i").test(text));
    if (match) {
      next.city = { value: titleCase(match), confidence: "explicit" };
    }
  }

  if (next.quantity.value === null) {
    // Requires the number to sit directly next to a real unit-of-goods
    // word ("1 unit", "one piece") or a "quantity"/"qty" label
    // ("quantity 500") — deliberately stricter than a bare "any 2+
    // digit number anywhere" rule (which would also have wrongly
    // captured e.g. "5" from "within 5 days"), while also covering the
    // single-item/word-form case a bare digit-count rule missed
    // entirely. Still never invents a number that wasn't typed.
    const quantityMatch = matchQuantity(text);
    if (quantityMatch) {
      // Non-null: group 1 is a required (non-"?") capture in both
      // QUANTITY_UNIT_PATTERN and QUANTITY_LABEL_PATTERN, so a truthy
      // overall match guarantees it matched too — TS just can't derive
      // that from the regex source itself.
      quantityRawToken = quantityMatch[1]!;
      next.quantity = { value: numberTokenToDigits(quantityMatch[1]!), confidence: "explicit" };
    }
  }

  if (next.timeline.value === null) {
    // Same adjacency principle as quantity: only an explicit number
    // directly next to a real time unit counts. A vague phrase like
    // "quickly"/"ASAP"/"urgently" matches nothing here and stays
    // missing — never guessed into an invented day count.
    const timelineMatch = text.match(TIMELINE_PATTERN);
    if (timelineMatch) {
      // Non-null: both groups are required captures in TIMELINE_PATTERN.
      next.timeline = {
        value: `${numberTokenToDigits(timelineMatch[1]!)} ${timelineMatch[2]!.toLowerCase()}`,
        confidence: "explicit",
      };
    }
  }

  if (next.budget.value === null) {
    // Requires the word "budget" itself — see BUDGET_PATTERN's own
    // comment above for why a bare number is never enough.
    const budgetMatch = text.match(BUDGET_PATTERN);
    if (budgetMatch) {
      // Groups 1 and 3 (currency) are genuinely optional in the
      // pattern — only group 2 (the amount) is required.
      const currency = (budgetMatch[1] ?? budgetMatch[3])?.toUpperCase().replace(/\.$/, "");
      const amount = numberTokenToDigits(budgetMatch[2]!);
      next.budget = { value: currency ? `${amount} ${currency}` : amount, confidence: "explicit" };
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
      // Strip a leading preposition together with the country/city itself
      // ("near Delhi", "in India") as one unit where present — otherwise
      // the preposition is left dangling mid-sentence once its object is
      // gone (only the *trailing* case was handled below; "near Delhi who
      // can…" doesn't end the sentence, so that check never caught it).
      // The plain bare-name strip right after is a no-op once the
      // preposition+name form already matched, and still catches the
      // (less common) case where no preposition preceded the name at all.
      remainder = remainder.replace(new RegExp(`\\b(?:in|near|at)\\s+${next.country.value}\\b`, "gi"), "").trim();
      remainder = remainder.replace(new RegExp(`\\b${next.country.value}\\b`, "gi"), "").trim();
    }
    if (next.city.value) {
      remainder = remainder.replace(new RegExp(`\\b(?:in|near|at)\\s+${next.city.value}\\b`, "gi"), "").trim();
      remainder = remainder.replace(new RegExp(`\\b${next.city.value}\\b`, "gi"), "").trim();
    }
    if (next.quantity.value) {
      remainder = remainder
        .replace(new RegExp(QUANTITY_UNIT_PATTERN, "gi"), "")
        .replace(new RegExp(QUANTITY_LABEL_PATTERN, "gi"), "")
        // The opening filler phrase itself was already stripped off the
        // front of `remainder` above, so a quantity captured via
        // QUANTITY_OPENING_PATTERN now shows up as a bare number at the
        // new start of `remainder` ("500 stainless steel ball valves…") —
        // strip just that.
        .replace(QUANTITY_OPENING_STRIP_PATTERN, "")
        .trim();
      if (quantityRawToken) {
        // QUANTITY_VERB_PATTERN's own verb half ("produce", "manufacture"…)
        // is also a ROLE_KEYWORDS entry, already stripped above — leaving
        // just the bare number sitting mid-sentence ("who can  5,000
        // stainless-steel…"). None of the three patterns above match that
        // shape, so strip the literal matched token directly.
        remainder = remainder.replace(new RegExp(`\\b${quantityRawToken}\\b`, "i"), "").trim();
      }
    }
    if (next.timeline.value) {
      remainder = remainder.replace(new RegExp(TIMELINE_PATTERN, "gi"), "").trim();
    }
    if (next.budget.value) {
      remainder = remainder.replace(new RegExp(BUDGET_PATTERN, "gi"), "").trim();
    }
    if (next.certifications.value && next.certifications.value.length > 0) {
      // Same "strip whatever this pass already recognized" principle as
      // the role-keyword strip above — a certification keyword found by
      // the extraction block earlier in this function is a label, not
      // part of the product/category description.
      for (const key of Object.keys(KNOWN_CERTIFICATIONS)) {
        // Strips "ISO-certified"/"ISO certified" as one unit, not just
        // the bare "ISO" — otherwise a hyphenated compound like
        // "ISO-certified" leaves an orphaned "-certified" fragment (the
        // hyphen itself already counts as a word boundary, so `\bISO\b`
        // alone matches and removes only the letters, not the suffix
        // riding along with it). Still matches plain "ISO" with no
        // suffix exactly as before.
        remainder = remainder
          .replace(new RegExp(`\\b${key}(?:[- ]?(?:certified|approved|compliant))?\\b`, "gi"), "")
          .trim();
      }
    }
    // Strip connective clauses and bare field labels left dangling once
    // the fields above are removed ("preferably in", "delivered
    // within", "and I need it quickly", the standalone word "timeline"
    // once its "2 months" has already been stripped, a relative clause
    // like "who can"/"that can" once the verb it led into is gone) —
    // same "simple text-stripping, not sentence understanding"
    // principle as the rest of this function; never affects which
    // fields were actually extracted, only how the leftover
    // product/category text reads.
    remainder = remainder
      .replace(
        /\b(preferably|delivered|and i need it \w+|quantity|qty|budget|timeline|who can|that can|which can)\b/gi,
        ""
      )
      .trim();
    // A leading article ("a manufacturer" -> "a" once "manufacturer" is
    // stripped above) reads as noise in front of a product/category
    // description — only stripped at the very start, never mid-sentence,
    // so a genuine product name is never touched.
    remainder = remainder.replace(/^(?:a|an|the)\s+/i, "").trim();
    // Collapse any run of two-or-more commas (left behind wherever a
    // field sat between two other stripped fields, e.g. "heater , ,
    // budget...") down to one — the original single-pair version of
    // this only handled exactly two consecutive commas, which sufficed
    // before a sentence could have more than one of quantity/budget/
    // timeline extracted out of it at once.
    remainder = remainder.replace(/,(?:\s*,)+/g, ",").trim();
    // Strip a preposition left dangling after removing the country
    // (e.g. "CNC machining in" once "India" is removed) — this isn't
    // cosmetic: a trailing word here would break the real ILIKE
    // substring match against the industry field once used in search.
    remainder = remainder.replace(/\s+(in|for|from|at|near)\s*$/i, "").trim();
    remainder = remainder.replace(/^[,\s]+|[,\s]+$/g, "").trim();
    remainder = remainder.replace(/[.,!?]+$/, "").trim();
    // Every strip above leaves a gap rather than closing it up (e.g. "a
    // manufacturer" -> "a  " once "manufacturer" alone is removed) —
    // collapse any run of internal whitespace left behind by the whole
    // pipeline into a single space, as a final pass rather than after
    // every individual strip.
    remainder = remainder.replace(/\s{2,}/g, " ").trim();
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

const CATEGORY_WORD_PATTERN = /[a-z0-9]+/g;

function normalizeCategoryWords(text: string): string[] {
  return text.toLowerCase().match(CATEGORY_WORD_PATTERN) ?? [];
}

/**
 * Deterministic, rule-based singular normalization — NOT a stemming
 * library, NOT fuzzy/semantic matching. Strips exactly the common
 * English plural inflections (heaters -> heater, lehengas -> lehenga,
 * categories -> category) so a category name and a buyer's plural
 * phrasing of it compare equal after normalization; the comparison
 * itself in resolveCategoryId is still plain exact-string equality,
 * only the input token is normalized first. Guarded against the
 * obvious false-positive shapes so it stays conservative:
 *   - words of length <= 3 are left alone (avoids "gas" -> "ga")
 *   - a double-s ending is left alone (avoids "glass" -> "glas")
 *   - a word already ending "us"/"ss" is left alone
 * This intentionally does not attempt irregular plurals (e.g.
 * "boxes" -> "box") — those fall back to requiring the exact word,
 * which is the same honest "no match found" behavior as today rather
 * than a guess.
 */
function singularize(word: string): string {
  if (word.length <= 3) return word;
  if (word.endsWith("ies") && word.length > 4) return word.slice(0, -3) + "y";
  if (/(?:s|x|z|ch|sh)es$/.test(word)) return word.slice(0, -2);
  if (word.endsWith("ss") || word.endsWith("us")) return word;
  if (word.endsWith("s")) return word.slice(0, -1);
  return word;
}

/**
 * Deterministic, keyword-based category resolution — the same
 * whole-word/whole-phrase philosophy as the backend's own
 * requirement_matching_service._label_present (never a blind substring
 * match, never NLP/an LLM/embeddings). The real Module 7A-2 matching
 * engine requires a `product_category_id` to run at all (it returns
 * `status: "category_required"` otherwise) — this only resolves *which*
 * existing category the user's free text refers to; it never scores or
 * ranks anything itself, so it doesn't duplicate backend matching
 * logic.
 *
 * Word comparison is done on the singularized form of every token (see
 * `singularize` above), so "room heaters" matches a "Room Heater"
 * category and vice versa — still exact-equality matching, just on a
 * normalized token, never a fuzzy/similarity score.
 *
 * Returns null when no category's full name appears as a contiguous
 * word sequence in the requirement text — an honest "unknown", not a
 * guess. The real backend's own `category_required` status is what
 * surfaces that to the user; this function never fabricates a
 * best-effort match. When more than one category name matches, the
 * longest (most specific) name wins — a deterministic tie-break, same
 * spirit as the backend's own tie-break rules.
 */
export function resolveCategoryId(categories: ProductCategory[], text: string): string | null {
  const requirementWords = normalizeCategoryWords(text).map(singularize);
  if (requirementWords.length === 0) return null;

  let best: { id: string; wordCount: number } | null = null;
  for (const category of categories) {
    const nameWords = normalizeCategoryWords(category.name).map(singularize);
    const n = nameWords.length;
    if (n === 0 || n > requirementWords.length) continue;
    const found = Array.from({ length: requirementWords.length - n + 1 }, (_, i) => i).some((i) =>
      nameWords.every((word, j) => requirementWords[i + j] === word)
    );
    if (found && (best === null || n > best.wordCount)) {
      best = { id: category.id, wordCount: n };
    }
  }
  return best?.id ?? null;
}
