# Module 3A — Company Core: Completion Report

Status: **Complete.** Per the module's own instruction, Module 3B has
not been started. This report follows the exact 10-point structure the
module brief requested.

---

## 1. Architecture Summary

Company Core adds the platform's first business domain on top of the
Module 1/2/2.5 foundation, following the layering and conventions those
modules already established (thin routers → service layer → repository-
style data access, the `ApiSuccess`/`ApiError` envelope, `Depends`-based
authorization) rather than introducing new patterns.

**Core design decisions** (each with a full ADR):
- `CompanyMember.role` uses a new `CompanyRole` enum, kept structurally
  separate from the existing platform-level `Role` — resolving the
  domain model's top-priority open recommendation
  ([ADR-0022](../adr/0022-company-role-naming.md)).
- `Company.industry` is a plain string and `Company.verification_status`
  is a placeholder, not the full taxonomy/verification systems the
  long-term domain model describes — deliberate, reversible
  simplifications scoped to what this module actually needs
  ([ADR-0023](../adr/0023-module-3a-scope-simplifications.md)).
- Ownership transfer reuses the existing `PATCH .../members/{member}`
  endpoint (`role: "owner"`) rather than a new endpoint outside the
  brief's fixed list ([ADR-0024](../adr/0024-ownership-transfer-mechanism.md)).
- The single-Owner business rule is enforced at **two** independent
  layers: application logic (`company_service.py`) and a database-level
  partial unique index — verified by a test that deliberately bypasses
  the service layer to prove the database constraint holds on its own.

**Two critical, previously-latent bugs affecting the entire application
(not just this module) were found and fixed during this module's
development** — see [ADR-0025](../adr/0025-enum-values-callable-bugfix.md)
and [ADR-0026](../adr/0026-ownership-transfer-flush-ordering.md). The
first meant user registration would have failed against any real
deployed database since Module 2; both are detailed in Section 9.

## 2. Files Changed

**Backend (`apps/api`)** — new:
`app/models/company.py`, `app/models/company_member.py`,
`app/schemas/company.py`, `app/services/company_service.py`,
`app/api/v1/companies.py`, `app/core/company_authorization.py`,
`app/core/slug.py`, `app/db/enum_utils.py`,
`alembic/versions/20260802_161523_0003_add_companies_tables.py`,
`tests/test_companies.py`, `tests/test_company_members.py`.

**Backend — modified:** `app/models/__init__.py` (register new models),
`app/models/user.py` + `app/models/session.py` (enum
`values_callable` fix, ADR-0025), `app/core/dependencies.py`
(`VerifiedUser` alias), `app/main.py` (router registration, missing
`jsonable_encoder` import fix), `app/services/auth_service.py` (timing
side-channel fix — see note below), `tests/conftest.py` (single-Owner
index creation via sync connection).

**Web (`apps/web`)** — new:
`src/app/companies/page.tsx`, `src/app/companies/new/page.tsx`,
`src/app/companies/[id]/page.tsx`,
`src/app/companies/[id]/settings/page.tsx`,
`src/app/companies/search/page.tsx`, `src/app/company/[slug]/page.tsx`,
`src/lib/companies.ts`, `src/lib/ui-styles.ts`,
`src/hooks/useRequireAuth.ts`, `__tests__/companies-search.test.ts`,
`__tests__/api-client-204.test.ts`.

**Web — modified:** `src/lib/api-client.ts` (204-response fix),
`src/contexts/AuthContext.tsx` (exported `AuthContextValue`),
`vitest.config.ts` (path-alias resolution fix).

**Mobile (`apps/mobile`)** — new:
`lib/features/companies/domain/company.dart`,
`lib/features/companies/data/company_repository.dart`,
`lib/features/companies/presentation/company_list_screen.dart`,
`lib/features/companies/presentation/create_company_screen.dart`,
`lib/features/companies/presentation/company_dashboard_screen.dart`,
`lib/features/companies/presentation/edit_company_screen.dart`.

**Mobile — modified:** `lib/core/network/api_client.dart` (`patchJson`
added), `lib/features/auth/presentation/auth_gate.dart` (navigation).

**Shared types:** `packages/shared-types/src/company.ts` (new),
`packages/shared-types/src/index.ts` (export).

**Documentation:** ADRs 0022–0026 (new),
`docs/architecture/company-core-data-model.md` (new),
`docs/architecture/company-core-sequences.md` (new),
`docs/architecture/openapi.json` (regenerated, 15→21 paths),
`docs/standards/coding-standards.md` (enum rule added),
`README.md` (status + checklist), this report.

## 3. Database Changes

Migration `0003_add_companies_tables`:
- `companies` table — see
  [`docs/architecture/company-core-data-model.md`](../architecture/company-core-data-model.md)
  for the full column list and rationale.
- `company_members` table, with a **unique constraint** on
  `(company_id, user_id)` and a **partial unique index** on `company_id
  WHERE role = 'owner'` enforcing the single-Owner invariant at the
  database level.
- Both FKs `ON DELETE CASCADE` from `company_members` to `companies` and
  `users`.
- Verified: applies cleanly (`alembic upgrade head`) against a freshly
  created database, and round-trips (upgrade → downgrade → upgrade)
  without error.

## 4. API Endpoints

All under `/api/v1/companies`, all with request validation (Pydantic),
authorization (company-scoped RBAC via `require_company_role`), OpenAPI
documentation (auto-generated, see `docs/architecture/openapi.json`),
and the standard error envelope:

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/companies` | Verified user | Creator becomes Owner atomically |
| GET | `/companies` | Any user | Companies the caller is a member of |
| GET | `/companies/search` | None (public) | Name/industry/country/city filters, pagination, sorting |
| GET | `/companies/slug/{slug}` | None (public) | Public profile |
| GET | `/companies/{company_id}` | Member (any role) | Full detail; 404 for non-members |
| PATCH | `/companies/{company_id}` | Editor+ | Editor restricted from legal_name/gst_number |
| DELETE | `/companies/{company_id}` | Owner | Soft-delete (archive) |
| POST | `/companies/{company_id}/members` | Admin+ | Creates a pending invite |
| GET | `/companies/{company_id}/members` | Member (any role) | Roster |
| PATCH | `/companies/{company_id}/members/{member_id}` | Admin+, or self (accept only) | Also the ownership-transfer mechanism (`role: "owner"`) |
| DELETE | `/companies/{company_id}/members/{member_id}` | Admin+, or self (leave) | Blocked for the Owner |

**Deviation from the brief, flagged explicitly:** the brief's endpoint
list included both `GET /companies/{id}` and `GET /companies/{slug}` —
identical path templates that FastAPI cannot route distinctly. Resolved
as `/companies/{company_id}` and `/companies/slug/{slug}`.

## 5. Frontend Pages (Next.js)

| Page | Route | Notes |
|---|---|---|
| Company List | `/companies` | Loading/empty/error states |
| Create Company | `/companies/new` | Full form, client-side + server validation |
| Company Dashboard | `/companies/[id]` | Name, logo placeholder, industry, location, member count, verification badge, created date |
| Company Settings | `/companies/[id]/settings` | Edit (role-gated fields), delete with confirmation, transfer-ownership placeholder |
| Public Company Profile | `/company/[slug]` | Server Component, no auth required |
| Company Search | `/companies/search` | Debounced filters, sorting, pagination |

Responsive via CSS Grid `auto-fit`/`minmax` and fluid containers rather
than fixed breakpoints. **Verified via a complete, successful
`next build`** — all 6 routes compiled (confirmed in the build output,
not assumed).

**Deviation from the brief, flagged explicitly:** kept Next.js 14.2.5
(already verified working end-to-end) rather than upgrading to the
brief's stated Next.js 15 — an unrelated, large, risky framework
upgrade with no specific action item requesting it, weighed against the
brief's own "do not break existing tests" instruction.

## 6. Flutter Screens

`CompanyListScreen`, `CreateCompanyScreen`, `CompanyDashboardScreen`,
`EditCompanyScreen` — loading/error/offline states throughout (offline
detected via the existing `ApiClient`'s `NETWORK_ERROR` code, not a
dedicated connectivity package — a deliberate scope simplification).
Wired into `AuthGate`'s navigation. Uses the existing architecture
(`ApiClient`, `SecureTokenStorage`, feature-first folder structure)
exactly as instructed.

**Confidence caveat, stated plainly:** Flutter/Dart tooling is not
available in this environment. These screens are verified by careful
static review only — cross-file reference checks, brace/paren balance,
and API-contract consistency checked against the real, live-tested
backend responses — not by an actual Dart analyzer or compiler run. Two
real bugs were still found this way (a `getJson`/`getJsonList` envelope
mismatch, and a dubious `ApiResult<void>` usage) — reasonable confidence,
not the same certainty as the backend/web verification.

## 7. Tests Added

- **Backend:** `tests/test_companies.py` (24 tests — creation, slugs,
  multi-company ownership, IDOR protection, public profile/search,
  graduated update authorization, delete/archive) and
  `tests/test_company_members.py` (16 tests — invite/accept lifecycle,
  role changes, removal/self-leave, single-Owner invariant from both
  the application and database level, ownership transfer). Plus
  regression tests for both bugfixes (ADR-0025, ADR-0026) and the
  dependency-ordering fix.
- **Total backend suite: 91 tests**, run against real Postgres + Redis
  (not mocked), confirmed stable across 3 consecutive full-suite runs
  from a freshly created database.
- **Frontend:** 2 new test files (`companies-search.test.ts` — query
  string construction; `api-client-204.test.ts` — the 204-handling
  regression). Web suite: 7/7 passing.
- **Flutter:** none — no test run was possible without Dart tooling;
  static review only, as stated in Section 6.

## 8. Documentation Added

ADRs 0022–0026 (five, including two detailed bugfix incident reports),
`docs/architecture/company-core-data-model.md`,
`docs/architecture/company-core-sequences.md`, a regenerated
`openapi.json` (21 endpoints), a coding-standards addition (the enum
`values_callable` rule), and this report.

## 9. Known Limitations

1. **`Company.industry` is a free-text string**, not a controlled
   taxonomy — search-by-industry uses substring matching. Deliberate
   (ADR-0023); revisit when a Products/Search module needs real
   taxonomy.
2. **`Company.verification_status` is always `unverified`** — no
   `Verification` aggregate exists yet. Deliberate (ADR-0023).
3. **Email verification still can't reach real inboxes** outside local
   dev (Module 2.5's unresolved gap) — `POST /companies` requires a
   verified email, so this blocks real company creation in any deployed
   environment until Module 2.5's email-provider gap closes.
4. **Ownership transfer has no dedicated UI** on any client — a
   deliberate, brief-sanctioned placeholder (the brief explicitly says
   "Transfer ownership (placeholder only)"); the API mechanism is fully
   functional and tested.
5. **Flutter screens are unverified by any compiler/analyzer** — static
   review only, per Section 6.
6. **Two bugs found in this module affected the entire pre-existing
   application, not just Module 3A** (ADR-0025, ADR-0026) — both are
   fixed and verified, but their prior undetected presence (since
   Module 2, in the enum case) is itself worth noting as a reminder that
   `Base.metadata.create_all`-based test schemas can mask real
   deployment bugs, as ADR-0025 discusses.
7. **No component-level tests exist for the new React pages themselves**
   (only for pure logic — query-string building, the 204 fix) — the
   pages were verified via a real `next build` and manual reasoning
   about their logic, not via React Testing Library component tests.

## 10. Production Readiness Score

| Category | Score | Why |
|---|---|---|
| Architecture | 9/10 | Clean layering, ADR-documented decisions; industry/verification simplifications are deliberate and reversible |
| Security | 9/10 | Company-scoped RBAC fully separated from platform RBAC; IDOR-safe (404 for non-members, auth-before-existence dependency ordering fixed); email-verification gate correctly enforced |
| Data Integrity | 9/10 | Single-Owner invariant enforced at both application and database level, independently verified; two real transaction-ordering/enum bugs found and fixed with regression tests |
| Code Quality | 9/10 | ruff, mypy --strict, tsc, and ESLint all clean; 91 backend + 7 web tests passing, confirmed stable across repeated runs |
| Testing | 8/10 | Backend and web thoroughly verified against real infrastructure; **Flutter has zero automated verification** (tooling unavailable) |
| Documentation | 9/10 | 5 new ADRs, 2 new architecture docs, regenerated OpenAPI spec, this report |
| Deployment Readiness | 6/10 | Blocked in practice by Module 2.5's still-open email-provider gap, since company creation requires email verification |

**Overall: ready for Module 3B**, with the email-provider dependency
(shared with Module 2.5, not new to this module) as the one real
deployment blocker, and the Flutter verification gap stated honestly
rather than glossed over.
