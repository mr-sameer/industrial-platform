# 0030 — Fix: Upload Storage Path Must Not Default to a Docker-Only Location

## Status
Accepted — configuration bugfix.

## Context
Bare `uvicorn app.main:app --reload` (no Docker) failed at startup with:

```
OSError: [Errno 30] Read-only file system: '/app'
```

**Root cause:** `Settings.upload_storage_path` (Module 3B,
`app/core/config.py`) defaulted to `"/app/uploads"` — a path that only
exists inside the API's Docker container filesystem. `app.main`'s
startup code calls `os.makedirs(settings.upload_storage_path,
exist_ok=True)` before mounting the uploads static route; outside
Docker, `/app` doesn't exist and isn't creatable, so this raised
immediately.

**Why it wasn't caught by the test suite or prior Docker verification:**
The test suite always sets `UPLOAD_STORAGE_PATH` explicitly via an env
var (`tests/conftest.py`'s documented test-run invocation), and
Module 3B's own Docker verification (no Docker daemon was available
then either — see that module's report) reproduced `Dockerfile.dev`'s
install+run sequence, which also always had `UPLOAD_STORAGE_PATH=/app/uploads`
set explicitly. Neither path ever exercised the **default value itself**
— i.e., what happens when nothing sets the variable at all, which is
exactly bare local `uvicorn` with no `.env` file, or an `.env` file
copied from `.env.example` before this fix (see below).

**A second, compounding issue found during the same audit:**
`apps/api/.env.example` itself hardcoded `UPLOAD_STORAGE_PATH=/app/uploads`.
Since `Settings` loads `.env` via `pydantic-settings`
(`model_config = SettingsConfigDict(env_file=".env", ...)`) for *any*
run — bare `uvicorn` included, not just Docker — anyone following the
project's own documented local-dev setup (copy `.env.example` to
`.env`) would hit this exact crash even after fixing only the Python
default. Compare with `DATABASE_URL` in the same file, which correctly
holds the **local** value (`localhost:5432`) — `docker-compose.yml`'s
`environment:` block then explicitly overrides it to the containerized
value (`postgres:5432`) for the container. `UPLOAD_STORAGE_PATH` had
this backwards.

## Decision
Two changes, both required together:

1. **`app/core/config.py`**: `upload_storage_path` now uses
   `default_factory=_default_local_upload_path`, a small function
   computing a path relative to `config.py`'s own file location
   (`apps/api/uploads/`) — deterministic regardless of the process's
   current working directory, always writable in a real local checkout,
   and never a Docker-only path.
2. **`apps/api/.env.example`**: `UPLOAD_STORAGE_PATH` is now commented
   out (falls back to the local-safe Python default), matching
   `DATABASE_URL`'s established pattern of holding the local value with
   Docker overriding it explicitly.

`docker-compose.yml`'s `environment:` block
(`UPLOAD_STORAGE_PATH: /app/uploads`) is **unchanged** — Compose's
explicit `environment:` values take precedence over both `env_file` and
any Python-level default, so Docker's behavior is untouched by this fix.
Verified directly: setting `UPLOAD_STORAGE_PATH=/app/uploads` (exactly
what Compose does) still resolves to `/app/uploads`, not the new local
default.

`app.main`'s directory-creation ordering (`get_settings()` resolved at
module import, `os.makedirs` called afterward inside `create_app()`)
was already correct — "create the directory only after resolving the
correct path" required no change, only the value being resolved did.

## Verification
- Reproduced the exact reported failure: bare `uvicorn app.main:app
  --reload`, no `.env` file, no `UPLOAD_STORAGE_PATH` env var — before
  this fix, this is the scenario that raises `OSError`. After the fix,
  confirmed a real server starts cleanly, `GET /health` returns 200, and
  the resolved path is `apps/api/uploads` (a real, writable directory
  that was actually created).
- Uploaded a real generated image to a real company's logo endpoint
  against this locally-running server — full success, including
  thumbnail generation, with the files verified present on local disk
  at the correct (non-Docker) path.
- Confirmed the Docker case is unaffected: explicitly setting
  `UPLOAD_STORAGE_PATH=/app/uploads` (what `docker-compose.yml` does)
  still resolves to exactly that value.
- Full test suite: 118 passing (113 pre-existing + 5 new regression
  tests for this bug specifically, including a subprocess-level test
  that imports `app.main` with no environment configuration at all and
  asserts it doesn't raise). `ruff`, `ruff format --check`, and
  `mypy --strict` (scoped to `app/`, matching this project's established
  CI-equivalent check) all clean.
- No Docker daemon is available in this environment (confirmed, not
  assumed) — Docker's behavior is verified via the explicit-env-var
  precedence check above, the same limitation and mitigation already
  used and disclosed in Module 3B's own report.

## Consequences
- `apps/api/uploads/` is now a real local directory created on first
  run outside Docker — added to `.gitignore` (it wasn't needed before
  this fix, since the old default never successfully created anything
  locally).
- Any other future setting that has a Docker-specific default should
  follow `DATABASE_URL`'s pattern from the start: local-safe value in
  `.env.example`, explicit override in `docker-compose.yml` — not the
  reverse. Worth a quick audit if another Docker-path-shaped setting is
  ever added.
