import { NextResponse, type NextRequest } from "next/server";

/**
 * Two independent jobs, both belonging here because both need
 * per-request logic `next.config.mjs`'s static `headers()` can't do:
 *
 * 1. Route gate: redirects to /login if the httpOnly refresh-token
 *    cookie is absent (Module 2). A UX convenience, NOT the security
 *    boundary — the API independently verifies the access token on
 *    every request. Unchanged from before this fix.
 *
 * 2. Content-Security-Policy with a per-request nonce (fix — see
 *    docs/adr/0031-csp-blocked-hydration.md). Next.js's App Router
 *    always injects inline `<script>` tags carrying the RSC/hydration
 *    payload — this is Next's own internal mechanism, not something
 *    avoiding inline scripts in application code sidesteps. The
 *    previous CSP (`script-src 'self'`, no nonce, no 'unsafe-inline')
 *    blocked those scripts outright, which blocked React hydration on
 *    every page in the app — confirmed via real browser testing
 *    (Playwright), which is what caught this: every prior verification
 *    of this app used curl, which doesn't execute JavaScript and so
 *    never exercised CSP's effect on scripts at all.
 *
 * Fixed the officially-documented way (Next.js's own CSP guide): a
 * fresh nonce per request, forwarded to the app via a request header so
 * Next.js's internal rendering can apply it to its own inline scripts
 * automatically, and included in the CSP response header itself.
 * 'unsafe-eval' is added only outside production — `next dev`'s React
 * Refresh / HMR tooling needs it; production builds don't.
 *
 * Deliberately NOT using 'strict-dynamic' (Next's docs example
 * includes it): when present, 'strict-dynamic' disables 'self'/host-
 * based script allowlisting entirely per the CSP3 spec — confirmed via
 * real production-build browser testing, every same-origin
 * `<script src="/_next/static/...">` chunk tag was refused. Root cause:
 * statically-generated pages (e.g. /login, /register — prerendered at
 * build time) can't have a per-request nonce baked into their chunk
 * tags at all, and 'strict-dynamic' offers no fallback to 'self' for
 * those. This app is same-origin only (no third-party script loading,
 * which is 'strict-dynamic''s actual use case) — plain 'self' + nonce
 * covers same-origin chunk files and inline hydration scripts alike,
 * correctly and more simply.
 */
const PROTECTED_PREFIXES = ["/dashboard"];
const REFRESH_TOKEN_COOKIE_NAME = process.env.REFRESH_TOKEN_COOKIE_NAME ?? "refresh_token";

function buildCsp(nonce: string): string {
  const isProduction = process.env.NODE_ENV === "production";
  // Client-side code calls the FastAPI backend directly (see e.g.
  // lib/companies.ts, lib/company-verification.ts) — a different origin
  // from the Next.js app itself. `connect-src 'self'` alone blocks every
  // one of those calls; the backend's own origin must be explicitly
  // allowed. Falls back to 'self' only if NEXT_PUBLIC_API_BASE_URL is
  // somehow unset, rather than producing an invalid empty directive.
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  const connectSrc = apiBaseUrl ? `'self' ${apiBaseUrl}` : "'self'";
  // Uploaded logos/cover images (Module 3B) are served from the API's
  // /uploads/* static route — same cross-origin situation as connect-src.
  const imgSrc = apiBaseUrl ? `'self' data: ${apiBaseUrl}` : "'self' data:";
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}'${isProduction ? "" : " 'unsafe-eval'"}`,
    "style-src 'self' 'unsafe-inline'", // Next.js's inline critical CSS — see next.config.mjs's original note
    `img-src ${imgSrc}`,
    `connect-src ${connectSrc}`,
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join("; ");
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const csp = buildCsp(nonce);

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);

  const isProtected = PROTECTED_PREFIXES.some((prefix) => pathname.startsWith(prefix));
  if (isProtected) {
    const hasSessionCookie = request.cookies.has(REFRESH_TOKEN_COOKIE_NAME);
    if (!hasSessionCookie) {
      const loginUrl = new URL("/login", request.url);
      loginUrl.searchParams.set("next", pathname);
      const redirectResponse = NextResponse.redirect(loginUrl);
      redirectResponse.headers.set("Content-Security-Policy", csp);
      return redirectResponse;
    }
  }

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  // Runs on every route except static assets/images — matches Next.js's
  // own documented recommended matcher pattern for exactly this reason:
  // every page needs the nonce/CSP, but re-running middleware on every
  // hashed static asset request is pure overhead with no benefit.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
