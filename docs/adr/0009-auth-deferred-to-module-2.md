# 0009 — Deferring Authentication to Module 2

## Status
Accepted

## Context
Module 1's explicit scope is foundation only: monorepo, app shells,
infra, standards, and a health check. Building authentication now — even
scaffolding — risks locking in decisions (session vs. JWT, provider
choice, RBAC model) before the domain model that authorization rules
depend on exists.

## Decision
Module 1 ships **zero** authentication: no login UI, no protected routes,
no auth middleware, no user/session tables. `.env.example` reserves
placeholder variable names (`JWT_SECRET_KEY`, etc., commented out) purely
to document the shape Module 2 will need, without implementing anything
against them. CORS is configured permissively for `localhost:3000` only,
appropriate for an unauthenticated local-dev foundation — **not**
production-safe once real user data exists behind it.

## Alternatives considered
- **Stub/mock auth now**: rejected — mock auth tends to leak assumptions
  (e.g. always-authenticated middleware) that are awkward to unwind once
  Module 2 defines the real model.

## Consequences
- Every route added before Module 2 lands is implicitly public. Do not
  deploy Module 1 as-is to any environment containing real data.
- The Module 2 kickoff should start by reading this ADR plus
  `docs/standards/api-response-standard.md` (for how auth error codes like
  `UNAUTHORIZED`/`FORBIDDEN` should look) and ADR-0007 (health check),
  since auth will likely need its own liveness-independent check.
