/**
 * Extracts the real originating client IP from an incoming BFF
 * request — see docs/adr/0035-rate-limit-collapsed-through-bff.md for
 * the bug this exists to fix: without this, every request the Next.js
 * server makes to FastAPI (registerUpstream, loginUpstream, ...)
 * arrives from the SAME loopback address (the Next.js server's own),
 * regardless of which real, distinct end user actually made it —
 * collapsing FastAPI's per-IP rate limiting into a single shared
 * bucket for everyone.
 *
 * In any real deployment, whatever sits in front of Next.js (a load
 * balancer, CDN, reverse proxy) sets x-forwarded-for on the incoming
 * request — that's the real client's IP, and this passes it straight
 * through to FastAPI (which already prefers x-forwarded-for over the
 * raw socket address — see apps/api/app/api/v1/auth.py's _client_ip).
 * In pure local dev with nothing in front of Next.js at all, neither
 * header exists, and this correctly returns null — there genuinely is
 * no distinguishing client identity to forward in that specific case,
 * and this deliberately doesn't fabricate one.
 */
export function getClientIp(request: Request): string | null {
  const forwardedFor = request.headers.get("x-forwarded-for");
  if (forwardedFor) return forwardedFor.split(",")[0]!.trim();

  const realIp = request.headers.get("x-real-ip");
  if (realIp) return realIp.trim();

  return null;
}
