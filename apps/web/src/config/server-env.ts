/**
 * Server-only environment variables — never imported from a "use client"
 * component or exposed to the browser (unlike src/config/env.ts, which is
 * safe for NEXT_PUBLIC_* values only). Route Handlers and Server
 * Components may import this; nothing else should.
 */
function required(name: string, value: string | undefined): string {
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

export const serverEnv = {
  apiBaseUrl: required(
    "API_BASE_URL",
    process.env.API_BASE_URL ?? "http://localhost:8000"
  ),
  refreshTokenCookieName: process.env.REFRESH_TOKEN_COOKIE_NAME ?? "refresh_token",
  // Used only for the Origin-header comparison in lib/auth/origin-check.ts.
  // Defaults to local dev; set explicitly in any real deployment.
  webAppSelfUrl: process.env.WEB_APP_SELF_URL ?? `http://localhost:${process.env.WEB_PORT ?? "3000"}`,
  nodeEnv: process.env.NODE_ENV ?? "development",
  isProduction: process.env.NODE_ENV === "production",
};
