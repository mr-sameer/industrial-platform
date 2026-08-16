# 0042 — Module 5F: Industrial Knowledge Graph (Implementation)

## Status
Accepted.

## Context
Implements the approved
docs/product/phase-5f-industrial-knowledge-graph-architecture.md
using PostgreSQL only, exactly as that document recommended - no
Neo4j, no dedicated graph database, no graph extension. Modules 5A
(80f4335c), 5B (bb0d3771), 5C (82dca0f/8db7fc4), 5D (aaa4e5f), and 5E
(49ded9a) are all frozen and unmodified.

## The high-risk decision, made deliberately

Before writing any code, every current usage of ProvenanceRecord was
inspected directly: 17 files across every Module 5A-5E component
depend on it. Given that breadth, altering its schema to also carry
relationship (subject, relationship_type, object) triples was judged
the higher-risk path. Instead: provenance_records was not modified at
all. A new, structurally separate table (graph_relationships) carries
relationship-level evidence, reusing the exact same provenance_status
Postgres enum type by reference (create_type=False in the migration)
rather than redefining it - the same conceptual system extended
structurally, not a second competing one. Verified directly, not
assumed: after the full migration round-trip, provenance_records'
column set is byte-identical before and after (19 columns, confirmed
via direct schema introspection, and via a dedicated structural test
in tests/test_graph.py).

## Decisions

1. Factory, confirmed to not exist anywhere before this module
   (verified by a direct search returning zero matches) - implemented
   minimally: company_id (required), name, and its own independent
   country/state/city, deliberately the same shape as Company's own
   fields but never synced with them, since a factory's physical
   location being distinct from the registered office is exactly the
   fact this model exists to represent.
2. Capability - a small, real table (not a static Python mapping,
   unlike Module 5E's field-risk classification) since capabilities
   are genuinely a controlled vocabulary multiple companies reference.
   Creation is idempotent on name.
3. GraphRelationship covers only owns/operates/has_capability - the
   relationship types nothing else in the existing schema already
   represents. Offering (Module 4B, unmodified) is reused directly,
   unduplicated, for manufactures/supplies/distributes/exports/
   provides_service_for - confirmed by a dedicated test that
   commercial facts (moq, lead_time) live only on the Offering edge,
   never migrated onto Product.
4. Real referential integrity, not a bare polymorphic UUID.
   company_subject_id/factory_object_id/capability_object_id are
   separate, typed FK columns with two CHECK constraints (subject is
   always company; exactly one object column is set, matching its
   object_type).
5. No Location entity built. Confirmed during architecture and
   reconfirmed here: Company.city/state/country and the new
   Factory.city/state/country already answer every query this MVP
   actually needs - adding a separate Location table would add schema
   without adding real capability.
6. Conflict detection is manual, not automatic - a deliberate,
   documented scope decision, not a shortfall. Module 5A's field-level
   conflict detection has a simple trigger (two values are unequal);
   an edge's "disagreement" has no equally simple automatic
   definition, since a company can genuinely own multiple factories or
   have multiple capabilities without that being a conflict at all.
   Rather than build a fragile, likely-wrong heuristic,
   flag_relationship_conflict lets a human reviewer explicitly link
   two specific relationship rows as conflicting, creating a real
   DataConflict (Module 5A, reused unchanged) - verified end-to-end,
   including that the resulting conflict is visible through the
   existing, unmodified GET /provenance/conflicts route.
7. verify_relationship/reject_relationship mirror
   provenance_service.verify_provenance_record exactly - VERIFIED is
   reachable only through the dedicated verify action, never as a side
   effect of creation, confirmed directly: creating a relationship
   with status="verified" is rejected (422); an extracted-status
   relationship with confidence=0.95 was verified by test to remain
   extracted, not silently promoted, regardless of confidence.
8. Duplicate relationship prevention is idempotent, not error-based -
   a second, identical (subject, type, object) claim returns the
   existing row rather than creating a duplicate or raising an error.
9. RBAC: Role.ADMIN for every route, including reads - an internal,
   backend-first surface, matching every prior Module 5 phase's
   identical pattern for this class of subsystem.
10. No frontend changes - confirmed: route list and bundle sizes are
    unchanged from before this module.

## Verification
- Migration 0010 run for real: upgrade -> downgrade -> re-upgrade, all
  confirmed clean. provenance_records' 19 columns confirmed
  byte-identical before and after - the single most important
  verification given the HIGH-RISK framing.
- Real, live smoke test end-to-end before any automated test existed:
  company -> factory -> owns relationship -> capability ->
  has_capability relationship -> capability query correctly finding
  the company unfiltered but returning empty with verified_only=true
  (proving "no automatic verification" live) -> explicit verify ->
  re-verify correctly rejected (409) -> duplicate relationship
  creation correctly idempotent (same row ID returned) -> manual
  conflict flagging correctly linking both relationships to one real
  DataConflict.
- 25 new tests (tests/test_graph.py), all passing, including five
  explicit regression tests (field-level provenance, data quality,
  Company APIs, Offering APIs, entity resolution) plus one structural
  test asserting ProvenanceRecord's exact column set.
- Full backend suite run in three batches (necessary due to sandbox
  tool-execution time limits at this suite's current size - not a
  test-runner limitation): 283 tests collected across all three
  batches, zero failures, one pre-existing skip, exit code 0 on every
  batch - 282 passed + 1 skipped, matching 257 pre-existing + 25 new.
- ruff/mypy --strict clean across all 112 backend source files.
- Frontend tsc, ESLint, Vitest (12/12, untouched), and a production
  build all clean - route list and bundle sizes unchanged.
- docs/architecture/openapi.json regenerated: 66 -> 80 paths.

## Known limitations
- Conflict detection for relationships is manual only (decision 6) -
  stated directly as a real, deliberate scope boundary, not parity
  with Module 5A's automatic field-level detection.
- Query layer is admin-only, internal - no public retrieval surface,
  no /discover integration (explicitly deferred, per the approved
  architecture's own roadmap).
- No Requirement Intelligence integration built - the ticket's 5F.11
  explicitly asked only for documenting the future hook, not
  implementing it; graph_service's query functions are the internal
  functions a future integration would call, but no /consult wiring
  exists.
- Machine Asset and Certification/Standard remain deferred, exactly as
  the approved architecture scoped them - not built, not stubbed.
- Location remains implicit (Company/Factory's own fields) rather than
  a first-class graph entity - a deliberate simplification, not an
  oversight.

## Consequences
No architectural deviation beyond the one high-risk decision itself
(decision 6: manual rather than automatic conflict detection),
explicitly flagged as a scope decision in the implementation and
restated here. Modules 5A, 5B, 5C, 5D, and 5E remain frozen and
unmodified - confirmed directly via a structural test, not assumed.
