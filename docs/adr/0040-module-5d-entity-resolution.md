# 0040 — Module 5D: Data Normalization & Entity Resolution

## Status
Accepted.

## Context
Builds the deterministic, explainable identity-matching foundation
needed to safely combine information about the same real-world company
arriving from multiple sources, without ever auto-merging on weak
signals. Reuses Modules 3A/5A/5B/5C completely unchanged — confirmed
directly, not assumed (Phase 1's own inspection requirement).

## Decisions

1. **No blended numeric score — a fixed, documented rule sequence
   over independently-evaluated signals instead**, per the ticket's
   own explicit instruction. Every signal (`cin`,
   `exact_source_identifier`, `verified_domain`,
   `normalized_name_and_address`, `normalized_name`,
   `fuzzy_name_similarity`) is evaluated and reported on its own, with
   a discrete strength label (`strong`/`medium`/`weak`) and a boolean
   matched/not-matched — never collapsed into a single number.
2. **Only an exact CIN match reaches `AUTO_MATCH`.** This is a
   deliberately conservative reading of the ticket's own priority list
   and its Phase 9 safety principle: the ticket's worked example
   describes name+address agreement as "potentially high confidence,"
   not "auto match," and no other identifier in this pilot's actual
   data (Module 5C) is as verifiable as CIN. Documented in
   `app/entity_resolution/matching.py`'s own module docstring as a
   deliberate choice, not an accidental gap — extending `AUTO_MATCH` to
   a future, genuinely government-issued second identifier would be a
   separate, explicit decision.
3. **Even `AUTO_MATCH` requires an explicit human decision before
   touching canonical data**, matching the ticket's own "do not
   automatically modify canonical company data without a valid
   decision." `EntityResolutionCandidate.resolution_state` (the
   system's assessment) and `.decision` (a human's later, independent
   action) are separate columns for exactly this reason — enforced by
   construction: `entity_resolution_service.decide()` is the only
   function in this module able to touch a `Company` or create a
   `ProvenanceRecord`, and it only runs in response to an
   already-recorded decision.
4. **One new table** (`entity_resolution_candidates`), migration
   `0008` — real upgrade/downgrade/re-upgrade round-trip confirmed
   clean. Determined during Phase 1's inspection that the existing
   schema had no way to represent "which Company (if any) does this
   raw observation appear to be" — a genuinely new question none of
   Modules 5A/5B/5C's tables were designed to answer, since all of
   them assume a Company is already resolved.
5. **`CONFIRM_MATCH` reuses Module 5A's existing `DataConflict`
   mechanism by construction, not by reimplementing it.** Attaching a
   confirmed observation's fields to an existing company calls
   `provenance_service.create_provenance_record` unchanged — that
   function's own, already-built conflict detection fires automatically
   if a field disagrees with what's already on record. Verified
   directly via a live diagnostic script before trusting it in a test:
   confirmed a real `DataConflict` row gets created, linking both the
   old and new `ProvenanceRecord`s.
6. **`CREATE_NEW` reuses Module 5C's `promote_raw_observation_to_company`
   completely unchanged** — including its own independent CIN duplicate
   check, a real second safety net even if entity resolution's own
   candidate generation somehow missed something.
7. **Idempotent candidate generation**: a second call for the same
   `raw_observation_id` returns the existing candidate rather than
   creating a duplicate (Phase 8, Case 5) — added deliberately, not
   assumed to fall out of the design for free.
8. **RBAC: `Role.ADMIN` for every route, including reads** — matching
   Module 5B/5C's own established pattern for this subsystem; no public
   entity-resolution endpoint exists, per the ticket's explicit
   instruction.
9. **No frontend changes** — an internal review-queue API only, per
   the ticket's explicit preference for backend-only unless a UI is
   genuinely required.

## A real bug found via direct diagnosis, not assumption, and its
## downstream consequences

A conflict-detection test kept failing with `0` conflicts found, even
though every relevant function looked correct on inspection. Rather
than guessing at a fix, a standalone diagnostic script was written to
call the actual service functions directly against a real database,
bypassing the test's HTTP layer entirely. That script proved the
service layer *did* correctly create a `DataConflict` — which
redirected the investigation to the test's own setup, and surfaced a
genuine, useful finding: **Module 5B's own idempotency (source-scoped,
by design) silently treats a second same-CIN observation pulled
*through the same source* as a duplicate, and never creates a second
raw observation at all.** Several tests (Case 1, Case 3, the
provenance-attachment test, and the original conflict test) had
unknowingly relied on a "second observation" that was actually a
silent re-reference to the first. Fixed by using two distinct
`SourceRegistry` rows per affected test — which is also the more
realistic scenario for how a real conflict would arise (disagreeing
data from two different sources, not two pulls of the identical one).

A second, smaller bug was found the same way while fixing the first:
`entity_resolution_service.decide()` never updated
`candidate_company_id` for a `CREATE_NEW` decision (it's only set at
generation time for `AUTO_MATCH`/`REVIEW_REQUIRED` candidates), so the
`GET .../candidates/{id}/company` convenience route returned `404`
even after a company was genuinely created. Fixed directly.

## Verification
- Migration `0008` run for real: upgrade → downgrade → re-upgrade, all
  clean. Confirmed zero changes to any existing table.
- 19 new tests (`tests/test_entity_resolution.py`), covering all seven
  of the ticket's own worked cases plus decision-flow, conflict,
  RBAC, and idempotency coverage. Full backend suite: **230/230
  passing** (211 pre-existing + 19 new), `ruff`/`mypy --strict` clean
  across all 99 backend source files.
- Frontend `tsc`, ESLint, Vitest (12/12, untouched), and a production
  build all clean — route list and bundle sizes unchanged from before
  this module (backend-only, per the ticket's explicit instruction).
- `docs/architecture/openapi.json` regenerated: 56 → 60 paths.

## Known limitations
- **Candidate generation is O(companies) per call** — every signal
  check that isn't the CIN/exact-identifier lookup iterates all
  Company rows in Python to compare normalized forms, since normalized
  values aren't persisted anywhere (Company stores only raw values, per
  this module's own "never overwrite raw/canonical values" principle).
  Fine at this pilot's real scale (tens of companies); would need a
  persisted-normalized-form index before scaling meaningfully — not
  built here, since scaling data acquisition is explicitly out of this
  phase's scope.
- **`REJECT_MATCH` is terminal for a given candidate** — a reviewer
  who rejects a proposed match and then wants to create a new company
  from the same observation must trigger a fresh review path (the
  existing, unmodified `POST /acquisition/observations/{id}/promote`
  route remains available as that escape hatch); the candidate itself
  isn't re-decidable, matching this codebase's established "decide once,
  auditably" pattern (Module 5A's `AlreadyVerifiedError` precedent).
- **Fuzzy name similarity uses `difflib.SequenceMatcher`**, a simple,
  deterministic, standard-library ratio — not a purpose-built
  fuzzy-matching library — proportionate to how little weight this
  signal actually carries in the rules (never sufficient for anything
  above `REVIEW_REQUIRED`).

## Consequences
No architectural deviation beyond the two documented bug fixes above,
both found via direct diagnosis and corrected, not silently worked
around. Modules 5A, 5B, and 5C remain frozen and unmodified — confirmed
directly.
