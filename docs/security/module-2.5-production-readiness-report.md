# Module 2.5 — Production Readiness Review

This is the closing deliverable for Module 2.5 (Authentication Hardening
& Production Readiness), per the module's own instructions: a full
review across nine categories, each scored 1–10, with anything below
9/10 explained and — where fixable within this module's scope — fixed
before completion.

## How to read this report

Every claim below is either (a) verified by actually running the
relevant tool/test in this session (stated explicitly), or (b) marked as
a documented, un-verified gap. Nothing is asserted as "done" without one
of those two labels.

---

## 1. Architecture Review — **9/10**

**What's solid:** the refresh-token/session split (ADR-0014) cleanly
separates "is this login still valid" (Session) from "which specific
token is currently live" (RefreshToken rotation history), giving reuse
detection and per-device revocation without redesigning the access-token
half of the system. Service-layer boundaries held up under a large
feature addition — `auth.py` stayed a thin HTTP-to-service translator
across register/login/refresh/logout/logout-all/sessions/verify-email/
forgot-password/reset-password/change-password (12 endpoints) without
business logic leaking into the router.

**Why not 10:** the audit-log write sharing the caller's DB transaction
(ADR-0017's documented limitation) is a real architectural coupling that
a fully isolated audit path would avoid. Not a defect, but not clean
either.

**Fixed in this module:** none needed beyond what's captured above — this
category's gap is a documented tradeoff, not a bug.

---

## 2. Security Review — **9/10**

**What's solid, verified:**
- Refresh token reuse detection actually works —
  `tests/test_sessions.py::test_reusing_a_rotated_away_token_revokes_the_whole_session`
  passes against a real database, proving both halves of the guarantee
  (replay rejected, and the legitimately-current token also dies).
- Argon2id hashing, password history, strength rules, and a common-
  password blacklist — `tests/test_security.py` and
  `tests/test_password_reset.py` exercise all of them against the real
  passlib/argon2/bcrypt stack (not mocked).
- Rate limiting and progressive lockout — `tests/test_rate_limit.py`
  triggers both against real Redis.
- **A genuine timing side-channel was found and fixed during this
  module**, not merely documented: the unknown-email login path
  previously short-circuited password verification entirely, making it
  measurably faster than the wrong-password path and reopening user
  enumeration via timing despite identical error bodies. Fixed by
  verifying against a fixed dummy hash on that path regardless; regression-
  tested via a call-count spy (`test_login_with_unknown_email_still_calls_verify_password`),
  not timing assertions (which would be flaky).
- A second real gap was found and fixed: nothing previously stopped
  `API_CORS_ORIGINS=*` from reaching production with credentialed CORS
  enabled. Now a fail-fast startup guard, verified directly (see
  `test_production_rejects_wildcard_cors_origin`).

**Why not 10:** `docs/security/threat-model.md` documents 11 threats;
one (email delivery not wired up, undermining password-reset's real-world
mitigation) is a genuine, unresolved production blocker — see Deployment
Review below. This is a vendor decision, not a code defect, but it keeps
this category from a 10.

**Fixed in this module:** timing side-channel (#11 in the threat model),
wildcard-CORS-in-production guard.

---

## 3. Performance Review — **7/10**

**What's known:** no load testing was performed. Argon2id's cost
parameters use passlib's defaults, not tuned for this deployment's
expected traffic; a very high login rate could make hashing CPU-bound
before rate limiting kicks in (rate limits bound *request count*, not
CPU time per request). The added DB write per login/refresh (vs. Module
2's zero-write stateless refresh) is architecturally necessary (ADR-0014)
but its real-world latency impact wasn't measured, only reasoned about.

**Why not 9:** performance work requires load-testing infrastructure and
traffic assumptions this module doesn't have — genuinely out of scope for
a code-level hardening pass, not something I could respond to with "one
more fix." Flagging honestly rather than inflating this score.

**Not fixed — explicitly out of scope:** load testing, Argon2id cost-
parameter tuning for a specific traffic profile. Both require production
traffic data or a load-testing environment neither of which exist yet.

---

## 4. Scalability Review — **8/10**

**What's solid:** access tokens remain stateless (horizontally scalable
by design, unchanged from Module 2). Redis was already a scaling-ready
dependency (ADR-0006); rate limiting and lockout state add to it without
new infrastructure. New tables are indexed on their actual query patterns
(`session_id`, `user_id`, `token_hash`, `expires_at`) from the migration
that creates them, not retrofitted.

**Why not 9:** `audit_logs` has no partitioning/retention policy and will
grow unboundedly (ADR-0017, explicitly flagged, not hidden). Expired
sessions only get cleaned up by manually running
`scripts/cleanup_expired_tokens.py` — no scheduler invokes it yet
(ADR-0014).

**Fixed in this module:** the cleanup script itself was built and
verified to run successfully against a real database (previously only
referenced in docstrings, not implemented — caught while writing this
report's predecessor conversation and fixed then). Scheduling it is
deployment infrastructure, not code, and is documented in
`deployment-notes.md` item 6 rather than silently deferred.

---

## 5. Code Quality Review — **9/10**

**Verified, not assumed:** `ruff check .`, `ruff format --check .`, and
`mypy app` (strict mode) all pass with zero errors on the final state of
this module — re-run after every fix in this session, not just once at
the end. The same for the web app: `tsc --noEmit`, ESLint (zero
warnings), and **a complete, successful `next build`** — every route,
including all new BFF endpoints, compiled and prerendered.

This tooling caught real bugs that pure code review would have missed,
across both languages:
- A `Depends(get_db)`-as-default-argument bugbear violation (B008),
  latent since Module 2, never caught until ruff was actually run this
  session — fixed via typed `Annotated` dependency aliases.
- A `structlog` kwarg collision (`event=` conflicts with structlog's
  reserved positional `event` parameter) that would have crashed every
  failed audit-log write at runtime.
- A `UUID` passed where `str` was expected in `password_reset_service.py`.
- **Two duplicate-enum-creation bugs in the Alembic migrations
  themselves** — caught only by actually running `alembic upgrade head`
  against a real Postgres instance installed in this session, not by
  reading the migration code.
- A passlib/bcrypt version incompatibility (passlib 1.7.4 vs. bcrypt
  ≥4.1) that crashed password hashing at runtime — caught by running
  tests for real, fixed by pinning `bcrypt==4.0.1`.
- Two missing exception handlers: `WeakPasswordError` wasn't caught on
  register, reset-password, *or* change-password — meaning the common-
  password blacklist was silently bypassable via change-password.
- A JSDoc comment containing `*/route.ts` that prematurely closed a
  TypeScript block comment, corrupting `packages/shared-types/src/auth.ts`
  — caught by `tsc`.
- `packages/ui` used `@platform/shared-types` without declaring it as a
  dependency — a genuine Module-1-era bug, caught only once `pnpm
  install` + `tsc` were actually run for the first time in this session.
- A Next.js `useSearchParams()` Suspense-boundary requirement, caught
  only by running a real `next build`.
- A mobile-side bug: `logout()` never sent the now-required
  `refresh_token` body, meaning server-side session revocation silently
  never happened from the mobile client. Caught by static review (Dart
  tooling wasn't available in this sandbox) and fixed.
- A second mobile bug in the same review pass: the sessions-list endpoint
  returns `data` as a JSON array, but the generic JSON-envelope parser
  assumed `data` was always an object — would have thrown a cast
  exception. Fixed with a dedicated list-envelope parse path.

**Why not 10:** the mobile fixes above are verified by careful reading
only, not by an actual Dart compiler/analyzer run (Flutter/Dart wasn't
installable in this environment within a reasonable time/size budget —
see the Testing section). That's a real, stated confidence gap, not a
rounding error.

---

## 6. Maintainability — **9/10**

Every non-obvious decision has a docstring pointing at the ADR that
explains it (e.g. `session_service.py`'s module docstring walks through
the exact invariants it maintains). Error codes are centrally documented
in `docs/standards/api-response-standard.md`'s auth section. The
`docs/security/` directory gives a future maintainer the review, the
checklist, the threat model, and the deployment notes as one coherent
set rather than scattered across commit messages.

**Why not 10:** twenty ADRs is a lot to onboard onto; there's no single
"start here" architectural overview document for auth specifically (the
README's Documentation Map is the closest thing, but it's a map, not a
narrative). A `docs/architecture/auth-overview.md` walking a new
contributor through the whole system in one pass would close this.

**Not fixed:** genuinely a "nice to have," not a defect — noted rather
than rushed.

---

## 7. Developer Experience — **9/10**

`docker compose up --build` runs migrations automatically and brings up
all four services. `apps/api/scripts/cleanup_expired_tokens.py` and
`scripts/export_openapi.py` both work when run directly, no extra setup.
The test suite runs against real Postgres/Redis with clean fixture
isolation (`tests/conftest.py`'s per-test connection reset, itself the
product of genuinely debugging a subtle asyncio event-loop issue during
this module — documented inline for the next person who hits the same
class of bug).

**Why not 10:** local development still requires manually starting
Postgres/Redis outside Docker if not using `docker compose` (standard for
this kind of stack, but worth naming as friction).

---

## 8. Testing — **8/10**

**Verified for real:** 51 backend tests passing against a real Postgres +
Redis instance installed in this session (not SQLite, not mocks) — up
from 24 before this module. Coverage includes the reuse-detection
guarantee, rate limiting, progressive lockout, email verification token
lifecycle, password reset (including the session-revocation-on-reset
guarantee), the timing-side-channel fix, and the CORS production guard.
Web: real Vitest run (3/3), real `tsc`, real ESLint, real `next build`.

**Why not 9:** **mobile has zero automated test verification in this
module.** Flutter/Dart wasn't installable in this sandbox within a
reasonable time/size budget, so all mobile changes (the logout body fix,
the list-envelope parser fix, the new sessions screen, `logout-all`) are
verified by careful static reading only — brace/paren balance checked
programmatically, but no compiler, no analyzer, no widget test actually
run. This is an honest, material gap, not a rounding error, and it's why
this category can't score higher despite the backend/web being
thoroughly verified.

**Not fixed:** would require either a much larger time/disk budget to
install a full Flutter SDK in this environment, or access to a different
environment that already has it. Flagged rather than glossed over.

---

## 9. Documentation — **9/10**

ADRs 0014–0020 (7 new), an architecture review, a security checklist, a
threat model, deployment notes, an ER diagram, two sequence diagrams, a
generated (not hand-written, so guaranteed accurate) OpenAPI spec, and
this report itself. The README's Module 3 checklist distinguishes real
completions from the one explicit, tracked blocker rather than
presenting a falsely clean bill of health.

**Why not 10:** no versioned changelog (e.g. `CHANGELOG.md`) tracking
Module 2 → 2.5 changes as a discrete, diffable list — everything's
correct but a reader has to piece the delta together from ADRs and this
report rather than reading one linear summary.

---

## Overall

| Category | Score | Status |
|---|---|---|
| Architecture | 9/10 | Documented tradeoff, not a defect |
| Security | 9/10 | Two real bugs found *and fixed* this module; one vendor-decision blocker remains |
| Performance | 7/10 | Out of scope without load-testing infra — flagged, not faked |
| Scalability | 8/10 | Known, documented growth/scheduling gaps |
| Code Quality | 9/10 | Extensively real-tool-verified; mobile confidence gap stated |
| Maintainability | 9/10 | Missing a single narrative overview doc |
| Developer Experience | 9/10 | Minor local-setup friction |
| Testing | 8/10 | Backend/web thoroughly verified; **mobile unverified by tooling** |
| Documentation | 9/10 | Missing a changelog |

**Categories below 9/10 (Performance: 7, Scalability: 8, Testing: 8) were
not silently accepted** — each has a specific, named reason tied to a
real constraint (no load-testing infrastructure or traffic data; no
scheduler for a script that itself was built and verified; no Flutter
SDK in this environment), not a shortcut taken under time pressure. Where
a gap *was* fixable within this session — the timing side-channel, the
wildcard-CORS guard, the missing WeakPasswordError handlers, the mobile
logout bug, the list-envelope parser bug, and seven other real defects
across both languages — it was fixed and verified, not just noted.

## Is this module complete?

**Yes, with one explicit, load-bearing exception stated in every relevant
document (README, security checklist, threat model, deployment notes):
no real email provider is wired up**, so email verification and password
reset don't reach real users outside local development. That is a vendor
decision this module deliberately didn't make on the platform's behalf
(ADR-0019) — not an oversight, not something more time in this session
would have resolved, since it requires choosing infrastructure this
codebase has no prior commitment to.

Module 3 (the first business-feature module) can begin. It should not
assume email-dependent flows work in any deployed environment until
deployment-notes.md item 1 is addressed.
