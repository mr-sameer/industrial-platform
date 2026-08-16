# 0018 — Password Hashing: Argon2id (supersedes ADR-0011), Password History, and Strength Rules

## Status
Accepted — supersedes ADR-0011 (bcrypt).

## Context
ADR-0011 chose bcrypt at Module 2's foundation stage specifically to
avoid an extra native dependency, while flagging Argon2id — the current
OWASP-recommended default — as the natural upgrade once a hardening pass
justified it. This is that pass.

## Decision
- **Hashing**: `passlib.context.CryptContext(schemes=["argon2", "bcrypt"],
  deprecated="auto")` (`app.core.security`). New hashes use Argon2id.
  Existing bcrypt hashes still verify correctly; `deprecated="auto"`
  means passlib transparently re-hashes to argon2 on next successful
  login — no bulk migration needed. `app.core.security.needs_rehash`
  exposes this check directly for anywhere that wants to force an
  upgrade path later (e.g. re-hashing on every login going forward, not
  just relying on passlib's internal verify-then-upgrade).
- **Compatibility pin**: `bcrypt==4.0.1` is pinned alongside passlib
  1.7.4 — a real, reproduced-in-this-repo's-CI incompatibility exists
  between passlib 1.7.4's bcrypt-backend version detection and bcrypt
  >=4.1 (it calls `bcrypt.__about__.__version__`, removed upstream),
  which crashes on `_finalize_backend_mixin`'s internal self-test the
  moment bcrypt is used at all — including passlib's own lazy backend
  initialization. Discovered by actually running the test suite against
  a real environment, not assumed.
- **Password history**: `password_history` table
  (`app.models.password_history`), storing the last 5 hashes per user.
  `app.services.password_service.assert_not_reused` checks both the
  current password and history before allowing a change/reset.
- **Strength validation**: `app.core.password_policy.validate_password_strength`
  — minimum 10 characters (already enforced at the schema level via
  Pydantic in Module 2), maximum 128, at least one letter and one digit,
  and rejection against a common-password blacklist
  (`COMMON_PASSWORDS`).

## Alternatives considered
- **scrypt**: comparable security properties to Argon2id; Argon2id
  chosen for being the more widely-adopted current recommendation
  (OWASP) and passlib's more mature Argon2 backend support.
- **Larger/external common-password list (e.g. full SecLists or a
  live HIBP k-anonymity check)**: the current `COMMON_PASSWORDS` set is
  deliberately small and illustrative — swapping in a real list or a live
  HIBP range-query is a drop-in future improvement, not a redesign,
  flagged explicitly rather than presented as exhaustive.

## Consequences
- Anyone deploying this platform must install `bcrypt==4.0.1` exactly as
  pinned (`requirements.txt`/`pyproject.toml`) — a newer bcrypt breaks
  password hashing entirely until either passlib is upgraded past this
  known incompatibility or the pin is revisited.
- `tests/test_security.py::test_hash_password_uses_argon2_by_default` and
  `test_needs_rehash_flags_legacy_bcrypt_hashes` verify both the new
  default and the legacy-upgrade path against real passlib/bcrypt code,
  not mocks.
