# Repository Structure

```
industrial-platform/
├── apps/
│   ├── web/          # Next.js 14 (App Router, TypeScript, standalone output)
│   ├── api/           # FastAPI (async SQLAlchemy, Alembic, structlog)
│   └── mobile/        # Flutter (app shell + health screen)
├── packages/
│   ├── shared-types/  # TS contracts shared by web (and, via mirrored Dart/Pydantic types, mobile/api)
│   ├── ui/            # Shared presentational React components
│   ├── eslint-config/ # Shared ESLint config
│   └── tsconfig/      # Shared tsconfig bases
├── infra/
│   └── docker/        # Postgres initdb scripts, infra-level config
├── docs/
│   ├── architecture/  # This directory — diagrams
│   ├── adr/           # Architecture Decision Records
│   └── standards/     # Coding standards, naming, API response, logging
├── .github/workflows/ # CI (web/api/mobile/docker-build), PR title lint
├── docker-compose.yml # Local dev stack: web, api, postgres, redis
├── turbo.json         # Turborepo task pipeline (JS/TS side)
└── pnpm-workspace.yaml
```

**Why this shape:** `apps/*` are deployable units; `packages/*` are
internal libraries with no independent deployment; `infra/*` holds
infrastructure config that isn't tied to one app; `docs/*` is versioned
alongside the code it documents so it never drifts out of a separate wiki.
