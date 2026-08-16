# 0032 — Fix: Register BFF Route Collapsed All Non-Duplicate Errors to HTTP 422

## Status
Accepted — critical bugfix, found via full-stack instrumented tracing.

## Context
Reported: registration succeeds by every other observable signal
(frontend renders, backend runs, Swagger works) but the browser
receives HTTP 422. A prior investigation (see the chat history this
ADR's sibling entries reference) ruled out a request-schema mismatch —
the exact frontend payload, sent directly to FastAPI, succeeds.

This investigation instrumented every layer of the real chain (browser
network capture, the BFF route, `server-auth-client.ts`'s upstream
fetch, and — for this pass — the FastAPI route handler and
`auth_service.register_user` itself with per-step trace prints) and ran
a real, fresh registration through a real browser.

**Result: the backend has no bug.** A complete, clean trace for a
well-formed registration: rate limit check passes, no existing user,
password strength validates, `User` row committed with a real UUID,
session created (JWT + rotating refresh token), verification token
issued, verification email "sent" (stub), `201` returned — all in
milliseconds, no exceptions, no hangs.

**The actual bug is in `apps/web/src/app/api/auth/register/route.ts`**:

```ts
const status = result.error.code === "EMAIL_ALREADY_REGISTERED" ? 409 : 422;
```

This BFF route never preserved FastAPI's real HTTP status — it
discarded it (`authFetch` only ever returned the parsed JSON body, not
the response's status code) and then guessed the browser-facing status
from a single special case. Every other outcome — a genuine validation
rejection, a rate limit (429), a connection failure between the BFF and
FastAPI, anything — collapsed into the same 422. This makes 422 alone
uninformative: it could mean "FastAPI correctly rejected this," or it
could mean "FastAPI was never reached at all." Confirmed directly, in
both directions, by instrumented real requests:
- A genuine weak-password submission: FastAPI returns real `422`
  (`VALIDATION_ERROR`) — correctly reported as 422.
- The backend unreachable (stopped mid-request): `authFetch`'s catch
  block synthesizes `NETWORK_ERROR` — also reported as 422, identically
  to the validation case, even though nothing was validated at all.

## Decision
`authFetch` (used by login/refresh/me/sessions/logout) is **left
completely unchanged** — none of those routes were reported broken, and
touching shared code beyond the actual bug wasn't warranted. Instead, a
new, separate function, `authFetchWithStatus`, does the same fetch but
also returns the real upstream HTTP status (`null` only when no HTTP
response was ever received — a genuine connection failure). Only
`registerUpstream` — and, downstream, the register route handler —
were changed to use it.

The route handler now uses the real status when one exists
(`upstreamStatus ?? 502`), instead of guessing. FastAPI already
correctly distinguishes 409/422/429 on its own; there was never a
reason for the BFF to re-derive that.

## Root cause classification
Per the ticket's required categories: **Bug** — specifically, an
HTTP-status-collapsing bug in the BFF route handler
(`apps/web/src/app/api/auth/register/route.ts`), not a validation
error, not a duplicate email, not a database error, not a timeout, not
a rate limit, not an exception, and not a schema mismatch (already
ruled out). The backend's actual behavior is provably correct.

## Files Modified
- `apps/web/src/lib/auth/server-auth-client.ts` — added
  `authFetchWithStatus` (new function); changed `registerUpstream` to
  use it. `authFetch` itself and its six other callers are untouched.
- `apps/web/src/app/api/auth/register/route.ts` — use the real upstream
  status instead of the `EMAIL_ALREADY_REGISTERED ? 409 : 422` guess.
- `apps/web/e2e/registration.spec.ts` (new) — real end-to-end test,
  see below.
- `apps/web/playwright.config.ts`, `apps/web/e2e/README.md` (new) —
  E2E test infrastructure, not previously present in this project.
- `apps/web/package.json` — `@playwright/test`, `pg`, `@types/pg`
  devDependencies; `test:e2e` script.

No backend file has any net change — `app/services/auth_service.py` and
`app/api/v1/auth.py` were instrumented with temporary trace prints
during this investigation and fully reverted afterward (confirmed via
`ruff`, `mypy --strict`, and a clean import) before this fix shipped.

## Regression Risk
Low, and scoped tightly:
- `authFetch` and its six existing callers: zero changes, zero risk.
- `registerUpstream`'s only caller is the register route (confirmed by
  search before making this change) — no other code path is affected.
- The register route's success path (`result.success` branch) is
  unchanged; only the error-status derivation changed.
- A real connection failure now returns `502` instead of `422` to the
  browser — a behavior change, but the *correct* one: 422 claims "your
  request was invalid," which was never true for that case.

## Tests Added
`apps/web/e2e/registration.spec.ts` — two real, full-stack browser
tests (Playwright), run against a real Next.js server, a real FastAPI
server, and a real Postgres database:
1. Full registration: real form submission, asserts the BFF's actual
   response status/body, directly queries Postgres to confirm the
   `users` row exists with the correct `full_name`, a properly hashed
   (never plaintext) password, and `is_email_verified = false`, then
   asserts the browser actually redirects to `/dashboard` and renders
   that exact user's data.
2. Duplicate email: registers once (`201`), registers the same email
   again, and asserts the **real** status is `409` — this test would
   have passed even before this fix (409 was already a correctly
   special-cased outcome), but it's included because it's the other
   half of proving the status-mapping logic is now driven by FastAPI's
   real response rather than a guess.

Both run against real infrastructure — nothing mocked. This is also the
first formal, repeatable E2E test suite in this project (prior
verification, including this investigation, used ad hoc Playwright
scripts run manually) — `apps/web/e2e/README.md` documents how to run
it.

## Browser Verification
Real headless Chromium (Playwright), not curl, not Swagger:
- Full registration flow from `/register`, through a real form
  submission, to a real `/dashboard` redirect showing the correct
  user's name — captured via the E2E test above, passing.
- Duplicate-email flow — same, confirming `409` is now the real
  upstream status, not a coincidental match of the old guessing logic.
- The originally-reported "422" scenario was reproduced directly (a
  stopped backend mid-request) and confirmed to now return `502`,
  correctly signaling a connection problem rather than misrepresenting
  it as a validation failure.

## Backend Verification
Full instrumented trace of `register_user` for a real, valid
registration: every step (existing-user check, password strength
validation, password hashing, `User` row commit, session/token
creation, verification token issuance, stub email send) completed
successfully with no exceptions, confirmed via real `print()`
instrumentation temporarily added and fully removed. `ruff check`,
`ruff format --check`, and `mypy --strict` all clean on the reverted
files; `python -c "import app.main"` succeeds.

## Confirmation: Modules 1–3B Unaffected
- No backend file has a net change (instrumentation added and fully
  reverted — confirmed by re-viewing the final file contents).
- `authFetch` (Module 2) and all six of its existing callers: zero
  changes.
- The only frontend files changed are the register-specific BFF route
  and a new function alongside (not replacing) existing code in
  `server-auth-client.ts`.
- Full existing test suites re-run after this fix (backend and web) —
  see the completion report for exact pass counts.
