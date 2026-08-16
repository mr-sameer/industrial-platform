import { afterEach, describe, expect, it, vi } from "vitest";

import { searchCompanies } from "@/lib/companies";

/**
 * Verifies searchCompanies builds the query string correctly — in
 * particular that empty/undefined filter values are omitted rather than
 * sent as literal "undefined"/"" query params (which would make the API
 * filter for a literal empty string instead of "no filter").
 */
describe("searchCompanies query string building", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("omits empty and undefined params from the query string", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      json: async () => ({
        success: true,
        data: { items: [], total: 0, page: 1, page_size: 20, total_pages: 1 },
        meta: { requestId: "x", timestamp: "now" },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await searchCompanies({ name: "Acme", industry: "", country: undefined, page: 1 });

    const calledUrl = fetchMock.mock.calls[0]?.[0] as string;
    expect(calledUrl).toContain("name=Acme");
    expect(calledUrl).toContain("page=1");
    expect(calledUrl).not.toContain("industry=");
    expect(calledUrl).not.toContain("country=");
  });

  it("sends no query string at all when every filter is empty", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      json: async () => ({
        success: true,
        data: { items: [], total: 0, page: 1, page_size: 20, total_pages: 1 },
        meta: { requestId: "x", timestamp: "now" },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await searchCompanies({});

    const calledUrl = fetchMock.mock.calls[0]?.[0] as string;
    expect(calledUrl.endsWith("/companies/search")).toBe(true);
  });
});
