# 0007 — Health-Check Endpoint Design

## Status
Accepted

## Context
We need a single, reliable way for orchestrators (Docker `HEALTHCHECK`,
future k8s probes), uptime monitors, and developers to answer "is this
service actually working?" — including its dependencies — from day one,
before any business feature exists to exercise the stack end-to-end.

## Decision
Two endpoints per backend service:

- `GET /health/live` — pure liveness, no dependency checks, always
  returns `{"status": "ok"}` if the process is running and can handle
  HTTP. Used for container `HEALTHCHECK`/orchestrator liveness probes.
- `GET /health` (aliased at both `/health` and `/api/v1/health`) —
  readiness/diagnostic endpoint. Actively probes Postgres (`SELECT 1`)
  and Redis (`PING`), returns `ok` / `degraded` / `down` per dependency
  and an aggregate `status`, wrapped in the standard success envelope
  (ADR-0008). Always returns HTTP 200 in Module 1 — a down dependency is
  surfaced in the JSON body, not via HTTP status, since no business route
  yet actually requires Postgres/Redis to function. **Revisit this** once
  a real feature makes a dependency being down an actual outage: at that
  point `/health` should return 503 when a *required* dependency is down.
- The web app mirrors the same pattern locally (`/api/health` in
  `apps/web`) for its own liveness, independent of the API's health.

## Alternatives considered
- **Single combined endpoint only**: rejected — conflates "is the process
  alive" (cheap, should never fail due to a slow dependency) with "are
  dependencies healthy" (can be slow/flaky), which orchestrators need to
  distinguish to avoid killing a healthy-but-dependency-degraded pod.

## Consequences
- `apps/web/src/app/health/page.tsx` gives humans a visual dashboard;
  machines should call the JSON endpoints directly, not scrape that page.
- Adding a new dependency (e.g. an object store, a vector DB) means adding
  a `check_<dependency>()` probe in `app/db/` and wiring it into
  `app/api/v1/health.py`, following the existing `check_database`/
  `check_redis` pattern.
