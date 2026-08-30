import { afterEach, describe, expect, it, vi } from "vitest";

import { searchCompanies } from "@/lib/companies";
import { discoverCompanies } from "@/lib/discover";
import { getProductOfferings, searchProducts } from "@/lib/products";

/**
 * Regression coverage for the ForgeX Product Audit's P0 #4: /discover
 * only ever searched company identity fields (name/industry/city/
 * country), so a buyer typing the exact product term a company sells
 * ("room heater") got "0 found" even though the same term matches a
 * real company through Consult's Product Graph seconds later. These
 * tests cover the fifth, product-name-aware path added alongside the
 * four existing (unmodified) identity-field searches — never the
 * Requirement Intelligence matching/scoring engine itself.
 */

vi.mock("@/lib/companies", () => ({
  searchCompanies: vi.fn(),
}));

vi.mock("@/lib/products", () => ({
  searchProducts: vi.fn(),
  getProductOfferings: vi.fn(),
}));

vi.mock("@/lib/company-verification", () => ({
  getPublicVerification: vi.fn(),
}));

const emptyCompanyPage = {
  success: true as const,
  data: { items: [], total: 0, page: 1, page_size: 50, total_pages: 1 },
  meta: { requestId: "x", timestamp: "now" },
};

const noProducts = {
  success: true as const,
  data: { items: [], total: 0, page: 1, page_size: 5, total_pages: 1 },
  meta: { requestId: "x", timestamp: "now" },
};

describe("discoverCompanies — product-name match (ForgeX Product Audit P0 #4)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("finds a company by the exact product it sells, even when none of its own identity fields match", async () => {
    vi.mocked(searchCompanies).mockResolvedValue(emptyCompanyPage);
    vi.mocked(searchProducts).mockResolvedValue({
      success: true,
      data: {
        items: [
          { id: "prod-1", name: "Room Heater", slug: "room-heater", product_family: null, category_id: "cat-1", industry: null, status: "published", offering_count: 1 },
        ],
        total: 1,
        page: 1,
        page_size: 5,
        total_pages: 1,
      },
      meta: { requestId: "x", timestamp: "now" },
    });
    vi.mocked(getProductOfferings).mockResolvedValue({
      success: true,
      data: {
        items: [
          {
            id: "off-1",
            company: { id: "co-1", name: "SN PHINICS PRIVATE LIMITED", slug: "sn-phinics-private-limited", verification_status: "unverified" },
            product: { id: "prod-1", name: "Room Heater", slug: "room-heater" },
            role: "manufacturer",
            moq: null,
            lead_time: null,
            capacity: null,
            country: "India",
            verification_status: "unverified",
            status: "active",
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      },
      meta: { requestId: "x", timestamp: "now" },
    });

    const { results, total } = await discoverCompanies("room heater", 1, 10);

    expect(total).toBe(1);
    expect(results).toHaveLength(1);
    expect(results[0]!.company.name).toBe("SN PHINICS PRIVATE LIMITED");
    expect(results[0]!.company.country).toBe("India");
    expect(results[0]!.matchedFields).toContain("product");
  });

  it("returns honestly empty when neither identity fields nor any product name match", async () => {
    vi.mocked(searchCompanies).mockResolvedValue(emptyCompanyPage);
    vi.mocked(searchProducts).mockResolvedValue(noProducts);

    const { results, total } = await discoverCompanies("zzzznonexistentxyz", 1, 10);

    expect(total).toBe(0);
    expect(results).toHaveLength(0);
    expect(getProductOfferings).not.toHaveBeenCalled();
  });

  it("prefers the fuller identity-field record over the thinner product-match one for the same company", async () => {
    vi.mocked(searchCompanies).mockImplementation((params) => {
      if (params.name === "aquabath") {
        return Promise.resolve({
          success: true,
          data: {
            items: [{ id: "co-1", name: "AQUABATH", slug: "aquabath", industry: "Bathroom Fixtures", city: "Delhi", country: "India", verification_status: "verified" }],
            total: 1,
            page: 1,
            page_size: 50,
            total_pages: 1,
          },
          meta: { requestId: "x", timestamp: "now" },
        });
      }
      return Promise.resolve(emptyCompanyPage);
    });
    vi.mocked(searchProducts).mockResolvedValue({
      success: true,
      data: {
        items: [{ id: "prod-1", name: "Aquabath Jacuzzi", slug: "aquabath-jacuzzi", product_family: null, category_id: "cat-1", industry: null, status: "published", offering_count: 1 }],
        total: 1,
        page: 1,
        page_size: 5,
        total_pages: 1,
      },
      meta: { requestId: "x", timestamp: "now" },
    });
    vi.mocked(getProductOfferings).mockResolvedValue({
      success: true,
      data: {
        items: [
          {
            id: "off-1",
            company: { id: "co-1", name: "AQUABATH", slug: "aquabath", verification_status: "verified" },
            product: { id: "prod-1", name: "Aquabath Jacuzzi", slug: "aquabath-jacuzzi" },
            role: "manufacturer",
            moq: null,
            lead_time: null,
            capacity: null,
            country: "India",
            verification_status: "unverified",
            status: "active",
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      },
      meta: { requestId: "x", timestamp: "now" },
    });

    const { results } = await discoverCompanies("aquabath", 1, 10);

    expect(results).toHaveLength(1);
    // The company's real industry/city — from the identity-field
    // match — must survive, not be overwritten by the product-match
    // path's industry:null/city:null placeholder.
    expect(results[0]!.company.industry).toBe("Bathroom Fixtures");
    expect(results[0]!.company.city).toBe("Delhi");
    expect(results[0]!.matchedFields).toContain("name");
    expect(results[0]!.matchedFields).toContain("product");
  });
});
