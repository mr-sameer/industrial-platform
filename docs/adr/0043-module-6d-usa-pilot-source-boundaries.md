# ADR-0043: Module 6D — USA pilot source boundaries and field-mapping generalization

## Status

Accepted.

## Context

Module 6D's brief requires a real, functional acquisition pilot against
three USA sources — SEC EDGAR (company identity/enrichment), Census CBP
(industrial statistics), and USITC DataWeb (trade intelligence) — plus
first-class manual data entry, all reusing Modules 5A–5F/6B unmodified
where possible. Inspecting that existing architecture surfaced two real
constraints not visible from the module specification alone:

1. **`ProvenanceRecord` (Module 5A, frozen) has a `CHECK` constraint
   requiring exactly one of `company_id`/`product_id`.** There is no
   way to attach a Census aggregate statistic or a USITC trade
   observation to it without either fabricating an entity link (which
   the brief explicitly forbids) or a schema change.
2. **`company_promotion_service` and `entity_resolution_service` both
   hardcoded MCA's own field names** (`"cin"`, `"company_name"`,
   `"registered_state"`, `"registered_office_address"`) at three call
   sites. `company_promotion_service`'s own docstring already called
   this "the one genuinely source-specific piece... isolated into
   module-level constants" — i.e. the intended extension point, just
   not yet parameterized by source. Without generalizing it, SEC's
   (or manual entry's) data could never be promoted to a `Company` or
   participate in entity resolution correctly, regardless of the
   `SourceAdapter`/registry abstraction Module 5B already generalized.

## Decision

**On (1) — no schema change.** Census CBP and USITC DataWeb
observations stay entirely at the `RawObservation` +
`SourceRegistry` + `AcquisitionJob`/`AcquisitionJobEvent` layer, which
already fully answers "where did this come from, when, by what
query/request" — the actual substance of "provenance" for aggregate/
trade data. They never receive a `ProvenanceRecord`, since that
model's real purpose (per its own docstring) is a claim about *one
field on one Company/Product entity*, which aggregate/trade data
structurally is not. Enforced at two independent points, not by
convention alone:
- `app.collectors.field_profiles` has no registered profile for
  `collector_type` `census_cbp` or `usitc_dataweb`.
- `app.services.pilot_service.run_pilot` never calls entity resolution
  for a `collector_type` with no registered profile
  (`field_profiles.has_profile`).

**On (2) — a new `app.collectors.field_profiles` module**, generalizing
the single hardcoded MCA field tuple into one `SourceFieldProfile` per
`collector_type` (`mca_data_gov_in`, `sec_edgar`, `manual_entry`,
`mock`), each with its own `extract()` closure (address/city parsing is
genuinely source-shaped — MCA's free-text Indian address heuristic
does not apply to SEC's already-structured US address fields, or to
manual entry's already-labeled fields). `company_promotion_service`
and `entity_resolution_service` now call
`field_profiles.resolve_profile_for_content` instead of reading raw
field names directly.

**Profile resolution is lineage-first, never a silent default.**
`resolve_profile_for_content` resolves a `collector_type` from the raw
observation's real `AcquisitionJob` lineage
(`acquisition_service.get_collector_type_for_observation`) and looks
up that collector's registered profile — authoritative for every
production-created observation. Only when an observation has **no**
job lineage at all does it fall back — and only to the MCA profile,
and only when the content carries MCA's own literal field-name
signature (`_is_legacy_mca_shaped`). This narrow shim exists solely
because `tests/test_pilot.py`'s `_create_mca_shaped_observation`
constructs `RawObservation` rows directly (bypassing
`acquisition_service` entirely) to unit-test entity resolution in
isolation — a real, pre-existing, pre-Module-6D test pattern this
module must not break. Any other lineage-less, non-MCA-shaped content
raises `UnknownSourceProfileError` rather than guessing — Census/USITC
content hitting this function (which should never happen in production,
since `pilot_service` never routes them here) fails closed for exactly
this reason.

**`SEC's CIK is never written to `Company.cin`.** CIK identifies a
company in a different registry than India's CIN, and
`app.entity_resolution.matching`'s own docstring already documents that
extending `AUTO_MATCH` to a new identifier type is "a deliberate,
separately-documented decision" — not implied by adding a new source.
SEC's CIK still participates in entity resolution via
`RawObservation.external_reference` (Tier 2 of `matching.py` — exact
cross-source identifier match, `REVIEW_REQUIRED`, never `AUTO_MATCH`),
which required zero change to `matching.py` itself — that tier was
already generic across any source's `external_identifier`.

**`MockSourceAdapter` gets its own explicit, registered profile**
(`_extract_mock`, always returns an empty identity), rather than being
silently swept into a default. This reproduces its exact pre-Module-6D
behavior (`MockSourceAdapter`'s fixtures use `{"name": ..., "country":
...}`, and the old hardcoded extraction only ever read `"company_name"`
— so mock-sourced candidates have always resolved `NO_MATCH`) without
guessing a new mapping onto its `"name"` field.

**Manual entry is a `SourceAdapter`, not a new endpoint or table.**
`app.collectors.manual_entry_adapter.ManualEntryAdapter` treats the
submitted record itself as the one "collected" item — `POST
/api/v1/acquisition/jobs` (Role.ADMIN-gated, Module 5B, unmodified)
with `collector_type="manual_entry"` is the submission path. This
gives manual entry idempotency, job/event auditing, redaction, entity
resolution, and human review/promotion for zero new persistence, zero
new route, and zero schema change — `entered_by`/`evidence_url`/`notes`
are preserved on the raw observation (visible via `GET
/acquisition/observations/{id}`) but deliberately excluded from the
manual profile's direct/extra field lists, so they never become a
company-fact `ProvenanceRecord`.

## Consequences

- No Alembic migration in this module.
- Three new files (`sec_edgar_adapter.py`, `census_cbp_adapter.py`,
  `usitc_dataweb_adapter.py`) plus `manual_entry_adapter.py` and
  `field_profiles.py`, registered in `app.collectors.registry` — the
  exact extension point Module 5B already provided.
- `company_promotion_service.py` and `entity_resolution_service.py`
  are modified (not rewritten) to call the shared resolver; every
  existing MCA/mock test in `tests/test_pilot.py` and
  `tests/test_mca_pilot.py` continues to pass unmodified.
- A future source that genuinely earns a stronger identifier tier
  (e.g. a verified government-issued ID with the same reliability as
  CIN) still requires its own deliberate, separately-documented
  decision to extend `AUTO_MATCH` — this ADR does not make that call
  for SEC's CIK, and nothing here should be read as having done so.
