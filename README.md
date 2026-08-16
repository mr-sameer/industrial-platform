# ForgeX

An AI-powered platform for industrial trust, procurement, and analytics —
this repository currently ships **Module 1 (foundation)** and **Module 2
(authentication)**: monorepo scaffolding, app shells for web/mobile/API,
infrastructure, engineering standards, and a working JWT-based auth flow
across all three clients. **No business/domain features are implemented
yet.**

## What's here

| Layer | Tech | Location |
|---|---|---|
| Web | Next.js 14 (App Router), TypeScript | `apps/web` |
| Mobile | Flutter | `apps/mobile` |
| API | FastAPI, SQLAlchemy 2.0 (async), Alembic | `apps/api` |
| Database | PostgreSQL 16 | via `docker-compose.yml` |
| Cache | Redis 7 | via `docker-compose.yml` |
| Auth | JWT (access + refresh), bcrypt password hashing | `apps/api/app/core/security.py` + `docs/adr/0010`–`0013` |
| Shared TS packages | `shared-types`, `ui`, `eslint-config`, `tsconfig` | `packages/*` |

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) + Docker Compose v2
- Node.js 20.11+ and [pnpm](https://pnpm.io/) 9+ (`corepack enable`)
- Python 3.12+
- Flutter 3.22+ (only if working on `apps/mobile`)

## Quick start (Docker — recommended)

```bash
git clone <this-repo>
cd industrial-platform
cp .env.example .env      # adjust values if needed; defaults work for local dev
docker compose up --build
```

- Web: http://localhost:3000 — home page, `/register`, `/login`, protected `/dashboard`, `/health`
- API: http://localhost:8000/docs (interactive OpenAPI docs)
- API health: http://localhost:8000/health

The `users` table is created by Alembic. `docker compose up` runs
`alembic upgrade head` automatically before starting the API (see
`docker-compose.yml`); running it outside Docker requires the manual step
shown below.

`docker-compose.override.yml` is auto-loaded and gives the web container
hot reload via `next dev`; the API container already runs with
`--reload`. Postgres and Redis data persist in named volumes
(`postgres-data`, `redis-data`) across restarts.

## Running services individually (without Docker)

**API:**
```bash
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env      # point DATABASE_URL/REDIS_URL at local or Dockerized services
# First time only: Docker's postgres image auto-creates its role/database
# from POSTGRES_USER/PASSWORD/DB on first start — a bare local Postgres
# install has no such automatic step, so run this once to create them:
./scripts/bootstrap_local_postgres.sh
alembic upgrade head
uvicorn app.main:app --reload
```

**Web:**
```bash
pnpm install               # from repo root — installs all JS/TS workspaces
cp apps/web/.env.example apps/web/.env.local
pnpm --filter web dev
```

**Mobile:** see [`apps/mobile/README.md`](apps/mobile/README.md) — requires
a one-time `flutter create .` to generate native platform folders.

## Trying the auth flow

1. Web: visit http://localhost:3000/register, create an account, land on
   `/dashboard`. Reload the page — the session survives via the httpOnly
   refresh cookie (see `docs/adr/0012-web-session-strategy.md`).
2. API directly: `POST /api/v1/auth/register` with
   `{"email": "...", "password": "at-least-10-chars-1", "full_name": "..."}`,
   then use the returned `access_token` as `Authorization: Bearer <token>`
   against `GET /api/v1/auth/me`.
3. Mobile: launch the app — it opens on the login screen; register or log
   in, and the session persists across app restarts via secure storage.

**Hit a 429 while testing register/login repeatedly?** That's the real,
unweakened rate limiter — in pure local dev (no proxy in front of
`next dev`), every request looks identical to it, so a normal afternoon
of manual testing exhausts it faster than a real deployment would. Run
`make reset-rate-limit` (or `bash apps/api/scripts/reset_dev_rate_limits.sh`)
to clear only the auth rate-limit keys — never a full Redis flush. See
`docs/adr/0036-local-dev-rate-limit-workflow.md`.

## Testing

```bash
pnpm turbo run test --filter=web      # web unit tests (Vitest), incl. auth-envelope test
cd apps/api && pytest --cov=app       # API tests (pytest, requires Postgres+Redis reachable)
cd apps/mobile && flutter test        # mobile widget tests
```

## Linting & type-checking

```bash
pnpm lint          # ESLint across web + packages
pnpm typecheck      # tsc --noEmit across web + packages
cd apps/api && ruff check . && mypy app
cd apps/mobile && flutter analyze
```

## Documentation map

- [`docs/domain/`](docs/domain) — the full business domain model (18
  sections): bounded contexts, entities, aggregates, permission matrix,
  and future-stage readiness. The source of truth for every business
  module built on top of it.
- [`docs/modules/`](docs/modules) — per-module completion reports:
  [Module 3A](docs/modules/module-3a-completion-report.md),
  [Module 3B](docs/modules/module-3b-completion-report.md) — each with a
  production readiness score.
- [`docs/architecture/`](docs/architecture) — system context, container,
  request-lifecycle, auth data model, company core data model, company
  verification data model, and sequence diagrams (Mermaid, render on
  GitHub), plus a generated [`openapi.json`](docs/architecture/openapi.json)
  (32 endpoints as of Module 3B — regenerate via
  `apps/api/scripts/export_openapi.py`).
- [`docs/adr/`](docs/adr) — Architecture Decision Records; read these before
  proposing a change to any decision they cover.
- [`docs/standards/`](docs/standards) — coding standards, naming conventions,
  the API response envelope spec (including auth error codes), and the
  logging standard.
- [`docs/security/`](docs/security) — the Module 2.5 architecture review,
  security checklist, threat model, and deployment notes. **Read
  `deployment-notes.md` before deploying anywhere beyond local dev** —
  it lists what must change from the local-dev defaults.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — how to propose changes, branch/commit
  conventions, and the PR checklist.

## Repository layout

See [`docs/architecture/repo-structure.md`](docs/architecture/repo-structure.md)
for the annotated folder tree.

## Status

- **Module 1 (foundation): complete.**
- **Module 2 (authentication): complete.**
- **Module 2.5 (auth hardening & production readiness): complete**, with
  known, explicitly-tracked gaps — see
  [`docs/security/module-2.5-production-readiness-report.md`](docs/security/module-2.5-production-readiness-report.md)
  for the full scored review. In short: refresh tokens now rotate and
  detect reuse (server-side revocation finally works — Module 2's gap is
  closed), sessions are listable/revocable per-device, Argon2id replaces
  bcrypt as the default hash, rate limiting + progressive lockout protect
  every auth endpoint, audit logging exists, and security headers are on
  every response. **The one deployment blocker that remains: no real
  email provider is wired up**, so email verification and password reset
  don't reach real inboxes yet outside local dev (`docs/adr/0019`) — this
  requires a vendor decision this module deliberately didn't make.
- **Module 3 Preparation (domain model): approved.** See
  [`docs/domain/`](docs/domain) for the full 18-section business domain
  model — bounded contexts, entities, aggregates, permission matrix, and
  a self-critical architecture review (Section 18) that this and future
  modules resolve against.
- **Module 3A (Company Core): complete.** See
  [`docs/modules/module-3a-completion-report.md`](docs/modules/module-3a-completion-report.md)
  for the full report (architecture summary, files changed, endpoints,
  tests, known limitations, production readiness score). In short:
  companies can be created, managed (Owner/Admin/Editor/Viewer roles),
  searched, and publicly viewed, across API, web, and mobile — with two
  genuinely critical, previously-latent bugs affecting the *entire*
  application (not just this module) found and fixed along the way, see
  [ADR-0025](docs/adr/0025-enum-values-callable-bugfix.md).
- **Module 3B (Company Verification & Industrial Identity): complete.**
  See [`docs/modules/module-3b-completion-report.md`](docs/modules/module-3b-completion-report.md)
  for the full report. In short: companies now have business
  identity (legal entity type, GSTIN/PAN/CIN/MSME/IEC), branding
  (logo with auto-generated thumbnail, responsive cover image),
  industry classification, social links, and a document-upload system
  with versioning/soft-delete/audit trail — all feeding a
  configuration-driven verification-scoring engine
  (Unverified → Email Verified → Business Verified → Factory Verified →
  Premium Verified) that is **always computed live, never a manually
  editable field**. Module 3A is untouched — every 3B endpoint lives in
  a new router file, every new column is additive.

## Notable Fix Between Modules 3A and 3B

A real production bug was reported and fixed between modules:
`pnpm dev`'s pino-pretty pipe broke `docker compose up --build` (the dev
container's primary process depended on a CLI binary that wasn't
resolvable at container runtime). See
[ADR-0027](docs/adr/0027-logger-transport-crash-fix.md) and
[ADR-0028](docs/adr/0028-docker-dev-script-must-not-require-pino-pretty.md)
for the full incident — Docker's dev path no longer pipes through
anything; pretty-printed local logs are opt-in via `pnpm dev:pretty`.

## Module 3C Readiness Checklist

- [x] `companies` gains 24 new additive columns; `verification_documents`
      and `company_social_links` tables added via Alembic (`0004`) —
      round-tripped (upgrade → downgrade → upgrade) against a real
      database. A genuinely new Alembic finding surfaced here: unlike
      `create_table`, `op.add_column` on an *existing* table does **not**
      auto-create the enum type it references — the opposite of the rule
      Module 3A discovered — found via a real failed migration run, now
      documented in the migration itself for the next person who hits it
- [x] Verification scoring is configuration-driven (13 weighted
      requirements summing to exactly 100, asserted at import time),
      computed live on every request, and **structurally impossible to
      edit directly** — no endpoint anywhere accepts a client-supplied
      percentage or level
- [x] Document upload/replace/delete with real versioning (soft delete +
      `superseded_by_id` chain) and a full audit trail via the existing
      `AuditLog` (Module 2.5) — no new audit system built
- [x] File storage is backend-abstracted (`StorageBackend` protocol) —
      local disk today, S3-shaped interface from day one; every upload
      validated by actually decoding the file content (Pillow / PDF
      magic bytes), never by trusting the client-declared type
- [x] Web: all 5 required pages (Verification Dashboard, Business
      Information, Documents, Branding, Social Links), real
      `tsc`/ESLint/Vitest, and a **verified real `next build`** with all
      new routes compiled
- [x] Mobile: all 5 required screens (Verification Dashboard, Business
      Info, Documents, Branding, Progress) plus navigation wiring —
      verified by static review only (no Flutter/Dart tooling in this
      environment, same limitation as every prior module); the brief's
      own Flutter section doesn't list a Social Links screen (unlike the
      web frontend), so its absence here is scope-matching, not a gap
- [x] 112 backend tests passing against real Postgres + Redis — including
      uploading and re-fetching real generated images/PDFs over HTTP —
      confirmed stable; ruff, ruff format, and mypy --strict all clean
- [x] ADR-0029 committed, consolidating 9 scope/design decisions (field
      reuse from Module 3A, the "Company Owner" permission
      interpretation, why Factory Verified needs no Factory entity yet,
      the storage/validation/static-serving design)
- [ ] **Not done — explicit gap, not an oversight:** no admin-approval
      workflow for verification documents exists — `verified_by`/
      `verified_at` are genuinely unset placeholders, exactly as the
      module brief specified. The scoring engine counts a document once
      *uploaded*, not once *approved* — see ADR-0029 decision #3 for why,
      and what a future admin-review module would need to change.
- [ ] **Not done:** the Module 2.5 email-provider gap is still open —
      unchanged from Module 3A's status.

**Module 3C can begin**, with the gaps above tracked and documented
rather than silently ignored.

