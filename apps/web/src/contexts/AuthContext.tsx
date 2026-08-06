"use client";

/**
 * Client-side session state. Holds the access token and current user in
 * memory only (component state) — never in localStorage/sessionStorage
 * (see docs/adr/0012-web-session-strategy.md). Lost on full page reload
 * by design; `bootstrap()` re-establishes it from the httpOnly refresh
 * cookie via POST /api/auth/refresh.
 */
import type { ApiResponse, ClientSession, LoginRequest, RegisterRequest, UserPublic } from "@platform/shared-types";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";


export interface AuthContextValue {
  user: UserPublic | null;
  accessToken: string | null;
  status: "loading" | "authenticated" | "unauthenticated";
  login: (payload: LoginRequest) => Promise<{ ok: true } | { ok: false; message: string }>;
  register: (payload: RegisterRequest) => Promise<{ ok: true } | { ok: false; message: string }>;
  logout: () => Promise<void>;
  logoutAll: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

async function postJson<T>(path: string, body?: unknown): Promise<ApiResponse<T>> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include", // sends the httpOnly refresh cookie
    body: body ? JSON.stringify(body) : undefined,
  });
  return (await res.json()) as ApiResponse<T>;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserPublic | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [status, setStatus] = useState<AuthContextValue["status"]>("loading");

  const applySession = useCallback((session: ClientSession) => {
    setUser(session.user);
    setAccessToken(session.access_token);
    setStatus("authenticated");
  }, []);

  const clearSession = useCallback(() => {
    setUser(null);
    setAccessToken(null);
    setStatus("unauthenticated");
  }, []);

  useEffect(() => {
    // Bootstrap: try to silently re-establish a session from the refresh cookie.
    postJson<ClientSession>("/api/auth/refresh").then((result) => {
      if (result.success) {
        applySession(result.data);
      } else {
        clearSession();
      }
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
    await postJson("/api/auth/logout");
    clearSession();
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

  const value = useMemo(
    () => ({ user, accessToken, status, login, register, logout, logoutAll }),
    [user, accessToken, status, login, register, logout, logoutAll]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
