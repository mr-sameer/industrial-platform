# 0002 — Next.js 14 (App Router) for the Web App

## Status
Accepted

## Context
The web app needs to serve both marketing/public pages and, in later
modules, authenticated dashboards with a mix of server-rendered data
fetching and client interactivity — for an analyst-facing product where
SEO for public reports and fast dashboard interactivity both matter.

## Decision
Use Next.js 14 with the App Router, TypeScript, and `output: "standalone"`
for lean Docker images. Server Components by default; `"use client"` only
where interactivity is required (see `docs/standards/coding-standards.md`).

## Alternatives considered
- **Remix**: strong data-loading model, smaller ecosystem/hiring pool;
  Next.js chosen for ecosystem maturity and the team's existing familiarity
  from prior related work.
- **Plain Vite + React SPA**: simpler mental model but no built-in SSR/SEO
  story, which matters for publicly-shared equity/industrial reports.
- **Pages Router (Next.js legacy)**: rejected in favor of App Router since
  this is a new project with no legacy-router code to migrate.

## Consequences
- Route Handlers (`src/app/api/**/route.ts`) exist for web-local concerns
  (e.g. the web app's own `/api/health`); business API calls go through
  `apps/api` (FastAPI), not through Next.js API routes, keeping business
  logic in one service.
- `transpilePackages: ["@platform/shared-types", "@platform/ui"]` is
  required in `next.config.mjs` since those packages ship untranspiled TS.
