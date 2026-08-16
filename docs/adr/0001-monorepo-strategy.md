# 0001 — Monorepo Strategy: pnpm workspaces + Turborepo

## Status
Accepted

## Context
The platform ships three deployable clients (web, mobile, API) plus shared
TypeScript contracts and UI components. We need one place to reason about
the whole system, atomic cross-cutting changes (e.g. updating a shared
type and its three consumers in one PR), and a single CI entry point —
without forcing Python and Dart into the same package manager as
TypeScript, which they don't belong in.

## Decision
- A single Git repository (`industrial-platform/`) houses `apps/*` and
  `packages/*`.
- **JavaScript/TypeScript side** (`apps/web`, `packages/*`): pnpm
  workspaces for dependency management + Turborepo for task orchestration
  and caching (`lint`, `typecheck`, `test`, `build`).
- **Python** (`apps/api`) and **Dart** (`apps/mobile`) are *part of the
  monorepo folder structure* but *not* part of the pnpm workspace or
  Turborepo pipeline — they have their own tool-native dependency
  management (`pip`/`pyproject.toml`, `pub`/`pubspec.yaml`) and their own
  CI jobs that run in parallel with the JS pipeline.

## Alternatives considered
- **Polyrepo** (separate repos per app): rejected — makes shared-type
  changes require multi-repo coordination and versioning overhead this
  team doesn't need yet at three apps.
- **Nx**: capable alternative to Turborepo with similar caching; Turborepo
  chosen for lower configuration surface area and first-party Next.js
  integration, given the web app is Next.js.
- **npm/yarn workspaces instead of pnpm**: pnpm chosen for strict,
  non-hoisted `node_modules` (catches implicit/phantom dependencies) and
  disk-efficient content-addressable storage.

## Consequences
- One `pnpm install` at the root sets up all JS/TS dependencies.
- Python and Dart contributors do not need Node.js installed to work on
  `apps/api` or `apps/mobile` in isolation, and vice versa.
- CI (`.github/workflows/ci.yml`) runs three independent jobs
  (`web`, `api`, `mobile`) that can succeed/fail independently.
