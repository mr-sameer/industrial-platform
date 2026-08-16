import { NextResponse } from "next/server";

import { listSessionsUpstream } from "@/lib/auth/server-auth-client";

/** Proxies GET /auth/sessions — "your active devices" list. */
export async function GET(request: Request) {
  const authHeader = request.headers.get("authorization");
  const accessToken = authHeader?.replace(/^Bearer\s+/i, "");
  if (!accessToken) {
    return NextResponse.json(
      {
        success: false,
        error: { code: "UNAUTHORIZED", message: "Missing access token." },
        meta: { requestId: "n/a", timestamp: new Date().toISOString() },
      },
      { status: 401 }
    );
  }

  const result = await listSessionsUpstream(accessToken);
  return NextResponse.json(result, { status: result.success ? 200 : 401 });
}
