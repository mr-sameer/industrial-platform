import type { RequirementMatchCandidate } from "@platform/shared-types";
import { describe, expect, it } from "vitest";

import { encodeMatchContext, parseMatchContext } from "@/lib/company-match-context";

/**
 * P0 #3 (Buyer UX Audit): the public company profile page carries
 * procurement/evidence data over from the Consult match card via a URL
 * query param, since that data (offering.moq/lead_time/capacity,
 * evidence, certifications) is scoped to a specific requirement match,
 * not something the company-slug endpoint returns. Because it travels
 * through a URL, parseMatchContext treats it as untrusted input — these
 * tests cover both the honest round trip and the malicious/malformed
 * cases it must not blow up or open an XSS vector on.
 */

function buildMatch(overrides: Partial<RequirementMatchCandidate> = {}): RequirementMatchCandidate {
  return {
    offering_id: "off-1",
    rank: 1,
    score: 78,
    company: { id: "co-1", name: "ABC Engineering", slug: "abc-engineering", verification_level: "business_verified" },
    product: { id: "prod-1", name: "Hydraulic Cylinder", slug: "hydraulic-cylinder" },
    signals: {
      category: { matched: true },
      criteria: [],
      location: { requested: {}, candidate: {}, points_earned: 0, points_possible: 0 },
      certifications: {
        requested: ["ISO"],
        evidence_found: ["ISO"],
        points_earned: 20,
        points_possible: 20,
        confidence: "low",
        note: null,
      },
      trust_tier: { level: "business_verified", points_earned: 25, points_possible: 50 },
    },
    score_breakdown: [],
    offering: { role: "manufacturer", verification_status: "unverified", moq: "1 Piece", lead_time: "2 Days", capacity: null },
    evidence: [
      { field_name: "moq", value_observed: "1 Piece", status: "observed", source_url: "https://example.com/listing" },
    ],
    ...overrides,
  };
}

describe("encodeMatchContext / parseMatchContext round trip", () => {
  it("carries MOQ, lead time, capacity, certifications, and evidence through unchanged", () => {
    const encoded = encodeMatchContext(buildMatch());
    const parsed = parseMatchContext(encoded);
    expect(parsed).not.toBeNull();
    expect(parsed?.moq).toBe("1 Piece");
    expect(parsed?.leadTime).toBe("2 Days");
    expect(parsed?.capacity).toBeNull();
    expect(parsed?.certificationsRequested).toEqual(["ISO"]);
    expect(parsed?.certificationsEvidenceFound).toEqual(["ISO"]);
    expect(parsed?.evidence).toEqual([
      { fieldName: "moq", valueObserved: "1 Piece", status: "observed", sourceUrl: "https://example.com/listing" },
    ]);
  });

  it("never upgrades an observed evidence status to verified", () => {
    const parsed = parseMatchContext(encodeMatchContext(buildMatch()));
    expect(parsed?.evidence[0]?.status).toBe("observed");
  });
});

describe("parseMatchContext with untrusted/malformed input", () => {
  it("returns null for undefined, empty, non-JSON, or array-of-strings input", () => {
    expect(parseMatchContext(undefined)).toBeNull();
    expect(parseMatchContext("")).toBeNull();
    expect(parseMatchContext("not json")).toBeNull();
    expect(parseMatchContext(["a", "b"])).toBeNull();
  });

  it("returns null when required fields are missing", () => {
    expect(parseMatchContext(JSON.stringify({ moq: "1" }))).toBeNull();
  });

  it("drops a javascript: source_url instead of surfacing it as a clickable link", () => {
    const malicious = JSON.stringify({
      productName: "X",
      role: "manufacturer",
      evidence: [
        { fieldName: "moq", valueObserved: "1", status: "observed", sourceUrl: "javascript:alert(1)" },
      ],
    });
    const parsed = parseMatchContext(malicious);
    expect(parsed?.evidence[0]?.sourceUrl).toBeNull();
  });

  it("keeps a real https source_url", () => {
    const raw = JSON.stringify({
      productName: "X",
      role: "manufacturer",
      evidence: [{ fieldName: "moq", valueObserved: "1", status: "observed", sourceUrl: "https://good.example" }],
    });
    expect(parseMatchContext(raw)?.evidence[0]?.sourceUrl).toBe("https://good.example");
  });

  it("ignores non-object evidence entries and non-string certification entries rather than throwing", () => {
    const raw = JSON.stringify({
      productName: "X",
      role: "manufacturer",
      certificationsRequested: ["ISO", 42, null],
      evidence: ["not-an-object", { fieldName: "moq", valueObserved: "1" }],
    });
    const parsed = parseMatchContext(raw);
    expect(parsed?.certificationsRequested).toEqual(["ISO"]);
    expect(parsed?.evidence).toHaveLength(1);
    expect(parsed?.evidence[0]?.status).toBe("observed"); // defaulted, never fabricated as "verified"
  });
});
