import { afterEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "@/lib/api-client";

/**
 * Regression test: apiFetch previously called res.json() unconditionally,
 * which throws on a 204 No Content response's empty body (e.g. every
 * Module 3A DELETE endpoint). See the fix in src/lib/api-client.ts.
 */
describe("apiFetch 204 handling", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns a success envelope for a 204 response instead of throwing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 204,
        json: async () => {
          throw new Error("should not be called for a 204 response");
        },
      })
    );

    const result = await apiFetch("/api/v1/companies/some-id");
    expect(result.success).toBe(true);
  });

  it("still parses a normal JSON body for a 200 response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 200,
        json: async () => ({
          success: true,
          data: { hello: "world" },
          meta: { requestId: "x", timestamp: "now" },
        }),
      })
    );

    const result = await apiFetch<{ hello: string }>("/api/v1/companies/some-id");
    expect(result.success).toBe(true);
    if (result.success) expect(result.data.hello).toBe("world");
  });
});
