# 0011 — Password Hashing: bcrypt via passlib

## Status
Superseded by [ADR-0018](0018-argon2id-password-hashing.md) — Module 2.5's
hardening pass moved the default scheme to Argon2id. This ADR is kept for
historical context; see 0018 for the current decision and rationale.

## Context
Passwords must never be stored in a reversible form. We need a hashing
scheme that's slow-by-design (resists brute force), self-salting, and
has a mature, well-audited Python implementation — chosen once, here,
rather than left to whoever writes the first auth-adjacent feature.

## Decision
`passlib.context.CryptContext(schemes=["bcrypt"], deprecated="auto")`
(`app/core/security.py`). Cost factor uses passlib/bcrypt's default; no
custom cost factor is set in Module 2.

## Alternatives considered
- **Argon2id**: the current OWASP-recommended default and arguably
  stronger against GPU/ASIC attacks. Not chosen for Module 2 purely to
  avoid an extra native-compiled dependency (`argon2-cffi`) at the
  foundation stage — bcrypt is battle-tested, has no known practical
  breaks at reasonable cost factors, and `deprecated="auto"` means
  switching later is a config change, not a data migration (passlib
  re-hashes transparently on next successful login when the scheme list
  changes). **Revisit this via a new ADR** if a security review calls for
  Argon2id specifically.
- **PBKDF2**: weaker resistance to GPU cracking than bcrypt/argon2 for
  equivalent configuration effort; not chosen.
- **Plain SHA-256 (+ manual salt)**: rejected outright — not
  deliberately slow, unsuitable for password storage regardless of
  salting.

## Consequences
- `hash_password`/`verify_password` (`app/core/security.py`) are the only
  sanctioned way to touch passwords anywhere in the codebase — never
  compare or store `payload.password` directly.
- Migrating to Argon2id later requires only changing `schemes=["bcrypt"]`
  to `schemes=["argon2", "bcrypt"]` (argon2 first, bcrypt kept for
  verifying existing hashes) — passlib re-hashes on next login
  automatically. No bulk password reset needed.
