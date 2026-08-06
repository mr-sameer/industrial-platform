import { NextResponse } from "next/server";

import { meUpstream } from "@/lib/auth/server-auth-client";

/**
 * Thin proxy so the browser never needs NEXT_PUBLIC_API_BASE_URL for
 * authenticated calls — it sends its in-memory access token here, and
 * this route forwards it upstream. Keeps a single call pattern
 * (`fetch("/api/auth/...")`) for every auth-related client call.
 */
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

  const result = await meUpstream(accessToken);
  return NextResponse.json(result, { status: result.success ? 200 : 401 });
}
