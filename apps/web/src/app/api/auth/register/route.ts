import type { ClientSession, RegisterRequest } from "@platform/shared-types";
import { NextResponse } from "next/server";


import { setRefreshTokenCookie } from "@/lib/auth/cookies";
import { registerUpstream } from "@/lib/auth/server-auth-client";

export async function POST(request: Request) {
  const payload = (await request.json()) as RegisterRequest;
  const result = await registerUpstream(payload);

  if (!result.success) {
    const status = result.error.code === "EMAIL_ALREADY_REGISTERED" ? 409 : 422;
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
