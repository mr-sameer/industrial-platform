# 0034 — Self-Hosted API Docs, and Database Startup Self-Healing

## Status
Accepted. (Written retroactively — both fixes below were implemented
and referenced by this ADR number in code comments across several
turns, but this document itself was never created until now, a real
documentation gap closed here rather than left dangling.)

## Part 1 — Self-hosted `/docs` and `/redoc`

`/docs` and `/redoc` depended on `cdn.jsdelivr.net`. In this sandbox's
network egress policy that CDN returns a real `403` — `/docs` returned
`200` (the HTML shell loaded fine) while Swagger UI silently never
rendered, confirmed via real headless-browser testing, not curl.

Fixed by vendoring the actual UI assets into the repo instead of
depending on any CDN at request time:
- Swagger UI: `swagger-ui-dist@5.32.12` (npm), not the `swagger-ui-bundle`
  PyPI package — its latest release only bundles Swagger UI 4.15.5,
  which rejects this app's `openapi: "3.1.0"` documents outright
  ("does not specify a valid version field"), found via real testing.
- ReDoc: `redoc@2.5.3`'s standalone bundle (npm).

Two further real bugs found via the same real-browser pass, both CSP-
related: `script-src 'self'` alone blocked Swagger UI's own inline
initialization script (the page rendered as 0 bytes despite `200`s
everywhere); no `worker-src` directive blocked ReDoc's `blob:` Web
Worker. Both fixed with narrowly-scoped, docs-only, dev-only CSP
additions (`app/core/security_headers.py`). ReDoc's own hardcoded
external logo fetch (`cdn.redoc.ly`) is deliberately left blocked —
purely cosmetic, degrades gracefully, and allowing it would reintroduce
the exact external-CDN fragility this whole fix exists to eliminate.

## Part 2 — Database startup self-healing

A reported `role "platform_user" does not exist` persisted even after
documenting a manual bootstrap step, because a separate manual script
is easy to skip, and because the failure previously only surfaced deep
inside a request handler with no indication of which `DATABASE_URL`
was actually in play.

Fixed in `app/main.py`'s lifespan: a real startup connectivity check
that (1) prints the exact resolved `DATABASE_URL`, password-masked,
and (2) on the exact reported error class — plus `InvalidCatalogNameError`
(role exists, database doesn't; found via a follow-up fresh-state
reproduction after the first fix shipped) — automatically creates
whatever's missing via a local Unix-socket connection and retries, no
manual step required. Falls back to a specific, actionable error only
if auto-creation itself can't succeed.

Two real bugs found while building this: the first version connected
via TCP, which (confirmed directly against this environment's
`pg_hba.conf`) always hits a password-auth rule regardless of OS-level
privilege — peer auth only applies over the Unix socket. Fixed by
omitting `host=` for that specific connection. Made the identical
mistake in the new tests' own admin connections before catching it via
real test failures.

## Verification
Both parts verified via real headless-browser screenshots (Swagger UI
and ReDoc genuinely rendering, not just returning `200`) and a complete
fresh-state proof (dropped role, database, or both; started `uvicorn`
with zero manual steps; confirmed `register`/`login`/`docs`/`openapi.json`
all succeed). Full backend suite passing throughout, `ruff`/`mypy --strict`
clean.
