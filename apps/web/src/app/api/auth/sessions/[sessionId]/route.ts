import { NextResponse } from "next/server";

import { revokeSessionUpstream } from "@/lib/auth/server-auth-client";

/** Proxies DELETE /auth/sessions/{id} — revoke one device/session. */
export async function DELETE(request: Request, { params }: { params: { sessionId: string } }) {
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

  const result = await revokeSessionUpstream(accessToken, params.sessionId);
  return new NextResponse(null, { status: result.success ? 204 : 404 });
}
