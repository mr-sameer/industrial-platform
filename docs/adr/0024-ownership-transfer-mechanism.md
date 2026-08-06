# 0024 — Ownership Transfer via PATCH Member role=owner

## Status
Accepted

## Context
`docs/domain/08-business-rules.md` requires a company to have exactly
one Owner at all times, with transfer as the only legal way to change
who holds that role. Module 3A's brief lists a fixed REST endpoint
surface (`POST/GET/PATCH/DELETE /companies/{id}`,
`POST/PATCH/DELETE /companies/{id}/members/{member}`, etc.) with no
dedicated `/transfer-ownership` endpoint, while separately describing
Company Settings' frontend as offering "Transfer ownership (placeholder
only)".

## Decision
Ownership transfer is performed via the already-listed
`PATCH /companies/{id}/members/{member}` endpoint, by setting
`role: "owner"` on the target member. `app.services.company_service.update_member`
detects this case specifically: it demotes the current Owner to Admin
(not removed — still a member) and promotes the target to Owner,
atomically, in one transaction. This reuses the endpoint the brief
already specifies rather than inventing a new one outside that list.

Two invariant guards enforce the "exactly one Owner" rule from both
directions:
- The current Owner's role/status **cannot** be changed directly (to a
  non-owner role, or to a non-active status) except via this transfer
  path — attempting to do so raises `CANNOT_DEMOTE_LAST_OWNER` (409).
- A member **cannot** be removed while holding the Owner role —
  `CANNOT_REMOVE_OWNER` (409), from the pre-existing DELETE endpoint.

A database-level partial unique index
(`uq_company_members_one_owner`, migration 0003) backstops both — see
`tests/test_company_members.py::test_database_enforces_single_owner_even_if_application_logic_were_bypassed`,
which deliberately bypasses the service layer to prove the constraint
holds even if application logic were wrong.

## Alternatives considered
- **A dedicated `POST /companies/{id}/transfer-ownership` endpoint**:
  arguably clearer intent, but not in the brief's fixed endpoint list;
  adding an endpoint outside that list wasn't judged worth deviating
  for when the existing member-update endpoint expresses the same
  operation correctly.
- **A separate `ownership_transfers` audit-specific table**: the
  existing `AuditLog` (Module 2.5) already captures this via the
  `company_ownership_transferred` event with `company_id`/`member_id`
  metadata — a dedicated table would duplicate that without adding
  queryable value Module 3A needs.

## Consequences
- The frontend/Flutter "Transfer ownership" UI (explicitly scoped as a
  placeholder in this module's brief) has a real, working API to call
  when it's built out — `PATCH .../members/{member}` with
  `{"role": "owner"}` — rather than needing a follow-up backend change.
- API consumers must know that `role: "owner"` in this one PATCH body
  means something structurally different (a transfer, with a side
  effect on a different row) than every other role value (a plain
  update) — documented here and in the endpoint's own docstring/OpenAPI
  description, not left implicit.
