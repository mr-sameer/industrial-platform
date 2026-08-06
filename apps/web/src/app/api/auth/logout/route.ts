import { NextResponse } from "next/server";

import { clearRefreshTokenCookie, getRefreshTokenCookie } from "@/lib/auth/cookies";
import { isSameOriginRequest } from "@/lib/auth/origin-check";
import { logoutUpstream } from "@/lib/auth/server-auth-client";

/**
 * Logs out *this device only*. As of Module 2.5, this is a real
 * server-side session revocation (see docs/adr/0014) — the refresh token
 * held in the httpOnly cookie is forwarded to the API so its session is
 * actually revoked, not just forgotten locally. (Module 2's version of
 * this route only cleared the cookie, since the API had nothing to
 * revoke yet — see docs/adr/0010's original consequences.)
 */
export async function POST(request: Request) {
  if (!isSameOriginRequest(request)) {
    return new NextResponse(null, { status: 403 });
  }

  const refreshToken = getRefreshTokenCookie();
  if (refreshToken) {
    await logoutUpstream(refreshToken); // best-effort — cookie is cleared either way below
  }
  clearRefreshTokenCookie();
  return new NextResponse(null, { status: 204 });
}
