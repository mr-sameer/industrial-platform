import { describe, expect, it } from "vitest";

import { getClientIp } from "@/lib/auth/client-ip";

/**
 * Regression tests for the fix to a real bug: every BFF->FastAPI call
 * used to arrive from the Next.js server's own loopback address,
 * regardless of which real end user made the original request —
 * collapsing FastAPI's per-IP rate limiting (register, login, refresh)
 * into one shared bucket for everyone. See
 * docs/adr/0035-rate-limit-collapsed-through-bff.md.
 */
describe("getClientIp", () => {
  it("returns the first address from a real x-forwarded-for header", () => {
    const request = new Request("http://localhost/api/auth/register", {
      headers: { "x-forwarded-for": "203.0.113.7, 10.0.0.1" },
    });
    expect(getClientIp(request)).toBe("203.0.113.7");
  });

  it("trims whitespace around the first address", () => {
    const request = new Request("http://localhost/api/auth/register", {
      headers: { "x-forwarded-for": "  203.0.113.7  , 10.0.0.1" },
    });
    expect(getClientIp(request)).toBe("203.0.113.7");
  });

  it("falls back to x-real-ip when x-forwarded-for is absent", () => {
    const request = new Request("http://localhost/api/auth/register", {
      headers: { "x-real-ip": "203.0.113.9" },
    });
    expect(getClientIp(request)).toBe("203.0.113.9");
  });

  it("returns null when neither header is present — pure local dev, no proxy in front of Next.js", () => {
    const request = new Request("http://localhost/api/auth/register");
    expect(getClientIp(request)).toBeNull();
  });
});
