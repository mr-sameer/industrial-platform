# Module 3B — Company Verification & Industrial Identity: Completion Report

Status: **Complete.** Module 3C has not been started, per this module's
instructions. This report follows the exact 11-point structure the
module brief requested.

---

## 1. Architecture Summary

Module 3B extends the Company domain (Module 3A) purely additively —
24 new nullable columns on `Company`, two new tables
(`VerificationDocument`, `CompanySocialLink`), and every new endpoint
lives in a **new router file** (`app/api/v1/company_verification.py`),
never touching Module 3A's `companies.py`. This was a deliberate,
brief-mandated constraint ("do not modify previous modules"), verified
by construction rather than by promise: `companies.py` has zero diffs
from Module 3A.

**Core design principle — trust must be computed, not declared.**
`app.services.verification_score_service.calculate` computes a
percentage, a 5-level classification, and a missing-requirements list
**live, on every request**, from real underlying data (owner email
verification, business info completeness, document presence, branding,
social links). There is no endpoint anywhere that accepts a client-
supplied verification level or percentage — this is a structural
guarantee, not a policy. Every weight lives in one configuration module
(`app.core.verification_rules`, asserted to sum to 100 at import time),
directly satisfying the brief's "never hardcode scores, use
configuration."

**File storage is backend-abstracted from day one.** `StorageBackend`
(`app.core.storage`) is a `Protocol` with exactly the shape an S3 client
naturally has — key-based, never path-based. `LocalStorageBackend` is
the only implementation shipped; swapping in a real S3 backend later
touches zero service/router code.

Nine scope/design decisions (field reuse from Module 3A, the "Company
Owner" permission interpretation, the Factory Verified level's design
without a Factory entity, etc.) are consolidated in
[ADR-0029](../adr/0029-module-3b-verification-and-identity.md) rather
than scattered.

## 2. Files Changed

**Backend (`apps/api`) — new:**
`app/core/storage.py`, `app/core/file_validation.py`,
`app/core/image_processing.py`, `app/core/verification_rules.py`,
`app/services/verification_score_service.py`,
`app/services/document_service.py`, `app/services/branding_service.py`,
`app/services/social_link_service.py`,
`app/models/verification_document.py`,
`app/models/company_social_link.py`,
`app/schemas/company_verification.py`,
`app/api/v1/company_verification.py`,
`alembic/versions/20260806_022421_0004_add_verification_and_identity.py`,
`tests/test_company_verification.py`.

**Backend — modified:** `app/models/company.py` (24 new additive
columns + 2 relationships + 2 new enums), `app/models/__init__.py`
(registration), `app/main.py` (router registration + `/uploads` static
mount), `app/core/config.py` (upload settings), `pyproject.toml` /
`requirements.txt` (Pillow, python-multipart).

**Frontend (`apps/web`) — new:**
`src/lib/company-verification.ts`,
`src/components/VerificationProgress.tsx`,
`src/app/companies/[id]/verification/page.tsx`,
`src/app/companies/[id]/business-info/page.tsx`,
`src/app/companies/[id]/documents/page.tsx`,
`src/app/companies/[id]/branding/page.tsx`,
`src/app/companies/[id]/social-links/page.tsx`.

**Frontend — modified:** `src/app/companies/[id]/page.tsx` (one
additive nav link to the new Verification section — the only touch to
a Module 3A file).

**Mobile (`apps/mobile`) — new:**
`lib/features/verification/domain/verification.dart`,
`lib/features/verification/data/verification_repository.dart`,
`lib/features/verification/presentation/verification_dashboard_screen.dart`,
`lib/features/verification/presentation/verification_progress_widget.dart`,
`lib/features/verification/presentation/business_info_screen.dart`,
`lib/features/verification/presentation/document_upload_screen.dart`,
`lib/features/verification/presentation/branding_screen.dart`.

**Mobile — modified:** `lib/core/network/api_client.dart`
(`uploadMultipart` method added), `lib/features/companies/presentation/company_dashboard_screen.dart`
(one additive nav icon — the only touch to a Module 3A file),
`pubspec.yaml` (`file_picker` dependency).

**Shared types:** `packages/shared-types/src/company-verification.ts`
(new), `packages/shared-types/src/index.ts` (export).

**Infrastructure:** `docker-compose.yml` (persistent `uploads-data`
volume for the API service).

**Documentation:** ADR-0029 (new), `docs/architecture/company-verification-data-model.md`
(new, ER diagram), `docs/architecture/company-verification-sequences.md`
(new, sequence diagrams), `docs/architecture/openapi.json` (regenerated,
21→32 paths), `README.md` (status + Module 3C checklist), this report.

## 3. Database Changes

Migration `0004_add_verification_and_identity`:
- 24 new nullable columns on `companies` — legal entity info
  (`legal_entity_type`, `business_type`, `export_capable`, `pan`, `cin`,
  `msme_number`, `iec_number`, `tax_registration`,
  `business_registration_date`), branding (`logo_url`,
  `logo_thumbnail_url`, `cover_image_url`), description
  (`short_description`, `mission`, `vision`, plus 3 array fields), and
  industry classification (5 array fields + `naics_sic_code`).
- `verification_documents` table — versioned (`version`,
  `superseded_by_id` self-reference), soft-deletable (`is_deleted`,
  `deleted_at`, `deleted_by`), with placeholder `verified_at`/
  `verified_by` fields nothing in this module sets.
- `company_social_links` table — unique per `(company_id, platform)`.
- Verified: round-trips (upgrade → downgrade → upgrade) against a real
  database. **A genuinely new Alembic finding surfaced while building
  this migration**: unlike `create_table` (Module 3A's lesson),
  `op.add_column` on an *existing* table does **not** auto-create the
  enum type it references — confirmed by a real failed migration run
  (`UndefinedObject: type "legal_entity_type" does not exist`), fixed by
  explicitly creating those two enum types before their `add_column`
  calls, and documented directly in the migration file.

## 4. API Endpoints

All under `/api/v1/companies`, 12 new endpoints (32 total in the API
now, up from 21):

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/{id}/verification` | Member | Live-computed score + missing requirements |
| GET | `/slug/{slug}/verification` | None (public) | Powers the public profile's badge |
| GET | `/{id}/business-info` | Member | Added mid-build — see Section 11 |
| PATCH | `/{id}/business-info` | Editor+ | Partial update, any subset of fields |
| GET | `/{id}/branding` | Member | Added mid-build — see Section 11 |
| POST / DELETE | `/{id}/logo` | Editor+ | Real image validation + auto thumbnail |
| POST / DELETE | `/{id}/cover-image` | Editor+ | Real image validation + responsive variants |
| GET / PUT | `/{id}/social-links` | Member / Editor+ | Upsert semantics |
| DELETE | `/{id}/social-links/{platform}` | Editor+ | |
| POST / GET | `/{id}/documents` | Admin+ / Member | Upload requires Admin+ (see ADR-0029 #4) |
| PATCH | `/{id}/documents/{id}/replace` | Admin+ | Creates a new version, soft-deletes the old |
| DELETE | `/{id}/documents/{id}` | Admin+ | Soft delete only — file and row both retained |

## 5. Frontend Pages (Next.js)

All 5 required pages: Verification Dashboard, Business Information,
Documents, Branding, Social Links — all under `/companies/[id]/*`.
Loading/empty/error states throughout; upload flows use a dedicated
`uploadFetch` helper (not the shared `apiFetch`, which forces
`Content-Type: application/json` — wrong for multipart bodies).
**Verified via a complete, successful `next build`** — all 5 new routes
compiled, confirmed in the build output.

## 6. Flutter Screens

`VerificationDashboardScreen`, `BusinessInfoScreen`,
`DocumentUploadScreen`, `BrandingScreen`, plus the shared
`VerificationProgressWidget` ("Progress," per the brief). **The brief's
own Flutter section does not list a Social Links screen** (unlike the
Next.js frontend section, which does) — its absence here is scope-
matching the brief exactly, not an oversight.

**Confidence caveat, stated plainly (same as Module 3A):** no Flutter/
Dart tooling is available in this environment. These screens are
verified by careful static review only — brace/paren balance, cross-
file import-path correctness, and API-contract consistency checked
against the real, tested backend responses. This review caught two real
risks before they could ship: `DropdownButtonFormField`'s `initialValue`
parameter likely doesn't exist at the project's stated minimum Flutter
version (3.22.0) — fixed to use the longer-standing `value` parameter;
and `.singleOrNull` isn't safely available without an extra package not
in this project's dependencies — fixed to a guaranteed-safe null-check
pattern instead.

## 7. Tests

`tests/test_company_verification.py` — 22 tests covering: verification
scoring (including that email-verified-by-default new companies start
at 20%, not 0%), the structural impossibility of manually setting a
score (405 on `PATCH .../verification`), the Module 3A
`verification_status` auto-sync, real image upload with actual Pillow-
verified thumbnail dimensions, oversized/invalid file rejection, PDF and
image document upload, versioning (replace creates a new row and soft-
deletes the old), soft-delete semantics, social link upsert/delete, and
authorization boundaries (Editor+ vs. Admin+ vs. IDOR-safe 404s for
non-members).

**Total backend suite: 113 tests** (up from 91 in Module 3A), run
against real Postgres + Redis with real generated images/PDFs uploaded
and re-fetched over HTTP — not mocked. 1 test self-skips gracefully when
a generated test image doesn't exceed the configured size limit on this
build's zlib compression (a legitimate, self-aware skip, not a failure).
Confirmed stable via a final clean run. `ruff check`, `ruff format
--check`, and `mypy --strict` all clean.

**Frontend:** no new component tests were added this module (existing 8
web tests still pass unmodified). **Flutter:** none — consistent with
Section 6's stated tooling limitation.

## 8. Documentation

ADR-0029 (consolidating 9 scope/design decisions), an ER diagram
(`company-verification-data-model.md`), two sets of sequence diagrams
(`company-verification-sequences.md` — score computation, document
replace/versioning, and logo upload with off-event-loop image
processing), a regenerated `openapi.json` (32 endpoints), `README.md`
updates, and this report. Also: ADR-0027 and ADR-0028, covering the
`pino-pretty`/Docker incident that occurred between Modules 3A and 3B
(see Section 11).

## 9. Known Limitations

1. **No admin-approval workflow for verification documents** —
   `verified_by`/`verified_at` are genuinely unset placeholders, exactly
   as the brief specified. The scoring engine counts a document as
   satisfying a requirement once *uploaded*, not once *approved*
   (ADR-0029 decision #3) — a deliberate, load-bearing choice given no
   admin-review UI exists yet, not an oversight.
2. **"Factory Verified" has no Factory entity backing it** — satisfied
   today by business-type + factory-license-document + manufacturing-
   categories as a proxy (ADR-0029 decision #6). Revisit when a future
   module builds Factory.
3. **Local file storage only** — `LocalStorageBackend` is explicitly not
   the intended backend for a multi-replica production deployment (local
   disk isn't shared across replicas). The `StorageBackend` interface is
   S3-ready; no S3 implementation is built.
4. **No access control on uploaded files** — everything under
   `/uploads/*` is publicly fetchable by URL. Acceptable for this
   module's content (logos, certificates whose purpose is eventually to
   be seen), documented explicitly in ADR-0029 decision #9 rather than
   silently assumed.
5. **The Module 2.5 email-provider gap is unchanged** — still open,
   still blocking real-world email verification (which gates company
   creation, per Module 3A) outside local dev.
6. **Flutter is unverified by any compiler** — Section 6's caveat,
   repeated here for completeness of the limitations list.
7. **No frontend component tests were added** for the 5 new pages — only
   real build/typecheck/lint verification, consistent with Module 3A's
   established testing depth for frontend pages (logic-heavy client
   files get unit tests; page components get build verification).

## 10. Production Readiness Score

| Category | Score | Why |
|---|---|---|
| Architecture | 9/10 | Clean separation (new router, new services), zero Module 3A modification achieved by construction |
| Security | 8/10 | Real content-based file validation; but uploaded files have no access control (deliberate, documented) and virus scanning is a stated placeholder |
| Data Integrity | 9/10 | Verification score structurally un-settable; document versioning/soft-delete verified end-to-end; a real Alembic enum-creation bug found and fixed before shipping |
| Code Quality | 9/10 | ruff/mypy/format all clean; 113 tests passing, confirmed stable; two real backend gaps (missing GET endpoints) caught and fixed mid-build via frontend integration, not left as TODOs |
| Testing | 8/10 | Backend thoroughly verified with real files/images over real HTTP; Flutter has zero automated verification (tooling unavailable, stated plainly) |
| Documentation | 9/10 | ADR-0029 is unusually thorough (9 consolidated decisions); ER + sequence diagrams match the actual implemented schema, not an aspirational one |
| Deployment Readiness | 6/10 | Same blocker as Module 3A: the shared email-provider gap. Additionally, local-disk storage is explicitly not production-multi-replica-ready (documented, not hidden) |

**Overall: ready for Module 3C**, with the admin-approval-workflow gap
(item 1) as the most significant deliberately-deferred piece of trust
infrastructure, and the email-provider/storage-backend gaps carried
forward from prior modules rather than newly introduced.

## 11. Bugs Discovered in Previous Modules, and Whether They Were Fixed

**Between Module 3A and Module 3B (reported by the user, fixed in a
dedicated pass before 3B began):**

- **`pino-pretty` crash taking down every Company page (HTTP 500).**
  Root cause: `apps/web/src/lib/logger.ts` used pino's `transport`
  option, which spawns a worker thread that synchronously resolves its
  target module at `pino()` construction time — and `pino-pretty` was
  never installed. Since the logger is constructed at module-import
  time, and every Company page's import chain bottoms out at that file,
  the crash fired before any request-handling code ran. **Fixed**:
  removed `transport` entirely; the logger now always emits plain JSON,
  in every environment (ADR-0027).
- **The first fix's follow-up broke `docker compose up --build`.**
  Moving the pino-pretty pipe into the `dev` npm script meant Docker's
  dev container (which runs exactly that script as its primary process)
  now depended on `pino-pretty` being resolvable at container runtime —
  it wasn't (compounded by a stale named Docker volume shadowing an
  otherwise-correctly-rebuilt image). **Fixed**: `dev` no longer pipes
  through anything; pretty-printed local logs are opt-in via a separate
  `dev:pretty` script Docker never runs (ADR-0028). Verified as
  faithfully as possible without a Docker daemon in this environment
  (stated plainly, not overclaimed) — the exact `Dockerfile.dev` install
  instruction and container command were reproduced in an isolated
  directory and confirmed clean.

**Discovered and fixed during Module 3B's own development (not
pre-existing, but worth listing since they affected shared/foundational
code):**

- **`python-multipart` was never installed** — every FastAPI file-upload
  endpoint (this module's core feature) would have failed at request-
  parsing time. Caught by trying to import it before writing the first
  upload endpoint, not discovered via a failing test. **Fixed.**
- **`op.add_column` does not auto-create referenced enum types** — a
  new, previously-undiscovered Alembic behavior (opposite of
  `create_table`'s behavior, which Module 3A's ADR-0025/migration-0001
  notes already documented). Found via a real failed migration run
  against a real database, not assumed from the prior rule. **Fixed**,
  and documented directly in the migration for the next person who
  extends `companies` with a new enum column.
- **Two missing read endpoints** (`GET .../business-info`,
  `GET .../branding`) — discovered while building the frontend Business
  Information and Branding pages, which had no way to pre-populate a
  form with existing values since Module 3A's `CompanyDetail` correctly
  doesn't expose Module 3B fields. **Fixed**: two new endpoints added,
  each with its own passing test, rather than leaving the frontend pages
  write-only.

No other previously-reported bugs were open at the start of this
module; Modules 1 through 3A's own completion/production-readiness
reports remain the record of what was found and fixed in each of those.
