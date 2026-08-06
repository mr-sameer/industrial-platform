# 0022 — CompanyRole as a Distinct Enum from the Platform-Level Role

## Status
Accepted

## Context
The domain model (`docs/domain/03-core-entities.md`, `docs/domain/18-architecture-review.md`
Weakness #1) flagged, as its highest-priority open item, that Module 2's
platform-level `Role` enum (`admin`/`analyst`/`viewer`, on `User.role`)
and the company-scoped role this module needs
(`owner`/`admin`/`editor`/`viewer`, on `CompanyMember.role`) must not be
collapsed into one enum — they answer different questions ("what can
this user do to the platform itself" vs. "what can this user do within
this specific company") and conflating them would eventually force one
system to awkwardly serve both purposes.

## Decision
`app.models.company_member.CompanyRole` is a new, separate enum
(`owner`/`admin`/`editor`/`viewer`), stored as its own Postgres native
enum type (`company_role`), used exclusively by
`CompanyMember.role`. `app.models.user.Role` (platform-level) is
untouched. A user's platform `Role` and their `CompanyRole` within any
given company they belong to are independent and both apply — see
`docs/domain/08-business-rules.md`'s reconciliation note.

Authorization built on each is also kept separate:
`app.core.dependencies.require_role` (platform-level, pre-existing) vs.
`app.core.company_authorization.require_company_role` (new, Module 3A) —
different modules, different dependency functions, matching
`docs/domain/09-permission-matrix.md`'s three-axis explanation (Buyer/
Seller capability, company management scope, platform operations
authority).

## Alternatives considered
- **One `Role` enum with a superset of values** (e.g. adding
  `company_admin`, `company_editor` alongside `admin`/`analyst`/
  `viewer`): rejected — this is exactly the collapse the domain model
  warned against. A single column can't express "this user is a
  platform `analyst` AND a `Company Owner` of Company X AND a `Viewer`
  of Company Y" simultaneously.

## Consequences
- Two enums named similarly enough (`Role` vs. `CompanyRole`) that a
  future contributor could still reach for the wrong one — mitigated by
  this ADR, the domain model's explicit warning, and the fact that
  `CompanyRole` only ever appears scoped to `CompanyMember`, never as a
  bare import alongside `Role` in the same authorization check.
- Establishes the naming pattern (`<Scope>Role`) for any future
  additional scoped-role system this platform introduces (e.g. a
  hypothetical `TeamRole` per `docs/domain/10-future-scalability.md`'s
  "Teams" section).
