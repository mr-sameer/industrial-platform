# 0010 — JWT Authentication Strategy

## Status
Accepted

## Context
Module 1 deliberately shipped zero authentication (ADR-0009). Module 2
needs a strategy that works identically across three very different
clients — a browser, a native mobile app, and (later) scripts/service
accounts — without the API needing to know which kind of client it's
talking to.

## Decision
Stateless JWTs, two per session:

- **Access token** — 15 minutes default (`JWT_ACCESS_TOKEN_EXPIRE_MINUTES`),
  sent as `Authorization: Bearer <token>`, verified by signature/expiry
  alone (no DB or Redis lookup on every request — see
  `app/core/dependencies.get_current_user`).
- **Refresh token** — 7 days default (`JWT_REFRESH_TOKEN_EXPIRE_DAYS`),
  used only against `POST /api/v1/auth/refresh` to mint a new pair. Each
  token carries a `jti` (unique ID) so a future revocation store can
  blocklist one token without invalidating every session.

Both tokens are HS256-signed with a single shared `JWT_SECRET_KEY`
(`app/core/security.py`). The API itself is transport-agnostic — it
always returns both tokens in the JSON body; what each client does with
the refresh token is that client's decision (see ADR-0012 for web).

## Alternatives considered
- **Server-side sessions (Redis-backed, opaque session ID in a cookie)**:
  simpler to revoke instantly, but requires a Redis round-trip on every
  authenticated request and doesn't map cleanly onto a native mobile
  client's needs. Revisit if instant, guaranteed revocation becomes a hard
  requirement (see Consequences below).
- **Long-lived single access token, no refresh token**: rejected — a
  stolen long-lived token has a large blast radius; short-lived access +
  refresh is the standard mitigation.
- **Asymmetric signing (RS256)**: unnecessary complexity while the API is
  the only service issuing and verifying tokens; revisit if a second
  service needs to verify tokens independently without holding the
  signing secret.

## Consequences
- **No server-side logout/revocation in Module 2.** `POST /auth/logout`
  is a client-side no-op (see `app/api/v1/auth.py`) — a stolen refresh
  token remains valid until it expires (7 days by default) even after
  "logout." A Redis-backed revocation list keyed by refresh-token `jti`
  is the natural fix and should land before this platform handles
  anything sensitive in production. Tracked as a follow-up, not blocking
  Module 2's foundation.
- Rotating `JWT_SECRET_KEY` invalidates every outstanding session
  immediately — acceptable as an emergency "log everyone out" lever, but
  plan secret rotation accordingly.
- `Settings` refuses to boot with the default dev secret when
  `ENVIRONMENT=production` (see `app/core/config.py`'s validator) — a
  deliberate fail-fast guard against shipping the placeholder secret.
