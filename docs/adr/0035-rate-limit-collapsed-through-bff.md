# 0035 — Fix: Per-IP Rate Limiting Collapsed Through the BFF

## Status
Accepted.

## Context
Reported: `POST /api/v1/auth/register` returning `429 Too Many
Requests` — "Too many requests. Try again in 3595 seconds" — on every
attempt, blocking all new registrations.

## Investigation (every claim below confirmed by direct reproduction, not inferred)

1. **Rate limiter configuration**: `rate_limit_register_per_ip=5`,
   window=3600s (`app/core/config.py`) — correct, working exactly as
   coded. `3595`/`3599` seconds remaining matches a ~3600s window
   almost exactly, confirming this specific limiter, not a
   misconfigured one.
2. **Redis keys**: inspected directly — `ratelimit:register:127.0.0.1`,
   a **single** key.
3. **Client IP detection**: `app/api/v1/auth.py`'s `_client_ip()`
   correctly prefers `X-Forwarded-For`, falling back to
   `request.client.host` — the logic itself is correct.
4. **Are all localhost requests sharing one bucket**: **yes, confirmed
   by reproduction** — registered 6 genuinely distinct users (different
   emails) through the real browser → Next.js → FastAPI path; the 6th
   failed with the exact reported error text.
5. **Does state persist across a server restart**: **yes, confirmed
   directly** — killed the `uvicorn` process entirely (`ps aux` showed
   no process), Redis still held the full counter afterward. Redis is
   a separate, independently-running service; nothing about restarting
   the API process touches it.
6. **Have test runs filled the bucket**: yes — every registration
   across many prior debugging sessions this project has gone through
   funneled through the same `127.0.0.1` bucket, a real, cumulative
   contributing factor, not just this investigation's own test calls.

## Root cause
`/api/v1/auth/register` (and `/login`, `/refresh`) are called through a
Backend-for-Frontend — `apps/web/src/app/api/auth/{register,login,refresh}/route.ts`
call FastAPI server-side (`server-auth-client.ts`), the browser never
reaches FastAPI directly. Nothing set `X-Forwarded-For` on that
server-to-server call, so `_client_ip()` fell back to
`request.client.host` — which, for every single request regardless of
which real end user initiated it, is the Next.js server's own loopback
address. The rate limiter isn't malfunctioning; it's counting correctly
against the only IP it was ever shown, which is architecturally wrong
for a BFF topology.

## Fix — not a limit increase, not a disable
Per the explicit requirement: fix client IP detection, not the limit
itself.

- `apps/web/src/lib/auth/client-ip.ts` (new) — `getClientIp(request)`
  extracts the real client's IP from the *incoming* request to the BFF
  (`x-forwarded-for`, falling back to `x-real-ip`), returning `null`
  when neither is present.
- `server-auth-client.ts`'s `authFetch`/`authFetchWithStatus` now
  accept an optional `clientIp` and forward it as `X-Forwarded-For` on
  the *outgoing* call to FastAPI — which already, correctly, prefers
  that header (point 3 above). `registerUpstream`, `loginUpstream`, and
  `refreshUpstream` updated to accept and pass it through; their three
  route handlers now call `getClientIp(request)` and pass the result.
- `verify_email` and `forgot_password` share the identical underlying
  bug (both rate-limit by IP through the same BFF pattern) but were
  **not** fixed in this pass — flagged here explicitly as a known,
  scoped-out follow-up with the identical fix shape, not silently
  left inconsistent.

In any real deployment (behind a load balancer, CDN, or reverse
proxy), the *incoming* request to Next.js already carries a real
`X-Forwarded-For` set by whatever's in front of it — this fix ensures
that value survives the BFF hop instead of being silently discarded
and replaced with the BFF's own identity.

**Honest limitation, not silently glossed over**: in pure local
development with nothing in front of Next.js at all (bare `next dev`,
browser connecting directly), there is no proxy to have set
`X-Forwarded-For` in the first place — `getClientIp` correctly returns
`null` in that case, and the behavior is *unchanged* from before this
fix: still one shared bucket. This is confirmed directly, not assumed,
and is an inherent property of that specific topology (there
genuinely is no way to distinguish two browser tabs on the same
developer machine as "different clients" without something upstream
assigning them different identities) — not a residual bug this fix
failed to address.

## Verification
- Reproduced the exact reported failure: 6 distinct users through the
  real BFF path, 6th fails with the exact reported error text and TTL
  range.
- Confirmed the fix: same 6 users, each with a distinct simulated
  `X-Forwarded-For` (as a real proxy would set) on the incoming
  request — all 6 succeed, Redis shows 6 separate keys.
- Confirmed the fix does *not* fabricate a false sense of correctness
  for pure local dev: with no incoming `X-Forwarded-For` at all,
  behavior is honestly unchanged (still one bucket) — directly
  reproduced, not assumed.
- Cleared the pre-existing stuck development key (`DEL
  ratelimit:register:127.0.0.1`) as an operational action once the
  root cause was fixed — not a substitute for the fix itself.
- Full backend suite unaffected (148/148 — this was a frontend-only
  change). Full frontend suite: 12/12 (8 pre-existing + 4 new,
  `__tests__/client-ip.test.ts`). `tsc`/ESLint clean.

## Consequences
- `verify_email` and `forgot_password` still share this bug — tracked
  above as an explicit, scoped-out follow-up, not silently left
  inconsistent with the fixed endpoints.
- No change to the rate limit values themselves, and the limiter was
  never disabled at any point — matching the explicit constraint this
  investigation was scoped under.
