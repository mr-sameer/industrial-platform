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
  ForgotPasswordRequest,
  LoginRequest,
  RegisterRequest,
  ResetPasswordRequest,
  SessionPublic,
  UserPublic,
  VerifyEmailRequest,
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

async function authFetch<T>(
  path: string,
  init: RequestInit,
  clientIp?: string | null
): Promise<ApiResponse<T>> {
  const url = `${serverEnv.apiBaseUrl}/api/v1/auth${path}`;
  try {
    const res = await fetch(url, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(clientIp ? { "X-Forwarded-For": clientIp } : {}),
        ...init.headers,
      },
      cache: "no-store",
    });
    return (await res.json()) as ApiResponse<T>;
  } catch (err) {
    logger.error({ err, url }, "auth_upstream_fetch_failed");
    return networkErrorResponse<T>();
  }
}

/**
 * Same request as authFetch, but also returns the real upstream HTTP
 * status — `null` when no HTTP response was ever received (a genuine
 * connection failure, not something FastAPI returned).
 *
 * A separate function, not a change to authFetch itself: authFetch's
 * six other callers (login/refresh/me/sessions/logout) don't have the
 * bug this exists to fix and are intentionally left untouched — see
 * docs/adr/0032-register-bff-status-collapsing-bug.md.
 */
async function authFetchWithStatus<T>(
  path: string,
  init: RequestInit,
  clientIp?: string | null
): Promise<{ status: number | null; body: ApiResponse<T> }> {
  const url = `${serverEnv.apiBaseUrl}/api/v1/auth${path}`;
  try {
    const res = await fetch(url, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(clientIp ? { "X-Forwarded-For": clientIp } : {}),
        ...init.headers,
      },
      cache: "no-store",
    });
    return { status: res.status, body: (await res.json()) as ApiResponse<T> };
  } catch (err) {
    logger.error({ err, url }, "auth_upstream_fetch_failed");
    return { status: null, body: networkErrorResponse<T>() };
  }
}

/**
 * For endpoints that return 204 No Content on success. On failure,
 * FastAPI's error responses do carry a real JSON body (error code +
 * message) — parsed and returned here rather than discarded, so a
 * caller like reset-password can show the real distinction between an
 * invalid/expired token, a weak password, and a reused password,
 * instead of a single generic message.
 */
async function authFetchNoContent<T = undefined>(
  path: string,
  init: RequestInit,
  clientIp?: string | null
): Promise<{ success: boolean; status: number; body?: ApiResponse<T> }> {
  const url = `${serverEnv.apiBaseUrl}/api/v1/auth${path}`;
  try {
    const res = await fetch(url, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(clientIp ? { "X-Forwarded-For": clientIp } : {}),
        ...init.headers,
      },
      cache: "no-store",
    });
    if (res.ok) return { success: true, status: res.status };
    const body = (await res.json().catch(() => undefined)) as ApiResponse<T> | undefined;
    return { success: false, status: res.status, body };
  } catch (err) {
    logger.error({ err, url }, "auth_upstream_fetch_failed");
    return { success: false, status: 502 };
  }
}

export function registerUpstream(payload: RegisterRequest, clientIp?: string | null) {
  return authFetchWithStatus<AuthTokenPair>(
    "/register",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    clientIp
  );
}

export function loginUpstream(payload: LoginRequest, clientIp?: string | null) {
  return authFetch<AuthTokenPair>(
    "/login",
    { method: "POST", body: JSON.stringify(payload) },
    clientIp
  );
}

export function refreshUpstream(refreshToken: string, clientIp?: string | null) {
  return authFetch<AuthTokenPair>(
    "/refresh",
    {
      method: "POST",
      body: JSON.stringify({ refresh_token: refreshToken }),
    },
    clientIp
  );
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

export function forgotPasswordUpstream(payload: ForgotPasswordRequest, clientIp?: string | null) {
  return authFetchNoContent(
    "/forgot-password",
    { method: "POST", body: JSON.stringify(payload) },
    clientIp
  );
}

export function resetPasswordUpstream(payload: ResetPasswordRequest) {
  // Not rate-limited by IP on the backend (app/api/v1/auth.py's
  // reset_password_endpoint) — the token itself is the scarce,
  // rate-limiting-relevant resource here, so no clientIp needed.
  return authFetchNoContent("/reset-password", { method: "POST", body: JSON.stringify(payload) });
}

export function verifyEmailUpstream(payload: VerifyEmailRequest, clientIp?: string | null) {
  return authFetch<UserPublic>(
    "/verify-email",
    { method: "POST", body: JSON.stringify(payload) },
    clientIp
  );
}
