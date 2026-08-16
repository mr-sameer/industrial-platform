# 0036 — Local Dev Rate-Limit Workflow, and Auth Module Completion

## Status
Accepted. Final stabilization pass for the Authentication module before
freezing ForgeX v0.5.0-alpha.

## Part 1 — Why localhost is still affected after the production fix

The prior fix (ADR-0035) forwards a real client IP through the BFF via
`X-Forwarded-For` — this correctly fixes rate limiting for any real
deployment behind a reverse proxy, CDN, or load balancer, where the
*incoming* request to Next.js already carries a real IP set by
whatever's in front of it.

Pure local development (`next dev`, browser connecting directly, no
proxy anywhere) has no such upstream to have set that header in the
first place. Confirmed by direct reproduction: registered 5 real
distinct accounts through the actual browser→BFF→FastAPI path;
`ratelimit:register:127.0.0.1` (namespace `ratelimit:register:*`) held
count=5, TTL=3598s (~3600s window, matching
`rate_limit_register_per_ip_window_seconds`) after exactly 5 real
requests. This is not a bug in the limiter, the IP-forwarding fix, or
`_client_ip()` — it's an inherent property of a topology with no proxy
in front of the BFF: there is no distinguishing signal to forward.
Redis state is independent of the API process (confirmed previously in
ADR-0034) — restarting `uvicorn` does not reset it, and a normal
afternoon of manually testing register/login exhausts the real,
unweakened limit faster than any real deployment would.

## Part 2 — Development-only workflow (not a limiter change)

Per explicit requirement: fix the workflow, not the limit. Nothing
about the actual rate-limiting values, windows, or per-IP keying
changes in any environment, including this one.

- `apps/api/scripts/reset_dev_rate_limits.sh` — deletes only
  `ratelimit:*`, `auth:lockout:*`, `auth:login_strikes:*` (the complete
  set of Redis namespaces the auth rate limiter and account-lockout
  mechanism use, confirmed directly against `app/api/v1/auth.py`), via
  `SCAN`, never `FLUSHALL`/`FLUSHDB`. Verified directly: filled the
  real 5-request limit, confirmed a genuine 429, ran the script,
  confirmed an unrelated Redis key survived untouched, confirmed
  registration worked immediately after with zero other changes.
  Refuses to run when `ENVIRONMENT=production` (exit 1) as a safety
  net — the stronger guarantee is operational (a developer's local
  `REDIS_URL` should never point at a real deployment's Redis in the
  first place), but costs nothing to also check for.
- `Makefile`'s `reset-rate-limit` target — a thin wrapper, tested.
- The 429 response itself now includes a hint pointing at both, but
  **only when `not settings.is_production`** — a message-text-only
  addition (`app/main.py`'s `rate_limit_exception_handler`), verified
  with a dedicated production-isolated test
  (`test_rate_limit_hint_never_appears_in_production`) that this text
  never reaches a production response even when a request is actually
  rate-limited there.

## Part 3 — Auth module completion

Audit against the full checklist found a real, substantial gap: only
`/login` and `/register` had frontend pages. `/forgot-password`,
`/reset-password`, and `/verify-email` had zero frontend presence — no
pages, no BFF routes — despite the backend already fully supporting
all three (`POST /auth/forgot-password`, `/auth/reset-password`,
`/auth/verify-email`). Built:

- Shared types (`packages/shared-types/src/auth.ts`):
  `ForgotPasswordRequest`, `ResetPasswordRequest`, `VerifyEmailRequest`
  — mirroring the backend Pydantic schemas field-for-field.
- Three new BFF routes, all forwarding the real client IP where the
  backend rate-limits by IP — closing the exact follow-up ADR-0035
  itself flagged as deliberately scoped out (`verify_email` and
  `forgot_password` sharing the collapsed-bucket bug).
- Three new pages: `/forgot-password` (email → privacy-preserving
  "check your email" state, matching the backend's own
  never-reveal-account-existence behavior), `/reset-password` (reads
  `?token=` from the emailed link, forwards the real per-field error —
  invalid token vs. weak password vs. reused password — rather than a
  single generic message), `/verify-email` (reads `?token=`, verifies
  on mount, success/failure states).
- Added the missing "Forgot password?" link on `/login`, and a
  success banner for the post-reset redirect
  (`/login?reset=success`).
- "Back to Home" link added centrally to `AuthCard` (shared by every
  page under the `(auth)` route group) rather than duplicated
  per-page — covers all five auth pages automatically, present and
  future.

## Verification

Every scenario run for real, not assumed:

- Fresh Redis → register (201) → login (200) → repeat registration
  with the same email → `409 EMAIL_ALREADY_REGISTERED` (not 429 — a
  real, distinct failure mode correctly distinguished from rate
  limiting).
- `forgot-password`: 204 for both a real and an unknown email
  (privacy-preserving, matches backend contract).
- `verify-email`: a bad token returns a clean `400
  INVALID_VERIFICATION_TOKEN`, not a 429 or 500.
- `refresh`: with a real cookie and matching `Origin` header (same-
  origin, as a real browser sends), 200 with a genuinely new access
  token. (A raw `curl` with no `Origin` header correctly gets `403
  FORBIDDEN_ORIGIN` from the refresh route's own CSRF-style same-
  origin check — confirmed as that check's own intended behavior, not
  a rate-limit issue, by re-testing with a proper `Origin` header.)
- Real browser, real Chromium (Playwright): register → redirects to
  `/dashboard` (needs ~5s in dev mode specifically due to Next.js's
  on-demand route compilation — a dev-only artifact, not present in a
  production build) → reload → still authenticated (session
  persistence, confirmed) → logout → explicit follow-up visit to
  `/dashboard` redirects to `/login?next=%2Fdashboard` (session
  genuinely terminated, not just client-state cleared).
- "Back to Home" link confirmed present on `/register`, `/login`,
  `/forgot-password` via real DOM query; `/reset-password` and
  `/verify-email` inherit it from the same shared `AuthCard`.

Backend: 150/150 passing (148 prior + 2 new
`test_rate_limit_dev_hint.py`), `ruff`/`mypy --strict` clean. Frontend:
12/12 passing, `tsc`/ESLint clean.

## Why production remains secure
- No rate-limit value, window, or per-IP keying logic changed, in any
  environment.
- The reset script only ever runs against whatever `REDIS_URL` it's
  pointed at (a developer's own local Redis in normal use) and refuses
  outright when `ENVIRONMENT=production`.
- The dev hint in the 429 response is gated on `not
  settings.is_production` and has a dedicated, isolated test proving
  it never appears when `is_production` is true — not just assumed
  from the `if` statement's presence.
