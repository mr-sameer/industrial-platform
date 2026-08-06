# 0013 — RBAC Model: Flat Platform-Wide Roles

## Status
Accepted

## Context
Some routes will eventually need to restrict access by role (e.g. only
`admin` can manage users). We need a role model now so `require_role(...)`
exists as a pattern before real protected business routes are written,
without over-building permissions the platform doesn't have a concrete
need for yet.

## Decision
A single, flat `role` column on `User` (`app/models/user.py`), one of
three values: `admin`, `analyst`, `viewer` (default). Enforced via the
`require_role(Role.ADMIN, ...)` FastAPI dependency factory
(`app/core/dependencies.py`), usable as
`Depends(require_role(Role.ADMIN))` on any route.

## Alternatives considered
- **Fine-grained permission strings** (e.g. `reports:write`,
  `suppliers:delete`) with a many-to-many roles↔permissions table:
  more flexible, but there are zero real permission checks to inform the
  right permission taxonomy yet — building it now means guessing.
  Revisit once the first 2–3 business features define concrete
  authorization needs.
- **Per-tenant / per-organization scoped roles**: this platform's
  multi-tenancy model isn't decided yet (see the industrial platform's
  broader product discovery work, outside this repo's scope) — adding
  tenant scoping to roles now would likely need to be redone once that's
  settled.

## Consequences
- Every new protected route picks the coarsest role that makes sense
  today; don't invent new role values without updating this ADR (or
  superseding it) first — the whole point of a flat enum is that it stays
  small.
- No protected business routes exist yet in Module 2 to actually exercise
  `require_role` — it ships proven only by
  `tests/test_security.py`/`tests/test_auth.py` and is ready for the
  first business-feature module to depend on.
