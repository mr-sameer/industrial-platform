# 0045 — Module 8C: Capability Graph Sync and ARRAY(String) Evidence Promotion

## Status
Accepted.

## Context
Module 8B (ADR-0044's addendum, commit `e195363`) closed one Company-write
gap (`apply_reviewed_field_to_company`, three scalar fields) but left two
explicitly flagged in its own code:

1. `evidence_service.py`'s own module docstring states `Company.capabilities`
   (Module 3B's plain `ARRAY(String)` column) is "a distinct, currently-
   unsynced concept" from the `Capability`/`GraphRelationship` graph
   (Module 5F) that `attach_capability_evidence` actually writes to.
2. `apply_reviewed_field_to_company`'s own docstring lists all 8
   `ARRAY(String)` Company columns (`secondary_industries`,
   `product_categories`, `manufacturing_categories`,
   `manufacturing_expertise`, `capabilities`, `core_values`,
   `export_categories`, `ai_tags`) as unreachable — "no safe single-value
   write semantics for those yet."

This module closes both gaps, additively, in the same two files Module 8B
introduced. No other module is touched.

## Decisions

### 1. Capability graph → `Company.capabilities` sync
A new, explicit, human-triggered function —
`graph_service.sync_company_capabilities_from_graph(db, company, *,
triggered_by)` — bridges `GraphRelationship`(`HAS_CAPABILITY`,
`status=VERIFIED`) to `Company.capabilities`. Deliberately **not**
automatic and **not** a side effect of `verify_relationship` (unchanged,
Module 5F) — a reviewer calls this separately, mirroring
`apply_reviewed_field_to_company`'s own "never automatic" rule.

- **Source is VERIFIED only.** The query filters
  `GraphRelationship.status == ProvenanceStatus.VERIFIED` directly —
  `OBSERVED`/`EXTRACTED`/`CLAIMED`/`UNDER_REVIEW`/`REJECTED`/`EXPIRED`
  relationships are never read.
- **Append-only, never a destructive replace.** Existing
  `Company.capabilities` entries — including any manually entered value
  with no backing graph relationship at all (e.g. typed directly via
  `PATCH .../business-info`) — are preserved untouched. Only capability
  names not already present (exact, case-sensitive match) are appended.
  Chosen over full-replace-with-derived-set because `graph_service.
  reject_relationship` already refuses to touch an already-`VERIFIED`
  row (no "unverify" path exists anywhere in this codebase) — the
  verified-capability set for a company only ever grows, so append-only
  produces an identical result to full-replace while never risking a
  manually-entered, graph-unbacked value.
- **Idempotent by construction**, following from the point above: a
  second call with no new `VERIFIED` relationship since the last sync
  finds nothing to add, and returns without a commit or an audit event —
  mirroring `graph_service.create_capability`/`create_relationship`'s
  own idempotent-return pattern.
- **Never writes `Company.status` or `Company.verification_status`.**
  Confirmed by construction: neither is referenced anywhere in the new
  function. `verification_status` is written in exactly one place in the
  whole codebase — `verification_score_service.sync_legacy_
  verification_status`, called only from the existing, unmodified `GET
  .../verification` route — not from this module.
- **Endpoint:** `POST /api/v1/graph/companies/{company_id}/sync-capabilities`,
  `Role.ADMIN`-gated (`RequireAdmin`), matching every other mutation in
  `graph.py`. No request body. Response: `{company_id, capabilities,
  added}` — `added` is empty on a no-op sync.

### 2. `ARRAY(String)` evidence promotion via `apply_reviewed_field_to_company`
Extends the existing function (Module 8B) with a new branch for the 8
array fields, dispatched on `record.field_name in _ARRAY_FIELD_LIMITS`
before the existing three-scalar-field dispatch. The scalar branch
(`description`/`industry`/`short_description`) is untouched — same
checks, same exceptions, same behavior, confirmed by a dedicated
regression test exercising both branches on one company.

The array branch is a **structurally distinct operation from the scalar
one**, not a generalization of it — arrays have no single "current
value" to conflict with, so there is no overwrite/conflict concept at
all:

- Shares the function's existing preamble unchanged: `RecordNotVerifiedError`
  (status must be `VERIFIED`), `RecordCompanyMismatchError`
  (`record.company_id == company.id`), `EmptyValueError`
  (`value_observed.strip()` non-empty).
- `overwrite=True` is **rejected outright** for any array field — new
  `ArrayFieldOverwriteNotSupportedError` → `422
  OVERWRITE_NOT_SUPPORTED_FOR_ARRAY_FIELD`. Silently ignoring the flag
  was considered and rejected: a caller passing `overwrite=True`
  expecting destructive-replace semantics should get a clear error, not
  a silently-different append.
- **Idempotency is exact, case-sensitive string match** against the
  existing list — reusing `graph_service.create_capability`'s own
  exact-name convention rather than inventing fuzzy matching. A
  duplicate value is a true no-op (no commit, no audit event).
- **List-count cap, not a character-length cap** — the `ARRAY(String)`
  column itself has no per-element length bound at the DB/model level;
  the only existing length control anywhere in this codebase is the
  list-count cap already enforced on `BusinessInfoUpdate`'s Pydantic
  schema (Module 3B) for 7 of the 8 fields. New `_ARRAY_FIELD_LIMITS`
  dict reuses those exactly:

  | Field | Cap | Source |
  |---|---|---|
  | `core_values` | 20 | `BusinessInfoUpdate` (Module 3B) |
  | `capabilities` | 30 | `BusinessInfoUpdate` (Module 3B) |
  | `manufacturing_expertise` | 30 | `BusinessInfoUpdate` (Module 3B) |
  | `secondary_industries` | 20 | `BusinessInfoUpdate` (Module 3B) |
  | `product_categories` | 30 | `BusinessInfoUpdate` (Module 3B) |
  | `manufacturing_categories` | 30 | `BusinessInfoUpdate` (Module 3B) |
  | `export_categories` | 30 | `BusinessInfoUpdate` (Module 3B) |
  | `ai_tags` | 30 | **New — no prior schema exposure existed** (confirmed absent from both `BusinessInfoUpdate` and `BusinessInfoDetail`); set here to match the majority convention, a deliberate choice rather than a discovered constraint |

  Exceeding the cap raises the new `ArrayLimitExceededError` → `422
  ARRAY_LIMIT_EXCEEDED`.
- **Append, never replace**, on success: `setattr(company, field_name,
  existing + [value])`.
- **Known, accepted consequence, not a violation:** `manufacturing_categories`
  and `export_categories` are live inputs to
  `verification_rules.VERIFICATION_REQUIREMENTS`
  (`manufacturing_categories_set`, `export_categories_set`). Appending to
  either legitimately changes the *next* live-computed verification
  score/level — exactly as uploading a document does today, per this
  codebase's own stated invariant ("verification is always computed
  live, never a manually editable field"). Neither this function nor its
  new array branch writes `verification_status` directly; the shift only
  appears the next time the score is (re)computed via the existing,
  unmodified `GET .../verification` route.

### Audit and provenance trail
- Array promotion reuses the **existing** `"provenance_applied_to_company"`
  audit event (no new event name, keeping one coherent audit stream for
  "apply reviewed evidence to Company"), with new metadata keys
  `value_kind="array_append"` and `resulting_length`.
- `record.review_note` gets the same style of audit line already used
  for scalars, adapted for append: `"Appended '<value>' to
  Company.<field> by <reviewer> at <timestamp> (list length N -> N+1)."`
- Capability sync uses a new, distinct event, `"company_capabilities_synced"`,
  since it is a different action (graph-derived sync) on a different
  trigger (a dedicated endpoint, not the provenance-apply route) —
  metadata: `company_id`, `added`, `resulting_capabilities`.

## Consequences
- No Alembic migration — every column involved (`Company.capabilities`
  and the other 7 `ARRAY(String)` columns, `GraphRelationship`,
  `Capability`) already exists, unmodified since Module 3B/5F.
- `apps/api/app/services/graph_service.py`,
  `apps/api/app/services/data_quality_service.py`,
  `apps/api/app/api/v1/graph.py`, `apps/api/app/api/v1/provenance.py`, and
  `apps/api/app/schemas/graph.py` are extended, not rewritten — every
  pre-existing function, exception, and route in those files is
  unchanged, confirmed by the full six-file regression suite (`tests/
  test_evidence_pilot.py`, `tests/test_graph.py`, `tests/
  test_data_quality.py`, `tests/test_pilot.py`, `tests/test_mca_pilot.py`,
  `tests/test_acquisition.py`) passing unmodified alongside the new tests.
- Modules 5A–5F, 6D, 7A–7C, and 8A/8B's own code paths remain unmodified.
- The two write paths onto `Company.capabilities` (this module's
  graph-sync, and Module 8C's own array-append via a `field_name=
  "capabilities"` `ProvenanceRecord`) are intentionally independent and
  not reconciled with each other — consistent with this codebase's
  established pattern of leaving genuinely distinct evidence channels
  distinct (see Module 8B's own capabilities/graph docstring) rather than
  auto-merging them.
