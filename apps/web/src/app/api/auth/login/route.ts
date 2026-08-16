import type { ClientSession, LoginRequest } from "@platform/shared-types";
import { NextResponse } from "next/server";

import { getClientIp } from "@/lib/auth/client-ip";
import { setRefreshTokenCookie } from "@/lib/auth/cookies";
import { loginUpstream } from "@/lib/auth/server-auth-client";

export async function POST(request: Request) {
  const payload = (await request.json()) as LoginRequest;
  const result = await loginUpstream(payload, getClientIp(request));

  if (!result.success) {
    const status = result.error.code === "INVALID_CREDENTIALS" ? 401 : 403;
    return NextResponse.json(result, { status });
  }

  setRefreshTokenCookie(result.data.refresh_token);
  const session: ClientSession = {
    access_token: result.data.access_token,
    expires_in_minutes: result.data.expires_in_minutes,
    user: result.data.user,
  };
  return NextResponse.json({ success: true, data: session, meta: result.meta });
}
