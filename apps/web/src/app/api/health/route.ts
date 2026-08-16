import { NextResponse } from "next/server";

import { logger } from "@/lib/logger";

const startedAt = Date.now();

/**
 * Liveness/readiness endpoint for the web app itself (not the API).
 * Used by the Docker HEALTHCHECK and by uptime monitors.
 */
export async function GET() {
  logger.info("health_check_requested");
  return NextResponse.json({
    success: true,
    data: {
      status: "ok",
      service: "web",
      uptimeSeconds: Math.round((Date.now() - startedAt) / 1000),
    },
    meta: { requestId: crypto.randomUUID(), timestamp: new Date().toISOString() },
  });
}
