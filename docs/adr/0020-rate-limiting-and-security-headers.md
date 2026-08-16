# 0020 — Rate Limiting, Account Lockout, and Security Headers

## Status
Accepted

## Context
No endpoint had abuse protection (architecture review weakness #4), and
API responses carried no security headers (weakness #10). Redis is
already a first-class dependency (ADR-0006), making it the natural home
for rate-limit counters without introducing new infrastructure.

## Decision

**Rate limiting** (`app.core.rate_limit.check_rate_limit`): a fixed-window
Redis counter (`INCR` + `EXPIRE` on first increment), applied per-IP to
`/register`, `/login`, `/refresh`, `/forgot-password`, and
`/verify-email`, with independently configurable limits per endpoint
(`app.core.config.Settings` — `rate_limit_*` fields). Exceeding the limit
raises `RateLimitExceededError`, mapped by a global FastAPI exception
handler (`app.main`) to HTTP 429 with a `Retry-After` header and error
code `RATE_LIMITED`.

**Progressive account lockout** (`app.core.rate_limit.register_failed_login`
/ `is_account_locked`): tracked per-*account* (by email), independent of
the per-IP limit — an attacker rotating IPs still hits this. After 5
failed logins, the account locks out for 30 seconds, doubling per
additional failure up to a 15-minute cap. Lockout state clears on a
successful login (`clear_failed_logins`).

**Security headers** (`app.core.security_headers.SecurityHeadersMiddleware`):
applied to every response — `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, a restrictive
`Permissions-Policy`, and `Content-Security-Policy: default-src 'none'`
(the API serves JSON only, never HTML, so there's nothing for a browser
to execute/render regardless). `Strict-Transport-Security` is added only
when `ENVIRONMENT=production`, since it's meaningless — and actively
wrong to cache — over plain HTTP in local dev.

## Alternatives considered
- **Sliding-window or token-bucket rate limiting**: more accurate at
  burst boundaries than fixed-window, but meaningfully more complex to
  implement correctly in Redis (typically needs a Lua script for
  atomicity). Fixed-window's edge-case over-permissiveness (up to 2x the
  nominal limit right at a window boundary) is an acceptable tradeoff at
  this stage — flagged as a known simplification in the architecture
  review's Technical Debt section, not hidden.
- **IP-only lockout (no per-account tracking)**: insufficient — doesn't
  stop a distributed/rotating-IP credential-stuffing attempt against one
  specific account, which per-account lockout does.
- **CAPTCHA after N failures instead of/alongside lockout**: adds a
  frontend dependency and UX cost this module doesn't currently need;
  revisit if lockout alone proves insufficient against real abuse
  patterns.

## Consequences
- Rate limit and lockout constants are configuration
  (`app.core.config.Settings`), not hardcoded, so they can be tuned per
  environment without a code change.
- `tests/test_rate_limit.py` verifies both the per-IP limit and the
  progressive lockout using monkeypatched (tightened) limits so tests
  run in seconds rather than waiting on real windows.
- CORS policy (`API_CORS_ORIGINS`) is unchanged from Module 1/2 — still
  a flat, single env var with no environment-specific validation
  (architecture review weakness #12, e.g. nothing stops a wildcard origin
  being set in production). Not addressed in this module; a
  production-deployment checklist item, not a code fix, since the correct
  origin list is inherently environment-specific configuration, not
  something the code can validate on its own.
