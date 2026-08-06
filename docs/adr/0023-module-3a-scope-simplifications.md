# 0023 — Module 3A Scope Simplifications

## Status
Accepted

## Context
The full domain model (`docs/domain/`) designs `Industry`/`Category` as
controlled-taxonomy entities and `Verification` as a full aggregate with
its own request/review/approve/revoke lifecycle (`docs/domain/03`,
`docs/domain/05`). Module 3A's brief asks only for Company Core —
company creation/membership/search — not the taxonomy or verification
modules themselves. Building either in full now would mean guessing at
requirements neither Module 3A's brief nor a dependent feature has
specified yet.

## Decision
Two deliberate simplifications, both reversible without a breaking
schema change later:

1. **`Company.industry` is a plain string**, not a foreign key into a
   controlled `Industry`/`Category` taxonomy. Free-text today; migrating
   to a FK later is an additive migration (add the taxonomy tables, add
   a nullable FK column, backfill, then tighten) — not a redesign of
   `Company` itself.
2. **`Company.verification_status` is a placeholder enum** (`unverified`
   / `verified`), always `unverified` in Module 3A — there is no
   `Verification` aggregate, no request/approve/revoke flow, no
   `Certificate` entity yet. The column exists purely so the Company
   Dashboard and public profile (both explicitly required by this
   module's brief) have something to display in the "Verification
   Status" / "Verification Badge Placeholder" fields the brief asks for.

## Alternatives considered
- **Build the full Industry/Category taxonomy now**: rejected — nothing
  in Module 3A's brief needs it to be queryable/controlled (search-by-
  industry works fine as a string `ILIKE` filter at this scale), and
  guessing the taxonomy's shape without a concrete Products/Search
  module driving real requirements risks building the wrong thing.
- **Build the full Verification aggregate now**: rejected — explicitly
  out of Module 3A's stated scope, and would require product decisions
  (tier definitions, evidence requirements) that
  `docs/domain/18-architecture-review.md` already flagged as
  undecided.

## Consequences
- Any future Verification module's migration will add a real
  `verifications` table and (likely) replace `Company.verification_status`
  with a computed/derived value rather than a directly-set column — this
  is anticipated, not accidental technical debt.
- Search filtering by industry (`GET /companies/search?industry=...`)
  uses substring matching (`ILIKE '%...%'`) rather than an exact FK
  match — acceptable at Module 3A's scale, revisit if/when a real
  taxonomy lands.
