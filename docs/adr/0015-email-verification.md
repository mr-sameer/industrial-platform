# 0015 — Email Verification

## Status
Accepted

## Context
Registration accepted any email string with no proof of ownership
(architecture review weakness #8). Future business features (e.g.
creating a company/organization record) need a way to require a
confirmed email first.

## Decision
- `POST /auth/register` issues a one-time, hashed, 24-hour-expiring
  token (`email_verification_tokens`, same opaque-token pattern as
  refresh tokens — see ADR-0014) and "sends" it via
  `app.services.email_service` (a logging stub — see ADR-0019).
- `POST /auth/verify-email` consumes the token, sets
  `users.is_email_verified` / `email_verified_at`.
- `POST /auth/resend-verification` (authenticated) re-issues a token;
  it's a no-op (204, not an error) if already verified.
- `app.core.dependencies.require_verified_email` is a ready-to-use
  FastAPI dependency for the first business route that needs to gate on
  verification (e.g. company creation) — no such route exists yet.

## Alternatives considered
- **6-digit numeric codes instead of a link/token**: more mobile-friendly
  (no deep-linking needed) but weaker against brute force per attempt
  without additional rate limiting specifically on the code-entry
  endpoint. The opaque-token-in-a-link pattern reuses infrastructure
  already built for refresh tokens and password reset; revisit numeric
  codes if mobile UX data suggests link-tapping is a real friction point.

## Consequences
- Registration is not blocked on verification — a user can log in and
  use the access/refresh token pair immediately after registering,
  unverified. Verification is an additional gate for specific future
  features, not a login gate. If a future requirement needs "must verify
  before first login," that's a different (breaking) decision, not this
  one.
- No real email provider is wired up (see ADR-0019) — verification links
  are only visible in structured logs (`email_send_stub` events) until
  one is.
