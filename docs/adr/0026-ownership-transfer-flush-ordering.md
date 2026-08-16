# 0026 — Explicit Flush Ordering in Ownership Transfer

## Status
Accepted — bugfix, found via an intermittent test failure.

## Context
`company_service.update_member`'s ownership-transfer path (ADR-0024)
demotes the current Owner to Admin and promotes the target member to
Owner in Python, in that order, within one transaction. This
intermittently violated `uq_company_members_one_owner` (migration
0003's partial unique index) with
`duplicate key value violates unique constraint` — reproducible only
when running the full test suite (not the failing test in isolation),
which pointed at flush/statement ordering rather than the business
logic itself.

Root cause: SQLAlchemy's unit-of-work batches UPDATE statements against
the same table into a single `executemany` call when multiple dirty
instances share the same set of changed columns — here, both the
demoted and promoted `CompanyMember` rows only change `role` (and
`updated_at`). `executemany`'s parameter-set order is not guaranteed to
match the order attributes were assigned in Python. Observed directly in
the failing SQL log: the promote-to-owner UPDATE executed *before* the
demote-to-admin UPDATE within the batch, transiently leaving two Owner
rows for that company and tripping the constraint mid-transaction.

## Decision
An explicit `await db.flush()` immediately after demoting the current
Owner, before promoting the target member — forcing that UPDATE to
physically execute (and pass its own constraint check) as a separate
statement, ahead of the promotion, regardless of how SQLAlchemy would
otherwise have batched them.

## Alternatives considered
- **Make the partial unique index `DEFERRABLE INITIALLY DEFERRED`**: the
  more conventional Postgres pattern for exactly this "swap" scenario
  (defers the uniqueness check to commit time, tolerating a transient
  two-owner state within the transaction). Not chosen here only to avoid
  touching the migration/index definition again after the debugging
  already spent getting it correct (see ADR-0025's related finding) —
  worth reconsidering if a similar ordering issue appears elsewhere,
  since a deferrable constraint fixes the general class of problem
  rather than one call site.

## Consequences
- Verified by running the full test suite three consecutive times from
  a freshly created database — 91/91 passing each time, where it had
  failed roughly 1 in 4 runs before this fix.
- Any future code that updates two rows of the same table toward
  opposite sides of a partial-unique-index boundary in one transaction
  should use the same explicit-flush pattern, or adopt the deferrable-
  constraint alternative above — flagged here so the next occurrence is
  recognized faster.
