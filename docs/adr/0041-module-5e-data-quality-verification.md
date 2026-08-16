# 0041 — Module 5E: Data Quality & Verification Operations

## Status
Accepted.

## Context
Implements
`docs/product/phase-5e-data-quality-verification-architecture.md`
(approved). One explicitly-sanctioned exception to "do not modify
Module 5A" — extending `ProvenanceRecord.status` and adding three new
columns — per this module's own approval ticket's "Most Important
Architectural Decision" section. Modules 5A (`80f4335c`), 5B
(`bb0d3771`), 5C (`82dca0f`/`8db7fc4`), and 5D (`aaa4e5f`) otherwise
unmodified.

## Decisions

1. **The sanctioned exception, scoped precisely.** `ProvenanceRecord.status`
   gains three values (`under_review`, `rejected`, `expired`); three
   new nullable columns (`expires_at`, `review_note`,
   `verification_document_id`). Nothing else in Module 5A's files
   changed — confirmed by diff. `app/api/v1/provenance.py` and
   `app/services/provenance_service.py` (both Module 5A) have zero
   changes; all new logic lives in new files
   (`app/services/data_quality_service.py`,
   `app/api/v1/data_quality.py`).
2. **`ProductSpecification.risk_tier`** — a new, real column (not a
   static mapping like Company fields use), per the architecture doc's
   own Section 12 proposal — category authors control it directly,
   defaulting to `LOW`.
3. **No new tables.** The review queue is a live query over the
   (extended) `provenance_records` and the existing, unmodified
   `data_conflicts` — confirmed during architecture design that no
   persisted queue table was needed, and confirmed again here: nothing
   in this implementation required one.
4. **Company field risk and freshness are static, documented Python
   mappings** (`app/data_quality/risk_classification.py`,
   `app/data_quality/freshness.py`), not database tables — the known
   field set is small (Module 5C's real field mapping), and a
   reviewable code-level mapping was judged more appropriate than
   "unnecessary schema," per the ticket's own instruction.
5. **The composite quality score is scoped to Company only in this
   phase**, returning an honest `null`/"not defined" for Product
   rather than a fabricated number — a real, deliberate scope
   boundary, not an oversight, since Section 15's weighting definition
   was built specifically against `VerificationScoreService`'s own
   existing "relevant fields" set (Company-only).
6. **`link_evidence` never changes `status`** — verified directly by
   test: linking a `VerificationDocument` to a `cin` claim leaves the
   record at `observed`. Verification remains a distinct, separate,
   deliberate action via Module 5A's own unmodified
   `verify_provenance_record`.
7. **`reject`/`mark_expired` reuse the existing `verified_by`/
   `verified_at` columns** for "who/when made this review decision,"
   rather than adding parallel `rejected_by`/`rejected_at` columns —
   a deliberate reuse, since both columns already mean "the person and
   time of the most recent authoritative decision on this record,"
   which is exactly what a reject or expire decision also is.
8. **A real structural limitation, found and confirmed directly, not
   glossed over: Offering-level provenance quality is not achievable
   in this phase.** `ProvenanceRecord`'s `CHECK` constraint only
   supports `company_id` XOR `product_id` — there is no `offering_id`
   path, and adding one was not sanctioned by this ticket (only the
   status enum and three columns were explicitly approved). Confirmed
   with a dedicated test: `GET /data-quality/offering/{id}` correctly
   `422`s at the route's own path-pattern validation.

## Real issues found during implementation, via actual testing, not assumption

- **A real `AssertionError` at FastAPI import time**: the first router
  draft used `Query()` for `entity_type`, which is actually a path
  parameter. Caught immediately by trying to import the module, fixed
  with `Path()`.
- **Two real `mypy --strict` failures**: two router helper functions
  were missing type annotations. Fixed directly.
- **A live smoke test caught a math/behavior discrepancy before any
  test suite existed** — verified the quality-score weighting formula
  by hand against a real API response (`14.3%` for one `HIGH`-risk
  field at `OBSERVED`, `2.0 × 0.5 ⁄ 7 × 100`), confirming the
  implementation matches the architecture doc's documented formula
  exactly.
- **Two genuinely broken tests, found by running them, not by
  inspection**: (1) `test_linking_evidence_never_changes_status`
  attempted a document upload using a platform `Role.ADMIN` user with
  no company-membership relationship to the target company — correctly
  rejected by existing, unmodified company-document RBAC; fixed by
  using the actual company owner. The same test also used an invalid
  `document_type` value and non-PDF-shaped byte content — fixed by
  reusing the exact, already-proven-working combination
  `test_company_verification.py` itself uses
  (`business_registration` + real PDF magic bytes via
  `_make_test_pdf_bytes()`). (2) The structural
  "never imports verification_score_service" test initially did a
  naive substring search, which false-positived on this file's *own
  docstring* explaining why it doesn't import that module — rewritten
  to parse the file with `ast` and check actual `Import`/`ImportFrom`
  nodes and `Attribute` accesses specifically, not prose mentions.

## Verification
- Migration `0009` run for real: upgrade → downgrade → re-upgrade, all
  confirmed clean, including the Postgres enum-extension handling
  (`ALTER TYPE ... ADD VALUE` inside an autocommit block) and the
  honest, documented limitation that Postgres cannot remove enum
  values on downgrade.
- Real, live API smoke test (not just pytest) confirmed the full
  workflow end-to-end: create company → create high-risk (`cin`)
  provenance at `observed` → quality report correctly shows it →
  `mark_under_review` → `reject` with a note, all against a real
  running server.
- **The ticket's own explicitly-required critical regression test**:
  confirmed directly that `Company.verification_status` still
  auto-syncs from profile completeness exactly as before (reusing the
  same real business-info + document-upload pattern
  `test_company_verification.py`'s own
  `test_legacy_verification_status_syncs_automatically` established),
  and confirmed structurally (via AST inspection, not a string search)
  that `data_quality_service.py` has zero import of or attribute
  access to `verification_score_service`/`.verification_status`
  anywhere.
- 27 new tests (`tests/test_data_quality.py`), all passing. Full
  backend suite: **257/257 passing** (230 pre-existing + 27 new),
  `ruff`/`mypy --strict` clean across all 105 backend source files.
- Frontend `tsc`, ESLint, Vitest (12/12, untouched), and a production
  build all clean — route list and bundle sizes unchanged from before
  this module (backend-only, per the ticket's explicit instruction).
- `docs/architecture/openapi.json` regenerated: 60 → 66 paths.

## Known limitations
- **Offering-level quality tracking is not possible without a further,
  separately-approved Module 5A schema change** (Section 8, above) —
  stated directly, not hidden.
- **Product's composite score is undefined**, by design (Section 5,
  above) — a future phase would need its own "relevant fields"
  definition for Product, not invented here without a real basis.
- **Risk classification for Company fields is a static code mapping**,
  not admin-configurable — appropriate at the current known field-set
  size; would need promotion to real configuration data if the field
  set grows substantially.
- **Freshness thresholds are fixed constants**, not per-tenant or
  per-industry configurable — matches the architecture doc's own
  scoping for this first pass.

## Consequences
No architectural deviation beyond the one explicitly sanctioned and
scoped exception (Module 5A's `ProvenanceRecord` extension). Modules
5A (beyond that sanctioned point), 5B, 5C, and 5D remain frozen and
unmodified — confirmed directly, not assumed.
