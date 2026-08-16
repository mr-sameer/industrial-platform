import type { ClientSession, RegisterRequest } from "@platform/shared-types";
import { NextResponse } from "next/server";

import { getClientIp } from "@/lib/auth/client-ip";
import { setRefreshTokenCookie } from "@/lib/auth/cookies";
import { registerUpstream } from "@/lib/auth/server-auth-client";

export async function POST(request: Request) {
  const payload = (await request.json()) as RegisterRequest;
  const { status: upstreamStatus, body: result } = await registerUpstream(
    payload,
    getClientIp(request)
  );

  if (!result.success) {
    // Prefer the real status FastAPI returned. It already distinguishes
    // 409 (duplicate email), 422 (validation), and 429 (rate limited)
    // correctly on its own — no guessing needed. `upstreamStatus` is
    // only `null` when no HTTP response was ever received at all (a
    // genuine connection failure between this BFF and FastAPI, not
    // anything FastAPI itself returned) — 502 Bad Gateway is the
    // accurate status for that case, not 422. See
    // docs/adr/0032-register-bff-status-collapsing-bug.md for the
    // investigation that found this.
    const status = upstreamStatus ?? 502;
    return NextResponse.json(result, { status });
  }

  setRefreshTokenCookie(result.data.refresh_token);
  const session: ClientSession = {
    access_token: result.data.access_token,
    expires_in_minutes: result.data.expires_in_minutes,
    user: result.data.user,
  };
  return NextResponse.json({ success: true, data: session, meta: result.meta }, { status: 201 });
}
