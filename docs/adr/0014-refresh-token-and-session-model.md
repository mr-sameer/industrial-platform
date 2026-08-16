# 0014 — Refresh Token & Session Model: Opaque, Rotating, Reuse-Detected

## Status
Accepted — supersedes the refresh-token half of ADR-0010 (the access-token
half of ADR-0010 is unchanged: still a short-lived, stateless JWT).

## Context
ADR-0010 shipped stateless JWT refresh tokens with an explicitly tracked
gap: no way to revoke one, and no way to detect a stolen token being
replayed. Module 2.5's hardening pass exists specifically to close that
gap (see docs/security/module-2.5-architecture-review.md, weaknesses #1
and #2).

## Decision
Two new tables replace the JWT refresh token:

- **`sessions`** — one row per login (per device/browser). Holds
  device/browser/platform/IP metadata (cosmetic only — never used for
  authorization), `expires_at`, and `revoked_at`/`revoked_reason`.
- **`refresh_tokens`** — the rotation history for a session. Exactly one
  row per session has `used_at IS NULL` at any time; that's the
  currently valid token. The value handed to a client is
  `"<row-id>.<random-secret>"` (see `app.core.opaque_tokens`) — only a
  SHA-256 hash of the secret is ever stored.

**Rotation:** every `POST /auth/refresh` call marks the presented token
`used_at = now()`, creates a new row, and returns the new token. The old
token string is dead the instant it's used.

**Reuse detection:** if a presented token's hash matches a row that
already has `used_at` set, that exact token has already been rotated
away once — someone is replaying it. This is treated as a compromise
signal strong enough to revoke the *entire session* immediately
(`app.services.session_service.rotate_refresh_token`), not just reject
that one request. `tests/test_sessions.py::test_reusing_a_rotated_away_token_revokes_the_whole_session`
verifies both halves of this: the replay is rejected, and the
previously-valid current token is also dead afterward.

## Alternatives considered
- **Token-family list stored as a JSON array on one row per session**:
  functionally similar but loses the audit trail of exactly which token
  was replaced by which; a normalized table costs one extra join and
  buys a queryable rotation history for incident response.
- **Sliding-window JWT refresh (just shorten the JWT's expiry further)**:
  doesn't solve revocability at all — a stolen JWT refresh token, however
  short-lived, is still valid until it expires with no way to kill it
  early. Doesn't address the actual gap.
- **Redis-only session store (no Postgres tables)**: would make
  revocation and rotation fast, but loses durability (a Redis restart
  logs everyone out) and loses the "list your active sessions" feature's
  natural home (Phase 3's requirement) in a system whose durability
  guarantees this platform's other data already depends on Postgres for.

## Consequences
- One extra DB write per login and per refresh (previously: zero writes
  for a stateless refresh). Acceptable at this stage — see the
  Scalability Risks section of the architecture review — and indexed
  correctly (`session_id`, `user_id`, `expires_at`, `token_hash`) from
  the first migration that creates these tables (`0002_add_auth_hardening_tables`).
- `POST /auth/logout` is now a **real** server-side revocation (it was a
  client-side no-op under ADR-0010). `POST /auth/logout-all` revokes
  every session for a user in one call.
- Expired sessions accumulate until cleaned up — there is no scheduled
  job in this codebase yet (no task scheduler exists — see ADR-0003's
  consequences). `app.services.session_service.cleanup_expired_sessions`
  exists and is intended to be invoked by a periodic job once one is
  introduced; until then it must be run manually or via an external cron
  hitting a future admin endpoint. This is a tracked, not hidden, gap.
