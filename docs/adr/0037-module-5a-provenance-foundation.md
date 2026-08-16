# 0037 — Module 5A: Provenance & Source Registry Foundation

## Status
Accepted.

## Context
Implements exactly the scope
`docs/product/phase-5-industrial-data-acquisition-architecture.md`
(frozen as approved) defines for Module 5A: the provenance and source
registry foundation — not collection, not extraction, not entity
resolution automation. No crawler, scraper, or external integration
exists anywhere in this codebase after this module; nothing here
ingests a single row of real external data. This module builds the
structure that a future collection system would write into.

## Decisions

1. **Four tables, not more.** `source_registry` (architecture doc
   Section 3), `raw_observations` (Section 5), `provenance_records`
   (Section 4/11), `data_conflicts` (Section 14, detection/flagging
   only). Each maps to a specific section of the approved architecture
   — nothing was added speculatively beyond what that document scoped
   for this phase.
2. **`raw_observations` carries no entity link at all.** Per Section
   6's pipeline ordering (raw collection precedes entity resolution),
   a raw observation must be creatable before any Company/Product
   match exists. `provenance_records` is what bridges a raw
   observation to a resolved entity — never `raw_observations`
   directly.
3. **Real referential integrity for the entity link, not a bare
   polymorphic UUID.** `provenance_records` and `data_conflicts` both
   use nullable `company_id`/`product_id` FK columns with a `CHECK`
   constraint (exactly one set) rather than a single untyped
   `entity_id` column with no FK at all — a genuine, deliberate
   improvement over the loosest possible design, at the cost of two
   nullable columns instead of one.
4. **The core enforcement point: `status=VERIFIED` is reachable only
   through `provenance_service.verify_provenance_record`.** Nothing
   else in the model, schema, or service layer can produce it —
   enforced at three independent layers: the Pydantic schema
   (`ProvenanceRecordCreate.model_post_init` rejects `verified` at
   input), the service function (`create_provenance_record` re-checks
   and raises `ValueError` even if the schema layer were ever
   bypassed), and the database default (`server_default='observed'`).
   Verified directly, not assumed: a real test asserts creating a
   record with `status=verified` returns `422`, and a second test
   confirms the only path to `verified` — the dedicated `/verify`
   route — requires a real, attributable `verified_by` (the
   authenticated caller's own user ID, never a system/anonymous
   value).
5. **Conflict detection never touches an already-verified record's
   status.** A disagreeing new observation against verified data still
   gets flagged (`conflict_id` set on both records) — confirmed via a
   dedicated test (`test_conflict_against_an_already_verified_record_is_still_flagged`)
   that the verified record's `status` stays `verified` and its
   `conflict_id` is set, matching the architecture doc's "never
   silently overwrite conflicting information" — a conflict against
   verified data is surfaced, not hidden by the higher status.
6. **`resolve_conflict` never mutates a `ProvenanceRecord`'s
   `value_observed` or `status`.** Resolving a conflict is
   record-keeping (a human decision, with a mandatory note) — deciding
   which value becomes canonical, or writing to `Company`/`Product` at
   all, is explicitly out of this module's scope, confirmed by a test
   asserting the provenance records are unchanged after resolution.
7. **Reads are public, mutations require authentication only** — no
   finer-grained RBAC for this new subsystem yet, matching the same
   honest, explicitly-flagged pattern Phase 4B used for `Product`
   creation (any authenticated user, no moderation queue yet).

## Verification
- Migration `0006` run for real: fresh upgrade, downgrade, re-upgrade,
  all clean — confirmed zero changes to any existing table (`company_id`/
  `product_id` on the two new tables are new *outbound* FKs, not
  columns added to `companies`/`products`).
- Real end-to-end API smoke test (not just unit tests): created a
  source, a raw observation, a provenance record, verified it via the
  dedicated action, created a second disagreeing observation, confirmed
  a real conflict was flagged against the already-verified record.
- 22 new tests, all passing, including the two most load-bearing ones
  (creation with `status=verified` rejected; re-verification rejected)
  and a dedicated cross-cutting test confirming the system works
  identically for `entity_type=product` as for `entity_type=company` —
  the architecture doc's explicit requirement that provenance be
  "capable of eventually attaching source lineage to both Company and
  Product information."
- Full existing suite unaffected: 150/150 pre-existing backend tests
  still pass unmodified, combined suite 172/172. `ruff`/`mypy --strict`
  clean across all 78 backend source files. Frontend `tsc`, ESLint,
  Vitest (12/12), and a production build all clean and unchanged in
  route list/bundle size — this module is backend-only, and the
  frontend build confirms that precisely (zero size delta).

## Consequences
- No architectural deviation from the approved Module 5A scope.
- Explicitly not built, matching the ticket's own exclusions: web
  crawlers, external data ingestion, AI extraction, entity-resolution
  automation, Knowledge Graph — none of the four new tables are
  populated by anything other than direct, authenticated API calls,
  identical in spirit to how Company/Product/Offering have worked
  since Modules 3A/4B.
- `docs/product/phase-5-industrial-data-acquisition-architecture.md`
  itself was not modified — it remains frozen as approved; this ADR is
  the implementation record, not a revision to that document.
