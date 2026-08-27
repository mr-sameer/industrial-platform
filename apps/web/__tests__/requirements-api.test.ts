import { afterEach, describe, expect, it, vi } from "vitest";

import { createRequirement, getRequirementMatches } from "@/lib/requirements-api";

/**
 * Verifies the Module 7A-1/7A-2 API client sends the real backend
 * contract exactly: POST /api/v1/requirements with the raw payload and
 * a Bearer auth header, and GET /api/v1/requirements/{id}/matches with
 * the same auth header — mirroring __tests__/companies-search.test.ts's
 * own pattern for lib/companies.ts.
 */
describe("requirements-api", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("createRequirement POSTs the payload with a Bearer auth header", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 201,
      json: async () => ({
        success: true,
        data: { id: "req-1" },
        meta: { requestId: "x", timestamp: "now" },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const payload = { raw_query: "Need CNC machining", criteria: [] };
    await createRequirement(payload, "token-abc");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/requirements");
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer token-abc");
    expect(JSON.parse(init.body as string)).toEqual(payload);
  });

  it("getRequirementMatches GETs the matches endpoint with a Bearer auth header", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      json: async () => ({
        success: true,
        data: {
          requirement_id: "req-1",
          status: "computed",
          total_candidates_considered: 0,
          more_candidates_may_exist: false,
          excluded_for_hard_criteria: 0,
          returned_count: 0,
          matches: [],
        },
        meta: { requestId: "x", timestamp: "now" },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await getRequirementMatches("req-1", "token-abc");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/requirements/req-1/matches");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer token-abc");
  });

  it("propagates a network failure as a NETWORK_ERROR response rather than throwing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("connection refused"))
    );

    const result = await createRequirement({ raw_query: "x", criteria: [] }, "token-abc");

    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.code).toBe("NETWORK_ERROR");
    }
  });
});
