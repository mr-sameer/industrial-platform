import type { ForgotPasswordRequest } from "@platform/shared-types";
import { NextResponse } from "next/server";

import { getClientIp } from "@/lib/auth/client-ip";
import { forgotPasswordUpstream } from "@/lib/auth/server-auth-client";

export async function POST(request: Request) {
  const payload = (await request.json()) as ForgotPasswordRequest;
  const result = await forgotPasswordUpstream(payload, getClientIp(request));
  // Deliberately the same response shape regardless of whether the
  // email is registered — mirrors FastAPI's own reset_password_endpoint
  // docstring: the response must never reveal account existence.
  return new NextResponse(null, { status: result.success ? 204 : result.status });
}
