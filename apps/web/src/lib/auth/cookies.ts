/**
 * httpOnly refresh-token cookie management — server-only (Route Handlers).
 * See docs/adr/0012-web-session-strategy.md for why this exists.
 */
import { cookies } from "next/headers";

import { serverEnv } from "@/config/server-env";

const REFRESH_TOKEN_MAX_AGE_SECONDS = 60 * 60 * 24 * 7; // 7 days — matches JWT_REFRESH_TOKEN_EXPIRE_DAYS default

interface CookieOptions {
  httpOnly: boolean;
  secure: boolean;
  sameSite: "lax";
  path: string;
  maxAge: number;
}

function cookieOptions(): CookieOptions {
  return {
    httpOnly: true,
    secure: serverEnv.isProduction,
    sameSite: "lax",
    path: "/",
    maxAge: REFRESH_TOKEN_MAX_AGE_SECONDS,
  };
}

export function setRefreshTokenCookie(refreshToken: string): void {
  cookies().set(serverEnv.refreshTokenCookieName, refreshToken, cookieOptions());
}

export function getRefreshTokenCookie(): string | undefined {
  return cookies().get(serverEnv.refreshTokenCookieName)?.value;
}

export function clearRefreshTokenCookie(): void {
  cookies().delete(serverEnv.refreshTokenCookieName);
}
