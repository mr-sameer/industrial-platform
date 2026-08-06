import type { ApiResponse } from "@platform/shared-types";

import { env } from "@/config/env";
import { logger } from "@/lib/logger";

/**
 * Thin fetch wrapper for calling the FastAPI backend. Centralizing this now
 * means auth headers (Module 2), retries, and tracing can be added in one
 * place later without touching call sites.
 */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<ApiResponse<T>> {
  const url = `${env.apiBaseUrl}${path}`;
  try {
    const res = await fetch(url, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...init?.headers,
      },
      cache: "no-store",
    });
    // 204 No Content (e.g. DELETE endpoints) has no body to parse — res.json()
    // throws on an empty string. Treat it as a bodyless success instead.
    if (res.status === 204) {
      return {
        success: true,
        data: null as T,
        meta: { requestId: "n/a", timestamp: new Date().toISOString() },
      };
    }
    const body = (await res.json()) as ApiResponse<T>;
    return body;
  } catch (err) {
    logger.error({ err, url }, "api_fetch_failed");
    return {
      success: false,
      error: {
        code: "NETWORK_ERROR",
        message: "Unable to reach the API service.",
      },
      meta: { requestId: "n/a", timestamp: new Date().toISOString() },
    };
  }
}
