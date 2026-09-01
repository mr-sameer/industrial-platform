import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import PublicCompanyProfilePage from "@/app/company/[slug]/page";
import { getCompanyBySlug } from "@/lib/companies";

/**
 * P0 #3 (Buyer UX Audit): the public company profile was nearly empty —
 * it didn't carry over MOQ/lead time/capacity/certifications/evidence
 * already shown on the Consult match card. This covers the page actually
 * rendering that "from your search" section when a `?match=` param is
 * present, and staying exactly as before when it isn't (a plain,
 * unrelated visit to the profile link shouldn't show a search-scoped
 * section that has no meaning outside that search).
 */
vi.mock("@/lib/companies", () => ({
  getCompanyBySlug: vi.fn(),
}));

const okMeta = { requestId: "x", timestamp: "now" };

const company = {
  id: "co-1",
  name: "ABC Engineering",
  slug: "abc-engineering",
  description: null,
  industry: "Manufacturing",
  website: null,
  country: "India",
  city: "Pune",
  verification_status: "verified" as const,
  member_count: 3,
  created_at: "2024-01-01T00:00:00Z",
};

describe("Public company profile — carried-over match context", () => {
  it("renders MOQ, lead time, certifications, and evidence when a valid ?match= param is present", async () => {
    vi.mocked(getCompanyBySlug).mockResolvedValue({ success: true, data: company, meta: okMeta });
    const match = {
      productName: "Hydraulic Cylinder",
      role: "manufacturer",
      moq: "1 Piece",
      leadTime: "2 Days",
      capacity: null,
      certificationsRequested: ["ISO"],
      certificationsEvidenceFound: ["ISO"],
      evidence: [
        { fieldName: "moq", valueObserved: "1 Piece", status: "observed", sourceUrl: "https://example.com" },
      ],
    };

    const jsx = await PublicCompanyProfilePage({
      params: { slug: "abc-engineering" },
      searchParams: { match: JSON.stringify(match) },
    });
    render(jsx);

    expect(screen.getByText("Procurement details from your search")).toBeTruthy();
    // "1 Piece" legitimately appears twice: once as the MOQ fact, once as
    // the cited evidence row's value for that same fact.
    expect(screen.getAllByText("1 Piece").length).toBe(2);
    expect(screen.getByText("2 Days")).toBeTruthy();
    expect(screen.getByText(/ISO/)).toBeTruthy();
    expect(screen.getByText("Source").closest("a")?.getAttribute("href")).toBe("https://example.com");
  });

  it("omits the section entirely on a plain profile visit with no match param", async () => {
    vi.mocked(getCompanyBySlug).mockResolvedValue({ success: true, data: company, meta: okMeta });

    const jsx = await PublicCompanyProfilePage({
      params: { slug: "abc-engineering" },
      searchParams: {},
    });
    render(jsx);

    expect(screen.queryByText("Procurement details from your search")).toBeNull();
    expect(screen.getByText("ABC Engineering")).toBeTruthy();
  });

  it("omits the section for a malformed/malicious match param instead of crashing", async () => {
    vi.mocked(getCompanyBySlug).mockResolvedValue({ success: true, data: company, meta: okMeta });

    const jsx = await PublicCompanyProfilePage({
      params: { slug: "abc-engineering" },
      searchParams: { match: "<script>alert(1)</script>" },
    });
    render(jsx);

    expect(screen.queryByText("Procurement details from your search")).toBeNull();
    expect(screen.getByText("ABC Engineering")).toBeTruthy();
  });
});
