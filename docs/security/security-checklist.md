# Security Checklist — Module 2.5

A living checklist for anyone deploying or extending the auth system.
Check items are either true today (✅), explicitly not yet true (⚠️, with
the tracking reference), or not applicable at this stage (—).

## Authentication
- ✅ Passwords hashed with Argon2id (bcrypt kept only for legacy-hash verification) — [ADR-0018](../adr/0018-argon2id-password-hashing.md)
- ✅ Password strength enforced (length, composition, common-password blacklist)
- ✅ Password history prevents reuse of the last 5 passwords
- ✅ Access tokens are short-lived (15 min default), stateless JWT
- ✅ Refresh tokens are opaque, hashed at rest, rotate on every use, and detect reuse — [ADR-0014](../adr/0014-refresh-token-and-session-model.md)
- ✅ Login errors don't distinguish "wrong password" from "unknown email" (user-enumeration protection) — including timing: the unknown-email path runs a real Argon2id verification against a dummy hash rather than short-circuiting
- ✅ Per-IP rate limiting on register/login/refresh/forgot-password/verify-email
- ✅ Progressive per-account lockout after repeated failed logins
- ⚠️ No CAPTCHA or equivalent secondary abuse gate beyond rate limiting/lockout — [ADR-0020](../adr/0020-rate-limiting-and-security-headers.md)

## Session management
- ✅ Sessions are individually listable and revocable (`GET`/`DELETE /auth/sessions`)
- ✅ "Log out everywhere" revokes every session for a user in one call
- ✅ Password reset and password change both revoke all existing sessions
- ⚠️ No scheduled cleanup job for expired sessions — a standalone script exists (`scripts/cleanup_expired_tokens.py`) but nothing invokes it automatically yet — [ADR-0014](../adr/0014-refresh-token-and-session-model.md)

## Email flows
- ✅ Email verification tokens are one-time, hashed, 24h-expiring
- ✅ Password reset tokens are one-time, hashed, 1h-expiring
- ✅ Forgot-password never reveals whether an email is registered
- ⚠️ **No real email provider is wired up** — verification/reset emails only reach structured logs (`LoggingEmailSender`) — [ADR-0019](../adr/0019-email-sending-stub.md). **This is the single largest production blocker in this module.**

## Transport & headers
- ✅ Security headers on every API response (CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, HSTS in production)
- ✅ Security headers on every web app response (same set, adapted for an HTML-serving app)
- ✅ Refresh-token cookie is `httpOnly`, `Secure` (in production), `SameSite=Lax`
- ✅ Origin-header check as defense-in-depth on cookie-mutating BFF routes (refresh, logout) — [ADR-0012](../adr/0012-web-session-strategy.md)
- ⚠️ CORS origin list is a single flat env var with no environment-specific validation — nothing prevents a wildcard being set in production by mistake
- — CSRF token pattern not used — mitigated instead by `SameSite=Lax` + Origin check (see above); revisit only if that combination proves insufficient

## Data protection
- ✅ Refresh, verification, and password-reset tokens are never stored in plaintext — only SHA-256 hashes
- ✅ Audit log captures IP/user-agent/device for security-relevant events — [ADR-0017](../adr/0017-audit-logging.md)
- ⚠️ Audit log has no retention/partitioning policy — grows unboundedly
- ⚠️ Audit log write shares the caller's DB transaction (documented limitation, not a silent one) — [ADR-0017](../adr/0017-audit-logging.md)

## Client storage
- ✅ Web: refresh token in httpOnly cookie (unreadable by JS); access token in memory only, never persisted
- ✅ Mobile: both tokens in platform secure storage (Keychain/Keystore), never `SharedPreferences`
- ⚠️ Mobile: no biometric re-auth gate yet — architecture prepared, not implemented — see `apps/mobile/lib/core/storage/secure_token_storage.dart`

## Authorization
- ✅ RBAC dependency (`require_role`) exists and is tested, ready for the first business route that needs it
- ✅ `require_verified_email` dependency exists, ready for the first route that should gate on email verification (e.g. company creation)
- — No protected business routes exist yet to actually exercise either dependency in production traffic

## Testing
- ✅ 48+ backend tests passing against real Postgres + Redis (not mocked), including the reuse-detection guarantee, rate limiting, and lockout
- ✅ Migrations verified to round-trip (upgrade → downgrade → upgrade) against a real database
- ✅ Web: real `tsc`, ESLint, Vitest, and a full `next build` all passing
- ⚠️ Mobile: no automated test run in this pass — Dart/Flutter tooling wasn't available in the environment this module was built in; changes were verified by careful static review only (see the architecture review's Phase 15 notes)
