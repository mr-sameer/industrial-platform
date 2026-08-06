# Coding Standards

These apply across `apps/web`, `apps/api`, `apps/mobile`, and `packages/*`.
Automated tooling (ESLint/Prettier, Ruff/mypy, `flutter analyze`) enforces
most of this in CI — this document explains the *reasoning*, not just the
rule, so contributors know when to bend a rule and when not to.

## General principles

1. **Explicit over clever.** Optimize for the next reader, not for fewer
   keystrokes. If a one-liner needs a comment to explain what it does,
   write it as three lines instead.
2. **Types are documentation.** Every function signature should be
   understandable without reading its body. TypeScript `strict` mode and
   Python `mypy --strict` are both on; do not weaken either.
3. **No silent failures.** Catch specific exceptions/errors, log them with
   context, and either recover or propagate a typed error. Never swallow
   an exception with an empty `except`/`catch` block.
4. **Small, reviewable units.** Prefer several focused PRs over one large
   one. A PR that touches more than ~400 lines of non-generated code
   should usually be split.
5. **Comment the "why," not the "what."** Code should be self-explanatory
   about *what* it does; comments exist to explain *why* a non-obvious
   decision was made (see inline comments throughout Module 1's source for
   the intended style).

## TypeScript / Next.js (`apps/web`, `packages/*`)

- `strict: true` everywhere (see `packages/tsconfig`). No `any` without a
  `// eslint-disable-next-line @typescript-eslint/no-explicit-any` and a
  comment explaining why it's unavoidable.
- Prefer named exports. Reserve default exports for Next.js special files
  (`page.tsx`, `layout.tsx`, `route.ts`) where the framework requires them.
- Server vs. client components: default to Server Components; add
  `"use client"` only where interactivity/state is required.
- No business logic inside JSX. Extract to a function/hook and unit-test
  that function directly.
- All environment variable access goes through `src/config/env.ts` — never
  read `process.env` elsewhere.

## Python / FastAPI (`apps/api`)

- Target Python 3.12, use modern typing (`str | None`, not `Optional[str]`).
- Ruff is the single source of truth for linting *and* formatting
  (`ruff format`, replacing Black). `mypy --strict` runs in CI separately.
- Route handlers stay thin: parse/validate input, call a service function,
  wrap the result with `success_response`/`error_response`. Business logic
  belongs in `app/services/*` (introduced alongside the first
  business-feature module), not in `app/api/**`.
- All configuration goes through `app.core.config.get_settings()` — never
  call `os.getenv` elsewhere.
- Use dependency injection (`Depends(...)`) for anything request-scoped
  (DB session, Redis client) rather than importing a global.
- Every native-enum SQLAlchemy column (`Enum(SomeEnumClass, ...,
  native_enum=True)`) **must** set
  `values_callable=app.db.enum_utils.str_enum_values` — without it,
  SQLAlchemy binds/generates DDL using each Python enum member's `.name`
  (e.g. `"VIEWER"`), not its `.value` (`"viewer"`), silently diverging
  from every hand-written Alembic migration's lowercase labels. This
  broke user registration against any real (non-test) database for two
  full modules before being caught — see
  [ADR-0025](../adr/0025-enum-values-callable-bugfix.md) for the full
  incident. New migrations should keep using explicit lowercase string
  literals in `sa.Enum(...)`, matching the ORM side.

## Dart / Flutter (`apps/mobile`)

- `flutter_lints` is the baseline; `analysis_options.yaml` adds a small set
  of stricter rules (see the file for the current list).
- Feature-first folder structure under `lib/features/<feature>/` once
  real features land; `lib/core/` is reserved for cross-cutting concerns
  (networking, theming, config) as established in Module 1.
- All environment variable access goes through `EnvConfig` — never call
  `dotenv.env[...]` elsewhere.

## Testing expectations

- New logic ships with tests in the same PR. Coverage is a signal, not a
  target to game — a well-chosen edge-case test beats padding coverage
  percentage with trivial assertions.
- Tests should be deterministic and independent of execution order and of
  each other's side effects.

## Git hygiene

- Conventional Commits for commit messages and PR titles (enforced by
  `.github/workflows/pr-title-lint.yml`): `feat:`, `fix:`, `docs:`,
  `refactor:`, `test:`, `chore:`, `ci:`, `build:`, `perf:`, `revert:`.
- Rebase (don't merge) `main` into feature branches to keep history linear.
