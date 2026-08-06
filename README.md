# Industrial Intelligence Platform

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
- [`docs/modules/`](docs/modules) — per-module completion reports (e.g.
  [Module 3A](docs/modules/module-3a-completion-report.md)), each with a
  production readiness score.
- [`docs/architecture/`](docs/architecture) — system context, container,
  request-lifecycle, auth data model, company core data model, and
  sequence diagrams (Mermaid, render on GitHub), plus a generated
  [`openapi.json`](docs/architecture/openapi.json)
  (regenerate via `apps/api/scripts/export_openapi.py`).
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

## Module 3B Readiness Checklist

- [x] `companies` and `company_members` tables migrated via Alembic
      (`0003`) — round-tripped (upgrade → downgrade → upgrade) against a
      real database; single-Owner invariant enforced at the DB level via
      a partial unique index, verified by a test that bypasses the
      service layer entirely
- [x] Full company lifecycle — create / read / update / archive
      ("delete") / search / member invite+accept / role changes /
      ownership transfer / member removal — verified end-to-end,
      including a live server run against a real (not test-only)
      migrated database completing register → verify → create-company
      over real HTTP
- [x] Company-scoped RBAC (`CompanyRole`: Owner/Admin/Editor/Viewer) is
      fully distinct from the platform-level `Role` (ADR-0022), closing
      the Module 3 domain model's top-priority open recommendation
- [x] Web: all 6 required pages (list, create, dashboard, settings,
      public profile, search), real `tsc`/ESLint/Vitest, and a
      **verified real `next build`**
- [x] Mobile: all 4 required screens (list, create, dashboard, edit),
      wired into navigation — verified by static review only (no
      Flutter/Dart tooling in this environment, same limitation as
      Module 2.5)
- [x] 91 backend tests passing against real Postgres + Redis, confirmed
      stable across repeated runs; ruff, ruff format, and mypy --strict
      all clean
- [x] ADRs 0022–0026 committed, including two bugfix incident reports
      (0025, 0026) with full root-cause analysis
- [ ] **Not done — explicit gap, not an oversight:** `Industry`/
      `Category` as a controlled taxonomy and the full `Verification`
      aggregate are both deliberately deferred (ADR-0023) —
      `Company.industry` is a plain string and
      `Company.verification_status` is a placeholder always reading
      `unverified` until those modules exist.
- [ ] **Not done:** the email-provider gap from Module 2.5 is still
      open — company creation itself works regardless, but the
      email-verification requirement gating it (`require_verified_email`)
      still can't deliver real emails outside local dev.

**Module 3B can begin**, with the two gaps above tracked and documented
rather than silently ignored.

