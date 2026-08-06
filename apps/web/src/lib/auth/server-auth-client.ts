/**
 * Server-only client for calling the FastAPI auth endpoints directly
 * (server-to-server, no CORS/cookie concerns). Used exclusively by the
 * Route Handlers under src/app/api/auth/* — the browser never imports
 * this. See docs/adr/0012-web-session-strategy.md.
 */
import "server-only";

import type {
  ApiResponse,
  AuthTokenPair,
  LoginRequest,
  RegisterRequest,
  SessionPublic,
  UserPublic,
} from "@platform/shared-types";

import { serverEnv } from "@/config/server-env";
import { logger } from "@/lib/logger";

function networkErrorResponse<T>(): ApiResponse<T> {
  return {
    success: false,
    error: { code: "NETWORK_ERROR", message: "Unable to reach the authentication service." },
    meta: { requestId: "n/a", timestamp: new Date().toISOString() },
  };
}

async function authFetch<T>(path: string, init: RequestInit): Promise<ApiResponse<T>> {
  const url = `${serverEnv.apiBaseUrl}/api/v1/auth${path}`;
  console.log("API BASE URL:", serverEnv.apiBaseUrl);
  console.log("REQUEST URL:", url);
  try {
    const res = await fetch(url, {
      ...init,
      headers: { "Content-Type": "application/json", ...init.headers },
      cache: "no-store",
    });
    return (await res.json()) as ApiResponse<T>;
  } catch (err) {
    logger.error({ err, url }, "auth_upstream_fetch_failed");
    return networkErrorResponse<T>();
  }
}

/** For endpoints that return 204 No Content on success (no JSON body to parse). */
async function authFetchNoContent(path: string, init: RequestInit): Promise<{ success: boolean }> {
  const url = `${serverEnv.apiBaseUrl}/api/v1/auth${path}`;
  try {
    const res = await fetch(url, {
      ...init,
      headers: { "Content-Type": "application/json", ...init.headers },
      cache: "no-store",
    });
    return { success: res.ok };
  } catch (err) {
    logger.error({ err, url }, "auth_upstream_fetch_failed");
    return { success: false };
  }
}

export function registerUpstream(payload: RegisterRequest) {
  return authFetch<AuthTokenPair>("/register", { method: "POST", body: JSON.stringify(payload) });
}

export function loginUpstream(payload: LoginRequest) {
  return authFetch<AuthTokenPair>("/login", { method: "POST", body: JSON.stringify(payload) });
}

export function refreshUpstream(refreshToken: string) {
  return authFetch<AuthTokenPair>("/refresh", {
    method: "POST",
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
}

export function meUpstream(accessToken: string) {
  return authFetch<UserPublic>("/me", {
    method: "GET",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

/** Best-effort — the caller (the /api/auth/logout route) clears the local cookie regardless of the result. */
export function logoutUpstream(refreshToken: string) {
  return authFetchNoContent("/logout", {
    method: "POST",
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
}

export function logoutAllUpstream(accessToken: string) {
  return authFetchNoContent("/logout-all", {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export function listSessionsUpstream(accessToken: string) {
  return authFetch<SessionPublic[]>("/sessions", {
    method: "GET",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export function revokeSessionUpstream(accessToken: string, sessionId: string) {
  return authFetchNoContent(`/sessions/${sessionId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}
