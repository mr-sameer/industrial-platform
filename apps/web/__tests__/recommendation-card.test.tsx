import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RecommendationCard } from "@/components/consult/RecommendationCard";
import type { RequirementMatchCandidate } from "@platform/shared-types";

function buildMatch(overrides: Partial<RequirementMatchCandidate> = {}): RequirementMatchCandidate {
  return {
    offering_id: "off-1",
    rank: 1,
    score: 78,
    company: {
      id: "co-1",
      name: "ABC Engineering",
      slug: "abc-engineering",
      verification_level: "business_verified",
    },
    product: { id: "prod-1", name: "Hydraulic Cylinder", slug: "hydraulic-cylinder" },
    signals: {
      category: { matched: true },
      criteria: [],
      location: {
        requested: { country: "India", state: null, city: null },
        candidate: { country: "India", state: "Maharashtra", city: "Pune" },
        points_earned: 15,
        points_possible: 30,
      },
      certifications: {
        requested: [],
        evidence_found: [],
        points_earned: 0,
        points_possible: 0,
        confidence: "low",
        note: null,
      },
      trust_tier: { level: "business_verified", points_earned: 25, points_possible: 50 },
    },
    score_breakdown: [
      { signal: "trust_tier", weight: 50, points_earned: 25 },
      { signal: "location", weight: 30, points_earned: 15 },
      { signal: "certifications", weight: 20, points_earned: 0 },
    ],
    offering: { role: "manufacturer", moq: null, lead_time: null, capacity: null },
    evidence: [],
    ...overrides,
  };
}

describe("RecommendationCard", () => {
  it("renders the real score, company, and product from the match contract", () => {
    render(<RecommendationCard match={buildMatch()} />);
    expect(screen.getByText("ABC Engineering")).toBeTruthy();
    expect(screen.getByText("Hydraulic Cylinder")).toBeTruthy();
    expect(screen.getByText("78% match")).toBeTruthy();
  });

  it("renders the score breakdown points earned vs. possible for every signal", () => {
    render(<RecommendationCard match={buildMatch()} />);
    expect(screen.getByText("25/50 pts")).toBeTruthy();
    expect(screen.getByText("15/30 pts")).toBeTruthy();
  });

  it("shows an honest Unknown state for a criterion with no candidate evidence, never a fabricated match", () => {
    const match = buildMatch({
      signals: {
        ...buildMatch().signals,
        criteria: [
          {
            specification_id: "spec-1",
            specification_name: "Bore diameter",
            operator: "gte",
            requirement_value: 50,
            candidate_value: null,
            status: "matched",
          },
        ],
      },
    });
    render(<RecommendationCard match={match} />);
    const label = screen.getByText("Bore diameter");
    expect(label.parentElement?.textContent).toContain("Unknown");
  });

  it("renders a requested certification with no VERIFIED evidence as explicitly unmet, not silently dropped", () => {
    const match = buildMatch({
      signals: {
        ...buildMatch().signals,
        certifications: {
          requested: ["ISO"],
          evidence_found: [],
          points_earned: 0,
          points_possible: 20,
          confidence: "low",
          note: "No VERIFIED evidence found for any requested certification.",
        },
      },
    });
    render(<RecommendationCard match={match} />);
    expect(screen.getByText(/ISO/)).toBeTruthy();
    expect(screen.getByText(/no VERIFIED evidence found/)).toBeTruthy();
  });

  it("renders a found certification as met", () => {
    const match = buildMatch({
      signals: {
        ...buildMatch().signals,
        certifications: {
          requested: ["ISO"],
          evidence_found: ["ISO"],
          points_earned: 20,
          points_possible: 20,
          confidence: "low",
          note: null,
        },
      },
    });
    render(<RecommendationCard match={match} />);
    expect(screen.getByText("ISO")).toBeTruthy();
    expect(screen.queryByText(/no VERIFIED evidence found/)).toBeNull();
  });

  it("renders the manufacturer/supplier role from the real Offering", () => {
    render(<RecommendationCard match={buildMatch({ offering: { role: "manufacturer", moq: null, lead_time: null, capacity: null } })} />);
    expect(screen.getByText("Manufacturer")).toBeTruthy();
  });

  it("renders MOQ and lead time as Observed when the real Offering has them", () => {
    const match = buildMatch({
      offering: { role: "manufacturer", moq: "1 Piece", lead_time: "2 Days", capacity: null },
    });
    render(<RecommendationCard match={match} />);
    expect(screen.getByText("1 Piece")).toBeTruthy();
    expect(screen.getByText("2 Days")).toBeTruthy();
    expect(screen.getAllByText("Observed").length).toBeGreaterThanOrEqual(2);
  });

  it("renders MOQ and lead time as honest Unknown when the Offering doesn't have them, never fabricating a value", () => {
    const match = buildMatch({ offering: { role: "manufacturer", moq: null, lead_time: null, capacity: null } });
    render(<RecommendationCard match={match} />);
    expect(screen.getByText("Minimum order quantity").parentElement?.textContent).toContain("Unknown");
    expect(screen.getByText("Published lead time").parentElement?.textContent).toContain("Unknown");
  });

  it("only renders capacity when the Offering actually has it, per the 'only if available' rule", () => {
    const withoutCapacity = buildMatch({ offering: { role: "manufacturer", moq: "1 Piece", lead_time: "2 Days", capacity: null } });
    const { rerender } = render(<RecommendationCard match={withoutCapacity} />);
    expect(screen.queryByText("Supply capacity")).toBeNull();

    const withCapacity = buildMatch({ offering: { role: "manufacturer", moq: "1 Piece", lead_time: "2 Days", capacity: "1 Piece Per Day" } });
    rerender(<RecommendationCard match={withCapacity} />);
    expect(screen.getByText("Supply capacity")).toBeTruthy();
    expect(screen.getByText("1 Piece Per Day")).toBeTruthy();
  });

  it("never labels an Observed fact as Verified — only a backend status of 'verified' produces a Verified badge", () => {
    const match = buildMatch({
      evidence: [
        {
          field_name: "certification_claim",
          value_observed: "ISO 9001:2015 — seller-published trade-term claim only. NOT independently verified.",
          status: "observed",
          source_url: "https://www.aquabathcornershelf.com/jacuzzi-bath-tub-5103849.html",
        },
      ],
    });
    render(<RecommendationCard match={match} />);
    expect(screen.getByText("Certification claim")).toBeTruthy();
    expect(screen.getByText(/NOT independently verified/)).toBeTruthy();
    expect(screen.queryByText("Verified")).toBeNull();
    expect(screen.getAllByText("Observed").length).toBeGreaterThanOrEqual(1);
  });

  it("renders a Verified badge only when the backend itself reports status='verified'", () => {
    const match = buildMatch({
      evidence: [
        {
          field_name: "gst_number",
          value_observed: "07CPRPB3439L1ZI",
          status: "verified",
          source_url: null,
        },
      ],
    });
    render(<RecommendationCard match={match} />);
    expect(screen.getByText("Verified")).toBeTruthy();
  });

  it("renders evidence source citations as real links", () => {
    const match = buildMatch({
      evidence: [
        {
          field_name: "product_line",
          value_observed: "Jacuzzi Bathtub, Hydrotherapy Bathtub, Acrylic Bathtub",
          status: "observed",
          source_url: "https://www.tradeindia.com/aquabath-23925485/",
        },
      ],
    });
    render(<RecommendationCard match={match} />);
    const link = screen.getByText("Source").closest("a");
    expect(link).toBeTruthy();
    expect(link?.getAttribute("href")).toBe("https://www.tradeindia.com/aquabath-23925485/");
    expect(link?.getAttribute("target")).toBe("_blank");
  });

  it("does not render a source link when no source_url exists, rather than fabricating one", () => {
    const match = buildMatch({
      evidence: [{ field_name: "moq", value_observed: "1 Piece", status: "observed", source_url: null }],
    });
    render(<RecommendationCard match={match} />);
    expect(screen.queryByText("Source")).toBeNull();
  });

  it("honestly states when no evidence exists at all for a product, rather than hiding the gap", () => {
    render(<RecommendationCard match={buildMatch({ evidence: [] })} />);
    expect(screen.getByText(/No cited evidence on file/)).toBeTruthy();
  });
});
