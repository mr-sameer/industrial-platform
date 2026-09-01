import { afterEach, describe, expect, it, vi } from "vitest";

import { listPendingDocuments, reviewDocument } from "@/lib/admin-verification";

/**
 * Phase 2B-1: the admin verification queue's API client. Same
 * fetch-mocking convention as __tests__/company-slug-base-url.test.ts —
 * stub global fetch, inspect the actual request fetch() was called
 * with, rather than asserting on lib/admin-verification.ts's return
 * value (which is just apiFetch's existing, already-tested envelope
 * handling).
 */
function okResponse(data: unknown = {}) {
  return {
    status: 200,
    json: async () => ({ success: true, data, meta: { requestId: "x", timestamp: "now" } }),
  };
}

describe("lib/admin-verification", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("listPendingDocuments", () => {
    it("defaults to page=1, page_size=20, and no status filter", async () => {
      const fetchMock = vi.fn().mockResolvedValue(okResponse());
      vi.stubGlobal("fetch", fetchMock);

      await listPendingDocuments("token-abc");

      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toBe("http://localhost:8000/api/v1/companies/documents/pending?page=1&page_size=20");
      expect((init.headers as Record<string, string>).Authorization).toBe("Bearer token-abc");
    });

    it("passes page/pageSize/status through as page/page_size/status query params", async () => {
      const fetchMock = vi.fn().mockResolvedValue(okResponse());
      vi.stubGlobal("fetch", fetchMock);

      await listPendingDocuments("token-abc", { page: 3, pageSize: 50, status: "rejected" });

      const calledUrl = fetchMock.mock.calls[0]?.[0] as string;
      const query = new URL(calledUrl).searchParams;
      expect(query.get("page")).toBe("3");
      expect(query.get("page_size")).toBe("50");
      expect(query.get("status")).toBe("rejected");
    });

    it("omits the status query param entirely when not supplied (backend defaults to pending)", async () => {
      const fetchMock = vi.fn().mockResolvedValue(okResponse());
      vi.stubGlobal("fetch", fetchMock);

      await listPendingDocuments("token-abc", { page: 2 });

      const calledUrl = fetchMock.mock.calls[0]?.[0] as string;
      expect(new URL(calledUrl).searchParams.has("status")).toBe(false);
    });
  });

  describe("reviewDocument", () => {
    it("posts {decision:'approve'} with no note field when approving without one", async () => {
      const fetchMock = vi.fn().mockResolvedValue(okResponse());
      vi.stubGlobal("fetch", fetchMock);

      await reviewDocument("company-1", "doc-1", "approve", "token-abc");

      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toBe("http://localhost:8000/api/v1/companies/company-1/documents/doc-1/review");
      expect(init.method).toBe("POST");
      expect((init.headers as Record<string, string>).Authorization).toBe("Bearer token-abc");
      expect(JSON.parse(init.body as string)).toEqual({ decision: "approve" });
    });

    it("posts {decision:'reject', note} when rejecting with a reason", async () => {
      const fetchMock = vi.fn().mockResolvedValue(okResponse());
      vi.stubGlobal("fetch", fetchMock);

      await reviewDocument("company-1", "doc-1", "reject", "token-abc", "Certificate is illegible.");

      const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(JSON.parse(init.body as string)).toEqual({
        decision: "reject",
        note: "Certificate is illegible.",
      });
    });

    it("targets the correct company_id/document_id pair in the URL", async () => {
      const fetchMock = vi.fn().mockResolvedValue(okResponse());
      vi.stubGlobal("fetch", fetchMock);

      await reviewDocument("company-xyz", "doc-789", "approve", "token-abc");

      const calledUrl = fetchMock.mock.calls[0]?.[0] as string;
      expect(calledUrl).toBe("http://localhost:8000/api/v1/companies/company-xyz/documents/doc-789/review");
    });
  });
});
