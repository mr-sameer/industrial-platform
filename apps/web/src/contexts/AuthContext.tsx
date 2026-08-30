"use client";

/**
 * Client-side session state. Holds the access token and current user in
 * memory only (component state) — never in localStorage/sessionStorage
 * (see docs/adr/0012-web-session-strategy.md). Lost on full page reload
 * by design; `bootstrap()` re-establishes it from the httpOnly refresh
 * cookie via POST /api/auth/refresh.
 */
import type { ApiResponse, ClientSession, LoginRequest, RegisterRequest, UserPublic } from "@platform/shared-types";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { logger } from "@/lib/logger";

export interface ResolvedAuth {
  status: "authenticated" | "unauthenticated";
  accessToken: string | null;
}

export interface AuthContextValue {
  user: UserPublic | null;
  accessToken: string | null;
  status: "loading" | "authenticated" | "unauthenticated";
  login: (payload: LoginRequest) => Promise<{ ok: true } | { ok: false; message: string }>;
  register: (payload: RegisterRequest) => Promise<{ ok: true } | { ok: false; message: string }>;
  logout: () => Promise<void>;
  logoutAll: () => Promise<void>;
  /**
   * ForgeX Product Audit P0: `status` starts "loading" on every mount and
   * only resolves once the bootstrap effect's POST /api/auth/refresh
   * settles — a caller that reads `status`/`accessToken` synchronously
   * (e.g. Consult's "Search now" handler) can catch that window and
   * wrongly treat a genuinely-logged-in buyer as unauthenticated if they
   * act before it resolves. This waits for the *real* outcome — via refs
   * updated the instant applySession/clearSession run, not via this
   * render's closure, which would still read stale "loading"/null even
   * after an await — and resolves immediately if bootstrap already
   * settled, so it costs nothing in the normal case.
   */
  resolveAuth: () => Promise<ResolvedAuth>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

async function postJson<T>(path: string, body?: unknown): Promise<ApiResponse<T>> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include", // sends the httpOnly refresh cookie
    body: body ? JSON.stringify(body) : undefined,
  });
  // 204 No Content (logout's real response) has no body to parse —
  // res.json() throws "Unexpected end of JSON input" on the empty
  // string, which — left uncaught by a caller like `logout` below —
  // aborted before it could clear client state at all. Same fix,
  // same reasoning, as lib/api-client.ts's apiFetch for exactly this
  // response shape; every other case (login/register/refresh/me's real
  // JSON bodies) parses exactly as before.
  if (res.status === 204) {
    return { success: true, data: null as T, meta: { requestId: "n/a", timestamp: new Date().toISOString() } };
  }
  return (await res.json()) as ApiResponse<T>;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserPublic | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [status, setStatus] = useState<AuthContextValue["status"]>("loading");

  // Mirrors `status`/`accessToken`, but updated synchronously in the same
  // call as the setState above — resolveAuth() below reads these instead
  // of the state variables so it never returns a value that's stale by
  // one render (state updates don't apply until the next render; these do
  // immediately, which is what a promise resolving mid-bootstrap needs).
  const statusRef = useRef<AuthContextValue["status"]>("loading");
  const accessTokenRef = useRef<string | null>(null);

  const applySession = useCallback((session: ClientSession) => {
    setUser(session.user);
    setAccessToken(session.access_token);
    setStatus("authenticated");
    statusRef.current = "authenticated";
    accessTokenRef.current = session.access_token;
  }, []);

  const clearSession = useCallback(() => {
    setUser(null);
    setAccessToken(null);
    setStatus("unauthenticated");
    statusRef.current = "unauthenticated";
    accessTokenRef.current = null;
  }, []);

  const bootstrapped = useRef(false);
  const bootstrapPromise = useRef<Promise<void> | null>(null);

  useEffect(() => {
    // Bootstrap: try to silently re-establish a session from the refresh cookie.
    //
    // Guarded with a ref, not just relying on this effect's own logic,
    // because React 18's StrictMode deliberately double-invokes effects
    // in development (mount -> cleanup -> mount again) to surface
    // missing-cleanup bugs. Without this guard, that double-invocation
    // fires this POST twice — and since refresh tokens rotate on every
    // use (see docs/adr/0014), the second call uses a token the first
    // call already consumed, which Module 2.5's reuse-detection
    // correctly treats as a stolen/replayed token and revokes the
    // entire session for. The practical effect, confirmed via real
    // browser testing: every local dev session bootstrap had a real
    // chance of immediately logging the user back out right after
    // registering — see docs/adr/0031 for the full incident. This
    // never affected production (`next build`/`next start`), where
    // StrictMode's double-invocation doesn't happen at all — only local
    // `next dev`, which is also what `docker compose up`'s default dev
    // path uses.
    if (bootstrapped.current) return;
    bootstrapped.current = true;
    bootstrapPromise.current = postJson<ClientSession>("/api/auth/refresh")
      .then((result) => {
        if (result.success) {
          applySession(result.data);
        } else {
          clearSession();
        }
      })
      .catch(() => {
        // If the fetch itself rejects (network failure, not an HTTP
        // error response — postJson already handles those), still
        // resolve out of "loading" rather than leaving the app stuck
        // showing a spinner forever.
        clearSession();
      });
  }, [applySession, clearSession]);

  const login = useCallback<AuthContextValue["login"]>(
    async (payload) => {
      const result = await postJson<ClientSession>("/api/auth/login", payload);
      if (!result.success) return { ok: false, message: result.error.message };
      applySession(result.data);
      return { ok: true };
    },
    [applySession]
  );

  const register = useCallback<AuthContextValue["register"]>(
    async (payload) => {
      const result = await postJson<ClientSession>("/api/auth/register", payload);
      if (!result.success) return { ok: false, message: result.error.message };
      applySession(result.data);
      return { ok: true };
    },
    [applySession]
  );

  const logout = useCallback(async () => {
    // ForgeX Product Audit P1 #6: clearSession() used to run only after
    // this await resolved, so `status` stayed "authenticated" for the
    // full POST /api/auth/logout round trip (server logs: 0.5-2s+ in
    // dev) with zero visual feedback in between — the audit's live
    // testing read that gap as the click having silently failed. The
    // comment below already establishes client-side logout as
    // best-effort/optimistic regardless of the network outcome, so
    // there's no reason `status` needs to wait on it: clearing first
    // flips `useRequireAuth`'s existing "redirect when unauthenticated"
    // effect (see AppShell) almost immediately, which is the one place
    // that should own this navigation — see ProfileMenu.tsx, which no
    // longer pushes its own competing redirect.
    clearSession();
    try {
      await postJson("/api/auth/logout");
    } catch (err) {
      // Best-effort, same as logoutAll below and the server-side
      // logoutUpstream() this proxies to (see its own comment): from
      // the user's perspective, clicking "Log out" must always end
      // their session client-side, even if the network request itself
      // failed (offline, upstream down, etc). The server-side session
      // still gets cleared in the success path above; a failure here
      // just means it may briefly outlive the local one.
      logger.error({ err }, "auth_logout_request_failed");
    }
  }, [clearSession]);

  const logoutAll = useCallback(async () => {
    if (accessToken) {
      await fetch("/api/auth/logout-all", {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` },
      });
    }
    clearSession();
  }, [accessToken, clearSession]);

  const resolveAuth = useCallback(async (): Promise<ResolvedAuth> => {
    if (bootstrapPromise.current) {
      await bootstrapPromise.current;
    }
    // statusRef/accessTokenRef were just updated (or already were, if
    // bootstrap had already settled) synchronously inside applySession/
    // clearSession above — never "loading" by this point.
    return {
      status: statusRef.current === "authenticated" ? "authenticated" : "unauthenticated",
      accessToken: accessTokenRef.current,
    };
  }, []);

  const value = useMemo(
    () => ({ user, accessToken, status, login, register, logout, logoutAll, resolveAuth }),
    [user, accessToken, status, login, register, logout, logoutAll, resolveAuth]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
