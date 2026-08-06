import { NextResponse } from "next/server";

import { logoutAllUpstream } from "@/lib/auth/server-auth-client";

/** "Log out everywhere" — revokes every session for the current user. Requires the caller's access token. */
export async function POST(request: Request) {
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

  const result = await logoutAllUpstream(accessToken);
  return new NextResponse(null, { status: result.success ? 204 : 401 });
}
