# End-to-end tests

Real browser tests (Playwright) against a real running stack — not
mocked, not Vitest. Distinct from `pnpm test` (unit tests, `__tests__/`).

## Running

Requires the full stack already running:

```bash
# 1. Postgres + Redis running, migrations applied
# 2. FastAPI:
cd apps/api && uvicorn app.main:app --port 8000
# 3. Next.js:
cd apps/web && pnpm dev
# 4. Run the E2E tests:
cd apps/web && pnpm test:e2e
```

Override the target URLs if the stack isn't on the defaults
(`http://localhost:3000` / `http://localhost:8000`):

```bash
E2E_BASE_URL=http://localhost:3000 \
E2E_DATABASE_URL=postgresql://platform_user:change_me_locally@localhost:5432/industrial_platform \
pnpm test:e2e
```

## Why these exist

`registration.spec.ts` covers the complete chain a unit test can't:
Browser -> Next.js -> BFF route -> `server-auth-client.ts` -> FastAPI ->
Pydantic -> service layer -> Postgres -> response -> browser redirect.
Added after a real production bug (see
`docs/adr/0032-register-bff-status-collapsing-bug.md`) was found by
real-browser investigation that no amount of `curl` or unit testing had
caught — this suite exists so that class of bug gets caught by CI going
forward, not just by manual investigation when a user reports it.
