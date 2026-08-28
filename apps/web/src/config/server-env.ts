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
  // Server-side BFF calls (Route Handlers, via server-auth-client.ts)
  // run inside *this* process, not the browser — reusing
  // NEXT_PUBLIC_API_BASE_URL for them is wrong the moment web and api
  // are separate containers, because that value is deliberately the
  // browser-facing origin (e.g. http://localhost:8000, published by
  // Docker Compose to the host) and is unreachable from inside the web
  // container itself (it resolves back to the web container, not the
  // api one). API_INTERNAL_BASE_URL is the network-internal address for
  // exactly that case — see docker-compose.yml's `web` service, which
  // sets it to the `api` Compose service's address. It's intentionally
  // absent for a native `next dev` run (no container boundary to
  // cross), so this falls back to NEXT_PUBLIC_API_BASE_URL there,
  // unchanged from before.
  apiBaseUrl: required(
    "API_INTERNAL_BASE_URL or NEXT_PUBLIC_API_BASE_URL",
    process.env.API_INTERNAL_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
  ),
  refreshTokenCookieName: process.env.REFRESH_TOKEN_COOKIE_NAME ?? "refresh_token",
  // Used only for the Origin-header comparison in lib/auth/origin-check.ts.
  // Defaults to local dev; set explicitly in any real deployment.
  webAppSelfUrl: process.env.WEB_APP_SELF_URL ?? `http://localhost:${process.env.WEB_PORT ?? "3000"}`,
  nodeEnv: process.env.NODE_ENV ?? "development",
  isProduction: process.env.NODE_ENV === "production",
};
