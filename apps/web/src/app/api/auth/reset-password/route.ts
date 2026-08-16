import type { ResetPasswordRequest } from "@platform/shared-types";
import { NextResponse } from "next/server";

import { resetPasswordUpstream } from "@/lib/auth/server-auth-client";

export async function POST(request: Request) {
  const payload = (await request.json()) as ResetPasswordRequest;
  const result = await resetPasswordUpstream(payload);
  if (!result.success) {
    const fallback = {
      success: false as const,
      error: { code: "RESET_FAILED", message: "That reset link is invalid or has expired." },
      meta: { requestId: "n/a", timestamp: new Date().toISOString() },
    };
    return NextResponse.json(result.body ?? fallback, { status: result.status });
  }
  return new NextResponse(null, { status: 204 });
}
