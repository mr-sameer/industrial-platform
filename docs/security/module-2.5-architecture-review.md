# Module 2.5 — Phase 1: Architecture & Security Review

Reviewed as of the end of Module 2. This is the audit that gates Phases
2–15; nothing below was "fixed while reviewing" — findings here are
addressed explicitly in the later phases, each cross-referenced.

## Scope reviewed

Authentication architecture, JWT implementation, refresh token flow,
session management, RBAC, cookie strategy, Flutter secure storage, API
security posture, middleware, error handling.

---

## Strengths

1. **Clean separation of concerns.** `security.py` (crypto primitives),
   `dependencies.py` (request-time enforcement), `auth_service.py`
   (business logic), `api/v1/auth.py` (thin HTTP layer) are already
   correctly layered — hardening can slot in without a rewrite.
2. **No user enumeration on login.** Wrong password and unknown email
   both return `INVALID_CREDENTIALS` (`tests/test_auth.py` asserts this).
3. **Consistent API envelope.** Every error already carries a stable
   `code`, which makes adding new failure modes (rate limiting, reuse
   detection, etc.) additive rather than a breaking change to the
   contract.
4. **BFF cookie split (web) is sound in principle.** Refresh token never
   touches browser JS; access token never touches disk. This is the
   correct shape — Phase 12 tightens details, doesn't replace it.
5. **Mobile correctly uses platform secure storage**, not
   `SharedPreferences`/plaintext files.
6. **Fail-fast config guard** already exists for the dev JWT secret in
   production (`app/core/config.py`).
7. **Good test coverage of the happy paths and the two enumeration/replay
   edge cases already present** (`test_refresh_rejects_an_access_token_used_as_refresh_token`).

## Weaknesses / Security Risks

Ranked by severity, not document order.

1. **CRITICAL — Refresh tokens are stateless JWTs with no server-side
   record.** A stolen refresh token (XSS on web despite the BFF split
   mitigating most of that risk, a compromised mobile device, a leaked
   log line) is valid for its full 7-day life with **no way to revoke
   it**. `POST /auth/logout` is a client-side no-op today. This was
   flagged as a known, tracked gap in ADR-0010 — Phase 2 closes it.
2. **HIGH — No reuse detection.** Because refresh tokens aren't rotated
   or tracked, there's no way to detect "this exact refresh token was
   already used once" — the textbook signal that a token has been
   stolen and both the attacker and the legitimate user are now racing
   to use it. Phase 2.
3. **HIGH — No visibility or control over active sessions.** A user
   (or an admin investigating an incident) cannot see which
   devices/browsers hold valid sessions, nor revoke one selectively.
   Phase 3.
4. **HIGH — No rate limiting anywhere.** `/login` is brute-forceable at
   whatever rate the network allows; `/register` can be used to spam
   account creation; `/refresh` has no abuse protection either. Phase 7.
5. **HIGH — No audit trail.** Structured logs exist for request
   completion, but there is no durable, queryable record of
   security-relevant events (who logged in when, from where, password
   changes, etc.) — needed both for incident response and, later,
   compliance. Phase 8.
6. **MEDIUM — bcrypt, not Argon2id.** ADR-0011 documented this as a
   deliberate, revisitable tradeoff (avoid a native dependency at
   foundation stage). The instruction driving this phase treats Argon2id
   as the default absent a documented compatibility reason — none exists
   here, so Phase 6 supersedes ADR-0011.
7. **MEDIUM — No password reuse / strength / blacklist checks beyond
   length.** `RegisterRequest`'s validator only checks length + a letter
   + a digit. Phase 6.
8. **MEDIUM — No email verification.** Any email string is accepted at
   registration with no proof of ownership. Phase 4.
9. **MEDIUM — No password reset flow at all.** A user who forgets their
   password has no recovery path today. Phase 5.
10. **MEDIUM — No security headers.** FastAPI responses carry no CSP,
    HSTS, `X-Content-Type-Options`, etc. Phase 9.
11. **LOW-MEDIUM — CSRF for the web BFF cookie routes relies entirely on
    `SameSite=Lax`.** That's a real, effective mitigation for the POST
    routes in question (Lax cookies aren't attached to cross-site POSTs),
    but it's a single layer with no defense-in-depth (e.g. no Origin
    header check). Phase 10/12.
12. **LOW — CORS origin list is a single flat env var with no
    environment-specific validation** (e.g. nothing stops
    `API_CORS_ORIGINS=*` from being set in production). Phase 9/10.
13. **LOW — Flutter has no lock/re-auth behavior on app foreground after
    backgrounding**, and no architecture placeholder for biometric gating
    of the stored refresh token. Phase 11.
14. **LOW — No automatic cleanup of expired anything** (tokens, sessions)
    — not urgent at current scale, but left unaddressed it's a slow
    unbounded-growth problem. Phase 2/3.

## Scalability Risks

- Stateless JWT access tokens scale horizontally by design — no change
  needed there.
- Introducing a `sessions`/`refresh_tokens` table (Phase 2/3) adds a DB
  write on every login and every refresh (previously zero DB writes for
  refresh). At 15-minute access-token life, this is one extra write per
  user per ~15 minutes of active use — acceptable, but worth indexing
  correctly (`session_id`, `user_id`, `expires_at`) from the start, which
  Phase 2/3's migration does.
- Rate limiting (Phase 7) needs Redis, which is already a first-class
  dependency (ADR-0006) — no new infrastructure required.
- Audit logs (Phase 8) will grow unboundedly; Phase 8 documents this as a
  known operational concern (partitioning/archival) rather than solving
  it now — solving log retention policy is a deployment/ops decision
  outside this module's scope.

## Technical Debt Being Created (tracked, not hidden)

- Email sending in Phase 4/5 is a **stub** (`EmailSender` interface,
  logging implementation) — no SMTP/provider is wired up, since no
  provider has been chosen for this platform yet. This is explicitly
  flagged in Phase 14's docs, not left implicit.
- Rate limiting uses a simple fixed-window Redis counter, not a more
  sophisticated sliding-window/leaky-bucket — sufficient for this stage,
  documented as a possible future refinement.
- Audit log storage is a single Postgres table with no partitioning —
  fine at current expected scale, flagged as a future concern.

## Decision

Proceeding to Phase 2. Nothing above is deferred silently — each
weakness maps to a numbered phase, and any that end up **not** fully
resolved will be called out explicitly in Phase 15's final report and
reflected in a category score below 9/10 with a stated reason.
