import type { ClientSession } from "@platform/shared-types";
import { NextResponse } from "next/server";


import { clearRefreshTokenCookie, getRefreshTokenCookie, setRefreshTokenCookie } from "@/lib/auth/cookies";
import { isSameOriginRequest } from "@/lib/auth/origin-check";
import { refreshUpstream } from "@/lib/auth/server-auth-client";

/**
 * Called on app bootstrap (and whenever an access token expires mid-session)
 * to silently re-establish a session from the httpOnly refresh cookie —
 * the browser sends no body; the cookie is read server-side.
 */
export async function POST(request: Request) {
  if (!isSameOriginRequest(request)) {
    return NextResponse.json(
      {
        success: false,
        error: { code: "FORBIDDEN_ORIGIN", message: "Cross-site requests are not allowed here." },
        meta: { requestId: "n/a", timestamp: new Date().toISOString() },
      },
      { status: 403 }
    );
  }

  const refreshToken = getRefreshTokenCookie();
  if (!refreshToken) {
    return NextResponse.json(
      {
        success: false,
        error: { code: "NO_SESSION", message: "No active session." },
        meta: { requestId: "n/a", timestamp: new Date().toISOString() },
      },
      { status: 401 }
    );
  }

  const result = await refreshUpstream(refreshToken);
  if (!result.success) {
    clearRefreshTokenCookie();
    return NextResponse.json(result, { status: 401 });
  }

  setRefreshTokenCookie(result.data.refresh_token);
  const session: ClientSession = {
    access_token: result.data.access_token,
    expires_in_minutes: result.data.expires_in_minutes,
    user: result.data.user,
  };
  return NextResponse.json({ success: true, data: session, meta: result.meta });
}
