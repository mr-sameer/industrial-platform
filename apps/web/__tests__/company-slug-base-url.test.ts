import { afterEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "@/lib/api-client";
import { getCompanyBySlug } from "@/lib/companies";

/**
 * P0 #2 (Buyer UX Audit) regression: /company/[slug] is a Server
 * Component, so it runs inside the web container and must call the API
 * over the Compose network (serverEnv.apiBaseUrl), not the browser-facing
 * default apiFetch/getCompanyBySlug otherwise fall back to — that default
 * is "http://localhost:8000" from inside the container, which resolves
 * back to the web container itself and ECONNREFUSEs. See
 * lib/companies.ts's getCompanyBySlug and app/company/[slug]/page.tsx.
 */
describe("getCompanyBySlug base URL override", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("calls the browser-facing default base URL when none is passed (existing client-side behavior, unchanged)", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      json: async () => ({ success: true, data: {}, meta: { requestId: "x", timestamp: "now" } }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await getCompanyBySlug("acme");

    const calledUrl = fetchMock.mock.calls[0]?.[0] as string;
    expect(calledUrl).toBe("http://localhost:8000/api/v1/companies/slug/acme");
  });

  it("calls the explicit server-internal base URL when one is passed, for the Server Component call site", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      json: async () => ({ success: true, data: {}, meta: { requestId: "x", timestamp: "now" } }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await getCompanyBySlug("acme", "http://api:8000");

    const calledUrl = fetchMock.mock.calls[0]?.[0] as string;
    expect(calledUrl).toBe("http://api:8000/api/v1/companies/slug/acme");
  });

  it("URL-encodes the slug regardless of which base URL is used", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      json: async () => ({ success: true, data: {}, meta: { requestId: "x", timestamp: "now" } }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await getCompanyBySlug("a b", "http://api:8000");

    const calledUrl = fetchMock.mock.calls[0]?.[0] as string;
    expect(calledUrl).toBe("http://api:8000/api/v1/companies/slug/a%20b");
  });
});

describe("apiFetch base URL parameter", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("defaults to the configured browser-facing base URL", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      json: async () => ({ success: true, data: null, meta: { requestId: "x", timestamp: "now" } }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/v1/health");

    expect(fetchMock.mock.calls[0]?.[0]).toBe("http://localhost:8000/api/v1/health");
  });

  it("uses an explicitly passed base URL instead", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      json: async () => ({ success: true, data: null, meta: { requestId: "x", timestamp: "now" } }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/v1/health", undefined, "http://api:8000");

    expect(fetchMock.mock.calls[0]?.[0]).toBe("http://api:8000/api/v1/health");
  });
});
