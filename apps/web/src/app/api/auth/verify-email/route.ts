import type { VerifyEmailRequest } from "@platform/shared-types";
import { NextResponse } from "next/server";

import { getClientIp } from "@/lib/auth/client-ip";
import { verifyEmailUpstream } from "@/lib/auth/server-auth-client";

export async function POST(request: Request) {
  const payload = (await request.json()) as VerifyEmailRequest;
  const result = await verifyEmailUpstream(payload, getClientIp(request));
  if (!result.success) {
    return NextResponse.json(result, { status: 400 });
  }
  return NextResponse.json(result);
}
