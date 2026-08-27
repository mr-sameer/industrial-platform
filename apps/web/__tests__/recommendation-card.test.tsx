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
    expect(screen.getByText("Bore diameter")).toBeTruthy();
    expect(screen.getByText("Unknown")).toBeTruthy();
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
});
