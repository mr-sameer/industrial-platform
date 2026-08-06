# 0016 — Forgot / Reset Password

## Status
Accepted

## Context
There was no account-recovery path at all (architecture review weakness
#9) — a user who forgot their password had no way back in.

## Decision
- `POST /auth/forgot-password` always returns 204 regardless of whether
  the email is registered (mirrors the login endpoint's user-enumeration
  protection — ADR-0010). If the account exists, a one-time, hashed,
  1-hour-expiring token (`password_reset_tokens`) is issued and emailed
  (stub — ADR-0019).
- `POST /auth/reset-password` consumes the token, validates the new
  password (strength + not-reused — ADR-0018), sets it, and — critically
  — **revokes every existing session** for that user
  (`session_service.revoke_all_sessions_for_user`, reason
  `PASSWORD_RESET`). A password reset is assumed to follow a compromise
  or a forgotten-but-possibly-guessed password; anything that could log
  in with the old password must stop working immediately.
- Reset tokens are single-use (`used_at` set on consumption, checked
  before honoring a second attempt) and time-boxed to 1 hour — much
  shorter than the 24-hour email-verification window, since a reset
  token grants account takeover if intercepted, not just email
  confirmation.

## Alternatives considered
- **Security questions**: weaker in practice (answers are often
  guessable or discoverable) and adds a data-collection requirement at
  registration this platform doesn't otherwise need; not chosen.

## Consequences
- `tests/test_password_reset.py::test_reset_password_revokes_all_existing_sessions`
  verifies the session-revocation guarantee directly.
- Same email-sending caveat as ADR-0015: no real provider wired up yet.
