import type { AuthTokenPair, ClientSession } from "@platform/shared-types";
import { describe, expect, it } from "vitest";


/**
 * Guards the BFF route handlers' most important invariant: a ClientSession
 * (what the browser receives) must never carry the refresh token. This is
 * a type-level guarantee in TS, but the runtime shape is worth asserting
 * too so a future refactor of the route handlers can't silently regress it.
 */
describe("ClientSession does not leak the refresh token", () => {
  it("has no refresh_token key even when constructed from a full AuthTokenPair", () => {
    const full: AuthTokenPair = {
      access_token: "access.jwt",
      refresh_token: "refresh.jwt",
      token_type: "bearer",
      expires_in_minutes: 15,
      user: {
        id: "u1",
        email: "ada@example.com",
        full_name: "Ada Lovelace",
        role: "viewer",
        is_active: true,
        is_email_verified: false,
        created_at: new Date().toISOString(),
      },
    };

    const session: ClientSession = {
      access_token: full.access_token,
      expires_in_minutes: full.expires_in_minutes,
      user: full.user,
    };

    expect("refresh_token" in session).toBe(false);
    expect(Object.keys(session).sort()).toEqual(["access_token", "expires_in_minutes", "user"]);
  });
});
