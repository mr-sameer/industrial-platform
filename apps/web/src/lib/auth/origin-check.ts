/**
 * Defense-in-depth CSRF mitigation for BFF routes that act on the
 * ambient httpOnly refresh-token cookie (refresh, logout, logout-all,
 * session revocation). `SameSite=Lax` (see lib/auth/cookies.ts) already
 * blocks the cookie from being sent on a cross-site POST/DELETE in
 * compliant browsers — this Origin check is a second, independent layer
 * for browsers/configurations where that protection is weaker than
 * expected (e.g. an embedded webview with nonstandard cookie handling).
 * See docs/adr/0012's Alternatives Considered and
 * docs/security/module-2.5-architecture-review.md weakness #11.
 */
import "server-only";

import { serverEnv } from "@/config/server-env";

export function isSameOriginRequest(request: Request): boolean {
  const origin = request.headers.get("origin");
  // Same-site navigations/fetches from the app itself always send Origin;
  // its absence is unusual enough (e.g. some non-browser tooling) that we
  // fail closed rather than assume same-origin.
  if (!origin) return false;
  try {
    return new URL(origin).origin === new URL(serverEnv.webAppSelfUrl).origin;
  } catch {
    return false;
  }
}
