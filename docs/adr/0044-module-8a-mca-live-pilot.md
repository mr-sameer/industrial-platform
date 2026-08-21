# 0044 — Module 8A: Live MCA Data Pilot (Transport Fix, Field Correction, Promotion)

## Status
Accepted.

## Context
Module 8A extended the already-built MCA pipeline (Module 5C, ADR-0039;
generalized by Module 6D, ADR-0043) with no new architecture: field
capture additions, a real-connectivity diagnosis and fix, live field-
schema corrections, and — for the first time — an actual live pilot
run against the real data.gov.in API, followed by human review and
promotion of every resulting observation to a canonical Company.

## Decisions

1. **Field capture additions** (commit a65106a): `nic_code`,
   `industrial_classification`, `indian_foreign_classification` added
   to `MCADataGovInAdapter`'s extraction and registered as
   `extra_fields` (provenance-only) in `field_profiles.py` — never a
   `Capability`/`Offering`/supplier claim, matching the explicit
   constraint from the Module 8A design review.
2. **Idempotency fix** (commit a65106a): `acquisition_service._find_existing_observation`
   now matches on `source_id + external_identifier + content_hash`
   (previously identifier alone) — a re-pull with the same CIN but
   changed content (e.g. a company_status change) now creates a new,
   immutable observation instead of being silently skipped.
3. **Transport fix** (commit 0f2011f): `api.data.gov.in` was found,
   via direct diagnosis, to hang indefinitely for default-configured
   Python HTTP clients while `curl` succeeded immediately. Reproduced
   the confirmed-working configuration in `httpx` (no new dependency):
   an `ssl.SSLContext` restricted to HTTP/1.1-only ALPN (certificate
   verification and hostname checking unchanged from
   `create_default_context()`'s own default — never weakened, never
   `verify=False`), a curl-shaped `User-Agent`, `Accept: */*`,
   `Connection: close`, and a 30s timeout (up from 15s).
4. **Live field-schema correction** (commit 0f2011f): a real
   authenticated request confirmed the resource's exact field casing.
   6 fields already matched a prior guess (`CIN`, `CompanyName`,
   `AuthorizedCapital`, `CompanyStatus`, `nic_code`,
   `CompanyIndustrialClassification`); 9 did not and were added as new
   variants, nothing removed or renamed: `CompanyROCcode`,
   `CompanyCategory`, `CompanySubCategory`, `CompanyClass`,
   `PaidupCapital`, `CompanyRegistrationdate_date`,
   `Registered_Office_Address`, `CompanyStateCode`,
   `CompanyIndian/Foreign Company`.
5. **Live pilot executed** — source `MCA Company Master Data
   (data.gov.in)` (`source_id=7360c0ad-f18e-4bc5-8bda-5da7303855a1`),
   resource `4dbe5667-7b6b-41d7-82af-211562424d9a`,
   `collection_policy_status` explicitly set to `allowed` for this
   controlled run. Job `83870cac-4987-47f9-8776-4f615dd6144f`:
   `succeeded`, 5 records created, 0 skipped, 0 failed, 0 retries.
   Entity resolution ran automatically for all 5 (per
   `pilot_service.run_pilot`'s existing behavior): 5/5 resolved
   `NEW` (no existing company matched any CIN/name/address) —
   0 AUTO_MATCH, 0 REVIEW_REQUIRED, 0 NO_MATCH.
6. **All 5 observations reviewed and promoted**, one at a time, each
   independently verified before the next, via the existing,
   unmodified `company_promotion_service.promote_raw_observation_to_company`
   (the same function `POST /acquisition/observations/{id}/promote`
   calls):

   | CIN | Name | Company ID | Provenance records |
   |---|---|---|---|
   | `U52100HR2015OPC056314` | COVEY RETAIL (OPC) PRIVATE LIMITED | `b83b5519-3af1-45b5-9c30-02cda123ac34` | 15 |
   | `ABD-0345` | Titan Winners Fund Management LLP | `b16e6bcf-f126-4449-a163-2deb55b810ac` | 8 |
   | `U51909DL2019PTC351212` | ABSENTIA TRADERS PRIVATE LIMITED | `e67d4d7c-2333-471b-9329-7960dc04fa65` | 15 |
   | `U51909DL2019PTC351862` | ZEBBOI CERAMICS PRIVATE LIMITED | `8a586d9c-01b8-4fe2-b81f-445c0bd26b65` | 15 |
   | `U51909DL2019PTC351870` | NISHAD OVERSEAS PRIVATE LIMITED | `0d3f72d8-a63c-4350-a1ab-87d7104818bb` | 15 |

   `ABD-0345` (an LLP-style identifier, not the 21-character CIN
   format used elsewhere) was accepted unmodified by the existing
   promotion path — confirming the architecture never assumed a fixed
   CIN format.
7. **Provenance status discipline confirmed, not just designed**:
   across all 5 promotions, every `ProvenanceRecord` was created at
   `observed` or `extracted` — **zero** at `verified`, checked
   directly. `Company.verification_status` remained the model default
   (`unverified`) for all 5 — MCA-sourced existence is explicitly not
   ForgeX verification.
8. **`Company.status` confirmed never derived from MCA's raw
   `company_status`** — COVEY RETAIL's real record carries
   `company_status="Strike Off"`, preserved only as a `ProvenanceRecord`
   (`field_name="company_status"`); `Company.status` is the plain
   model default (`active`), exactly as Module 5C originally designed.
9. **Promotion script** (`apps/api/scripts/promote_mca_pilot_observations.py`,
   commit caf7a91): a thin CLI wrapper around the same, unmodified
   promotion function — no new business logic — preserved as the
   record of how this promotion was performed and as a reusable tool
   for future controlled promotions.

## Verification
- Live authenticated request confirmed reachable and returning valid
  JSON before the pilot ran (single-record smoke tests).
- Full 5-record pilot job succeeded on the first attempt after the
  transport fix — 0 retries needed.
- Field-by-field inspection of one real record (COVEY RETAIL)
  confirmed every "not extracted" case was a genuinely empty source
  value, not a mapping defect — checked directly against the real
  `_extract_field` function, not inferred.
- Post-promotion, all 5 pilot CINs matched to exactly 5 distinct
  `Company` rows; no unintended `Company` rows were created; the
  other 4 observations remained unpromoted at each intermediate step.
- Full provenance lineage for one promoted company (COVEY RETAIL)
  inspected via the existing `GET /api/v1/provenance` service path:
  15 records, all traced to the correct source and originating
  `RawObservation`, all `observed`/`extracted`, none `verified`.

## Known limitations (carried forward, not resolved by this module)
- This is a 5-record controlled pilot, not the 25–50 record pilot
  Module 5C's Section 9 recommends for full validation — a larger run
  remains a separate future decision.
- Legal-review items from Module 5C's Section 10 remain a human
  decision; `collection_policy_status` was set to `allowed` for this
  specific controlled run, not as a general clearance determination.
- `attempt_city_from_address`'s address→city heuristic and the
  reviewing-admin-becomes-technical-owner placeholder (both noted in
  ADR-0039) are unchanged by this module.

## Consequences
No new table, model, migration, or change to canonical architecture.
Modules 5A–5F, 6D, and 7A–7C remain unmodified.
