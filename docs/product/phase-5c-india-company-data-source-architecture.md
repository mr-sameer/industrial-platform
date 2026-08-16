# ForgeX — Module 5C: India Company Data Acquisition Pilot — Source Selection & Architecture

**Status:** Architecture only. Nothing in this document is implemented.
No code was written, no collector was created, no external connection
was made, no file other than this one was touched. Module 5A (commit
`80f4335cb6ce693e21198992bfd2ac2e0f6134ce`) and Module 5B (commit
`bb0d377111ae7b42e5c0cae49292db74f0538f0b`) are both frozen and
unmodified. Every "currently exists" claim in Section 1 was checked
directly against the real codebase. Every claim about an external
source's terms, access mechanism, or licensing was checked via live
research at the time of writing (Section 2 cites what was found and
where); nothing about an external source's legal status is asserted
from memory or assumption — where verification wasn't possible within
this research pass, the source is explicitly marked **LEGAL REVIEW
REQUIRED**, per this module's own instruction.

---

## Table of Contents

1. [Inspect Current System](#1-inspect-current-system)
2. [Source Candidates](#2-source-candidates)
3. [Selected Pilot Source](#3-selected-pilot-source)
4. [Field Mapping](#4-field-mapping)
5. [Source → Observation](#5-source--observation)
6. [Identifiers](#6-identifiers)
7. [Duplicates](#7-duplicates)
8. [Data Quality](#8-data-quality)
9. [Pilot Size](#9-pilot-size)
10. [Legal / Compliance Gate](#10-legal--compliance-gate)
11. [Operational Design](#11-operational-design)
12. [Observability](#12-observability)
13. [Security](#13-security)
14. [Future Enrichment](#14-future-enrichment)
15. [Implementation Plan (Not Built Yet)](#15-implementation-plan-not-built-yet)
16. [Success Criteria](#16-success-criteria)
17. [What Must Not Happen](#17-what-must-not-happen)
18. [Final Self-Review](#18-final-self-review)

---

## 1. Inspect Current System

Checked directly against the real, frozen implementation — not
assumed.

### Company domain (Module 3A/3B)
Real fields on `app/models/company.py`'s `Company`: `name`,
`legal_name`, `slug`, `industry` (free text), `website`, `email`,
`phone`, `country`, `state`, `city`, `status`, `verification_status`,
plus Module 3B's `gst_number`, `pan`, `cin`, `msme_number`,
`iec_number`, `legal_entity_type`, `business_type`, `export_capable`,
`business_registration_date`. **`cin` and `gst_number` already exist as
real columns** — directly relevant to Section 4's field mapping below,
since India's MCA registry's own primary identifier is exactly a CIN.

### Company Verification (Module 3B)
Real, live-computed self-reported-completeness scoring
(`VerificationScoreService`) across weighted requirements. Confirmed,
per Phase 3A/4A/5A's own prior ground-truth findings and unchanged
since: this system has no concept of external-source corroboration —
it scores profile completeness, not independently-confirmed truth.
Module 5C's pilot data does not interact with this system at all (see
Section 5).

### Source Registry, Provenance, Raw Observation (Module 5A — frozen)
`SourceRegistry` (`source_class` enum: `company_owned`,
`public_government`, `third_party_structured`, `news_publication`,
`association_directory`, `user_contribution`; `reliability_weight`;
`collection_policy_status`: `allowed`/`restricted`/`blocked`/
`pending_legal_review`). `RawObservation` (source-scoped, append-only,
no entity link). `ProvenanceRecord` (`status`: `observed`/`extracted`/
`verified`/`claimed` — verification is a distinct, explicit,
attributed action, never automatic). `DataConflict` (detection/
flagging only). All confirmed present and unchanged via direct model
inspection.

### AcquisitionJob, SourceAdapter, Collector Registry (Module 5B — frozen)
`AcquisitionJob` (`pending`/`running`/`succeeded`/`failed`/`cancelled`,
with `retry_count`, `result_count`, `skipped_count`, `failed_count`).
`SourceAdapter` abstract base (`validate_config`, `collect`,
`source_metadata`) in `app/collectors/base.py`. `app/collectors/registry.py`
maps a `collector_type` string to an adapter class — **only `"mock"` is
registered today**, confirmed directly; no real collector exists
anywhere in this codebase. Idempotency key: `source_id` +
`external_identifier` (primary) or `source_id` + `content_hash`
(fallback) — confirmed in `acquisition_service.py`. Retry: bounded at
`MAX_RETRIES = 3`, `RetryableCollectorError` vs.
`NonRetryableCollectorError` as the adapter's own explicit
responsibility.

### Admin authorization
`app/api/v1/acquisition.py` gates every route (including reads) behind
`require_role(Role.ADMIN)` — confirmed via direct inspection
(`RequireAdmin = Annotated[object, Depends(require_role(Role.ADMIN))]`,
applied to all four acquisition routes). A future real India collector
would be created and run through this exact same gate — no new
authorization mechanism is implied by this document.

### Summary: what Module 5C can reuse unchanged
Every piece of infrastructure this pilot needs already exists and is
frozen: `SourceRegistry` to register the chosen source,
`AcquisitionJob`/`SourceAdapter` to run a real collector once one is
built (Section 15, not this phase), `RawObservation` to store what's
collected, `ProvenanceRecord` to later (a separate, explicit act) turn
an observation into a traceable claim about a `Company` field. Nothing
in Module 5A or 5B requires modification for this pilot.

---

## 2. Source Candidates

Every claim below reflects live research conducted while writing this
document (see each row's basis), not memorized/assumed facts about
these sources' current terms. **Publicly accessible is not the same
claim as legally redistributable/usable by ForgeX** — that distinction
is preserved explicitly throughout.

### Candidate A: MCA Company Master Data, via data.gov.in (Open Government Data Platform India)

| Dimension | Finding |
|---|---|
| Source name | "Company Master Data" catalog, data.gov.in, sourced from the Ministry of Corporate Affairs (MCA) / Registrar of Companies |
| Owner | Government of India — Ministry of Corporate Affairs (data), National Informatics Centre / OGD Platform India (publication) |
| Access mechanism | Structured **API** (key-based, registration required) **or CSV bulk download**, per registrar-of-companies dataset — confirmed directly: "These datasets can either be accessed through the API or downloaded as a CSV" |
| Data fields (confirmed) | CIN, Company Name, Company Status, Company Class, Company Category, Authorized Capital, Paid-up Capital, Date of Registration, Registered State, Registrar of Companies, Principal Business Activity, Registered Office Address, Sub Category |
| Stable identifier | **CIN (Corporate Identification Number)** — a 21-digit alphanumeric government-issued identifier, confirmed as the dataset's own primary key field |
| Geographic coverage | All India, organized per Registrar of Companies (22 ROCs across major states) |
| Freshness | Not independently confirmed in this research pass — MCA's own portal is described as providing current status; the data.gov.in republished dataset's update cadence was not confirmed and should be checked during implementation |
| Licensing/terms | Governed by India's **National Data Sharing and Accessibility Policy (NDSAP)**, notified 17 March 2012, with an associated Open license confirmed (via a direct license-text excerpt found in research) to permit: *"use, adapt, publish (either in original, or in adapted and/or derivative forms), translate, display, add value, and create derivative works (including products and services), for all lawful commercial and non-commercial purposes."* This is a genuinely favorable finding — but NDSAP is a policy **framework**; individual dataset pages on data.gov.in carry their own license tag, which should be checked for this specific dataset before implementation, not assumed identical to every other OGD dataset. |
| Redistribution restrictions | The license text found explicitly permits derivative works and both commercial/non-commercial use — favorable, but per-dataset confirmation still recommended (see Legal Gate, Section 10) |
| API availability | Yes — confirmed real, structured, key-based API access exists specifically for this dataset (not merely a metadata catalog) |
| Cost | Free — registration for an API key is free (multiple independent sources confirm free registration) |
| Rate limits | **Not independently confirmed** in this research pass for data.gov.in specifically — general OGD-platform behavior suggests key-based throttling exists, but a specific numeric limit was not found and must be confirmed during implementation (Section 10, Section 11) |
| Authentication | API key, obtained via free account registration and retrieved from the account dashboard |
| Technical complexity | Low-moderate — a conventional key-based REST API with documented parameters (`api-key`, `format`) |
| Expected data quality | High for the fields it covers (a primary government registry, not a reseller) — but narrow: no product/capability/verification-relevant fields beyond legal identity and registered address |

### Candidate B: MCA21 portal directly (mca.gov.in)

| Dimension | Finding |
|---|---|
| Access mechanism | Free public web lookup by company name or CIN — **confirmed no API is provided directly by MCA** ("The Ministry of Corporate Affairs (MCA) does not provide API for any of these master data") |
| Assessment | Same underlying data as Candidate A, but no structured bulk/API access — would require per-record web automation (effectively scraping), directly contradicting this phase's explicit prohibition. **Not viable as a pilot source method**, even though it is the authoritative origin of Candidate A's data. |

### Candidate C: UDYAM / MSME Registration dataset, via data.gov.in

| Dimension | Finding |
|---|---|
| Source name | "UDYAM Registration (MSME Registration)" catalog, data.gov.in, Ministry of MSME |
| Access mechanism | API or CSV, same OGD platform mechanism as Candidate A |
| **Critical finding** | The published dataset is **district-wise aggregate counts** ("total MSME registered enterprise data... district wise"), **not individual per-company records** with names/addresses. Confirmed via multiple independent dataset description sources. |
| Assessment | Not usable for populating individual `Company` rows — it answers "how many MSMEs are registered in district X," not "what are their names and addresses." Real, per-company Udyam lookups exist only via **paid third-party verification APIs** (Deepvue, Figment, APIMall were found) that require an already-known PAN/GSTIN/CIN as *input* to return one record — useful for **future enrichment** of an already-identified company (Section 14), not for **discovering** new companies, which is this pilot's actual goal. |

### Candidate D: Licensed commercial datasets (e.g., business-data aggregators)

| Dimension | Finding |
|---|---|
| Access mechanism | Typically paid API or bulk export |
| Assessment | Plausible future source, but licensing terms, cost, and redistribution rights were not independently verified for any specific named vendor in this research pass — every such vendor would need its own dedicated legal/commercial review before selection. **Marked LEGAL REVIEW REQUIRED, and additionally deferred on cost grounds** — a paid source is a worse pilot choice than a free one when a free, legally-clearer alternative (Candidate A) already exists. |

### Candidate E: Industry associations / directories

| Dimension | Finding |
|---|---|
| Assessment | Not independently researched for a specific named association in this pass (no single obvious best-fit association was identified for a general industrial-company pilot, unlike Candidates A–C which are unambiguous, singular, authoritative sources). Directory terms of service commonly restrict bulk collection even of public listings, per this project's own prior architecture finding (Phase 5 Section 3, Class 5's general assessment). **Marked LEGAL REVIEW REQUIRED** if a specific association is considered later — not evaluated further here since a stronger candidate (A) already exists. |

### Candidate F: Company-owned sources (individual company websites)

| Dimension | Finding |
|---|---|
| Assessment | Not a viable *discovery* source for a first pilot — a company website only exists for a company ForgeX already knows about. Directly relevant to **Section 14 (Future Enrichment)**, not source selection for this pilot, since discovery must come first. |

### Candidate G: Company-submitted information

| Dimension | Finding |
|---|---|
| Assessment | Real and already supported today (Module 3A/3B's own registration/profile-editing flow) — but this is **not an acquisition pilot** in the sense this module means (a company submitting its own data isn't "acquired" via a collector, it's directly authored). Not a candidate for *this* pilot's source selection. |

---

## 3. Selected Pilot Source

**Recommendation: Candidate A — MCA Company Master Data, accessed via
data.gov.in's structured API/CSV mechanism.**

Ranked against the brief's own priority order:

1. **Legal usability** — the strongest finding of this research: a
   directly-quoted, confirmed NDSAP-associated open license permitting
   commercial and non-commercial reuse, adaptation, and derivative
   works. Not certain to the point of skipping legal review entirely
   (Section 10 still applies, and the per-dataset license tag should
   be confirmed), but categorically stronger than any other candidate
   researched.
2. **Data quality** — a primary government registry, not a reseller or
   aggregate summary (ruling out Candidate C directly).
3. **Stable identifiers** — CIN, a real, government-issued, unique
   identifier, confirmed as a native field in the dataset itself.
4. **Reliability** — a government ministry's own official registry
   data, republished through India's official open-data platform.
5. **Reproducibility** — a structured, queryable API/CSV mechanism
   (unlike Candidate B's lookup-only web portal, which would require
   scraping — explicitly prohibited).
6. **Cost** — free (ruling out Candidate D as a first pilot, on cost
   grounds alone, independent of its unverified licensing).
7. **API/structured access** — confirmed real and available, not
   inferred.
8. **India coverage** — comprehensive by construction (the national
   company registry).

**Why this is preferable to the alternatives, stated directly:**
Candidate B is the same authoritative data with no structured access
path (a scraping problem this phase must not create). Candidate C
looked promising by name association ("MSME/Udyam data") but the
actual published dataset turned out — on real inspection, not assumed
— to be aggregate counts, not usable for company discovery at all;
this is exactly the kind of finding this document's research-first
approach exists to catch before it becomes an implementation mistake.
Candidates D and E both carry real, unresolved legal uncertainty with
no corresponding advantage over Candidate A to justify carrying that
risk into a first pilot. Candidates F and G are not discovery sources
at all — they matter later (Section 14), not now.

**This is not asserted as a fully legally cleared source.** Section 10
identifies exactly what remains to be confirmed (the specific dataset
page's license tag, current rate limits, update freshness) before any
real collection begins.

---

## 4. Field Mapping

Source fields (Candidate A, as confirmed in Section 2) mapped to the
real, existing `Company` model (Section 1). No value is invented for
any field the source doesn't provide.

| Source Field | ForgeX Field | Mapping type |
|---|---|---|
| Company Name | `name` | Direct |
| CIN | `cin` | Direct — `Company.cin` already exists as a real column |
| Registered Office Address | `country`, `state`, `city` | Transformed — the source's address is a single field; parsing into ForgeX's three separate columns requires address-component extraction (Section 9's normalization concern, not invented here — a real, bounded parsing task for Section 15's implementation phase, not this document) |
| Company Status (active/dormant/etc.) | *(no direct field)* | **Unavailable** — `Company.status` (Module 3A) represents ForgeX's own publication lifecycle (`active`/`inactive`/etc. in ForgeX's own sense), not the source's legal-status concept; conflating the two would misrepresent what `Company.status` means. Proposed: store the source's raw status value in the `RawObservation`/`ProvenanceRecord` layer (Section 5) as an observed fact about the field `"registry_status"`, without mapping it onto `Company.status` at all in this pilot. |
| Date of Registration | `business_registration_date` | Direct — `Company.business_registration_date` already exists (Module 3B) |
| Registrar of Companies | *(no direct field)* | **Unavailable** — no existing Company field represents "which of India's 22 ROCs" a company is registered under. Not invented; captured only as a raw observation, not forced into an ill-fitting canonical field. |
| Principal Business Activity | `industry` | Transformed, loosely — `Company.industry` is free text (Section 1); the source's activity description can populate it directly as a candidate value, subject to the same "candidate, not automatic canonical overwrite" rule as everything else (Section 5) |
| Authorized/Paid-up Capital | *(no field)* | **Unavailable** — no existing Company field represents capital structure. Not invented. Flagged as a plausible future field, not created here (this document does not propose a schema change — Section 15 defers any such decision). |
| Company Class/Category/Sub Category | *(no field)* | **Unavailable** — India-specific legal classification (private/public/one-person-company, etc.) has no existing ForgeX equivalent. `legal_entity_type` (Module 3B) exists but its exact enum values were not designed with MCA's specific category taxonomy in mind — mapping this correctly is a real task for Section 15, not resolved here to avoid inventing a mapping this document can't verify is correct. |

**Fields requiring verification, not just extraction:** every field
above, once it becomes a `ProvenanceRecord` (Section 5), starts at
`status=observed` or `extracted` — **never** `verified` — per Module
5A's own frozen enforcement (Section 1) and this module's explicit
instruction not to create a shortcut to verified data.

**Fields requiring enrichment beyond this source:** `website`, `email`,
`phone`, `gst_number`, `pan`, `msme_number`, `iec_number`,
`export_capable`, and everything under Module 3B's branding/capability
fields — none of these are present in Candidate A's confirmed field
list. Section 14 addresses how these would be added later from other
sources without overwriting what this pilot establishes.

---

## 5. Source → Observation

```
Candidate A (MCA Company Master Data via data.gov.in)
        ↓
AcquisitionJob (Module 5B — collector_type = a future real adapter,
                NOT "mock"; source_id references a SourceRegistry row
                for this specific dataset)
        ↓
RawObservation (Module 5A — one per source record, external_identifier
                = the record's CIN, raw_content = the full source
                record as returned, exactly as Module 5B's existing
                idempotency strategy already expects — see Section 6)
        ↓
ProvenanceRecord (Module 5A — one per mapped field per Company,
                  status = observed or extracted, NEVER verified,
                  extraction_method = rule_based for the direct/
                  transformed mappings in Section 4)
        ↓
Candidate Company
```

**"Candidate Company" is deliberately not defined as a new schema
concept in this document.** Per Section 1's ground truth, `Company`
rows are created today only via direct API calls (Module 3A). This
pilot does not propose an automatic path from `ProvenanceRecord` to a
new `Company` row — that step (turning a cluster of observed/extracted
provenance into an actual candidate Company row a human can review) is
explicitly **Section 15's 5C.6/5C.7 scope**, not resolved
architecturally in this document beyond stating the principle: a
`Company` row is only ever created through **review** (mandatory,
human, per Section 7), never automatically from raw acquisition alone.

**This must never become a shortcut to VERIFIED**, restated per the
brief's own instruction: nothing in this flow, at any stage, sets a
`ProvenanceRecord.status` to `verified`. That remains — exactly as
Module 5A enforces today — a distinct, explicit, human-attributed
action, unconnected to acquisition.

---

## 6. Identifiers

**Strongest available identifier: CIN** (Corporate Identification
Number) — a 21-digit, government-issued, unique identifier, confirmed
as a native field of Candidate A's dataset. This is a **strong-tier**
identifier by the standard Phase 5's own architecture document already
established (Section 8 of that document: "registration identifier...
strongest — near-exact match").

How ForgeX should handle each identifier type for this pilot:

| Identifier | Role |
|---|---|
| CIN | Primary idempotency key (`external_identifier` on `RawObservation`, per Module 5B's existing, unmodified strategy) and, once entity resolution exists (a future module, not this one), the primary strong-tier matching signal against `Company.cin` |
| Company registration number (= CIN in this source) | Same as above — MCA does not appear, per this research, to use a separate "registration number" distinct from CIN for the fields this dataset exposes |
| Website/domain | Not present in Candidate A's field list at all — not usable as an identifier for this specific source/pilot; would become relevant once Section 14's website enrichment is added |
| Normalized company name | A medium-tier signal only (per Phase 5's own architecture document, Section 8) — never used alone, but valuable as a secondary corroboration signal once real entity resolution exists |
| Address | A medium-tier signal, same caveat |

**How this supports future entity resolution:** exactly as Phase 5's
own architecture document (Section 8) already specifies — CIN, being
strong-tier, is the one signal this pilot could eventually support
*automatic* linking on (once entity resolution is actually built, a
future module — not this one). Every weaker signal (name, address)
remains review-queue-only, never sufficient alone, matching that
document's already-established, unmodified rule.

---

## 7. Duplicates

**First-stage strategy for this pilot — detection tiers, not automatic
resolution, per the brief's explicit instruction.**

| Confidence | Condition | Action |
|---|---|---|
| **HIGH** | An incoming record's CIN exactly matches an existing `Company.cin` | Flagged as a high-confidence match candidate — **still not auto-merged** in this pilot's scope (no entity-resolution automation exists, per this module's explicit exclusion list); routed to human review as a "likely existing company, confirm before creating a duplicate" case |
| **MEDIUM** | Normalized name and address both correspond closely to an existing Company, but CIN doesn't match or isn't present on the existing record | Routed to human review with both signals shown — a genuine "might be the same, might not" case a human must decide |
| **LOW** | Only a single weak signal (name alone, address alone) suggests a possible match | Not blocked from becoming its own candidate — but flagged for a human reviewer's awareness, not silently treated as definitely-new either |

**Explicitly, per this module's own hard rule: no automatic merging at
any confidence level in this pilot.** Even a HIGH-confidence CIN match
only *flags* — a human still confirms before any `Company` row is
created or linked. This is stricter than what Phase 5's general
architecture document's own entity-resolution design (Section 8)
eventually allows for "automatic" processing, deliberately: this pilot
has no entity-resolution automation built yet at all (Section 1
confirms this doesn't exist), so *everything* is human-reviewed by
necessity, not just the medium/low tiers.

---

## 8. Data Quality

**Minimum quality requirements for a pilot record to be considered
acceptable for review (not automatically published):**

- **Mandatory identity fields**: `name` and `cin` must both be
  present and non-empty. A source record missing either is rejected
  at validation (Module 5B's existing `AcquisitionJobEvent`
  `FAILED`/per-item handling — reused unchanged), not silently
  accepted with a blank field.
- **Source completeness**: at minimum, the identity fields above plus
  at least one of (`state`, address) — a bare name+CIN with nothing
  else is technically acceptable but flagged as low-completeness for
  reviewer prioritization (Section 12).
- **Freshness**: the source record's own presence in a current
  dataset pull is the only freshness signal available for this pilot
  (no separate "last updated" field was confirmed present on
  individual records in Section 2's research) — flagged as a real
  limitation, not glossed over.
- **Stable identifier**: CIN present, matching the format documented
  by MCA (21-character alphanumeric) — a structural validation, not a
  truth claim about the company itself.
- **Source confidence**: fixed at this pilot's `SourceRegistry.reliability_weight`
  for the registered source row (a single, deliberately conservative
  value — not computed per-record, since Candidate A's structured,
  government-registry nature makes per-record confidence variation
  unlikely to be meaningful at pilot scale).

**What a "quality score" would mean here, stated explicitly per the
brief's own instruction not to create one without explaining its
meaning:** this pilot does not compute a composite numeric quality
score at all. The dimensions above are pass/fail gates for entering
the review queue, not inputs to a blended score — matching Phase 5's
own architecture document (Section 10)'s caution that a quality score
must never be presented as objective truth, which is most safely
honored at this small a scale by not inventing one yet.

---

## 9. Pilot Size

**Recommendation: 25–50 companies for the first real pilot run.**

Within the brief's suggested 10–100 range, chosen at the lower-middle
of that range specifically because:

- The objective (per the brief's own framing) is to validate the
  pipeline, not maximize record count — a smaller number is easier to
  **manually verify by hand** against the real MCA source (spot-checking
  every single pilot record against the source is realistic at 25–50,
  not at 100).
- A number in this range still exercises every code path this
  document's success criteria (Section 16) require — idempotency,
  duplicate detection at all three tiers, and honest partial-failure
  handling all need more than a handful of records to be meaningfully
  tested, but don't need hundreds.
- Small enough that if the pilot reveals a real problem (a licensing
  concern, a data-quality surprise, a mapping error) the blast radius
  of already-collected data is trivial to review or discard entirely.

---

## 10. Legal / Compliance Gate

**This section does not provide legal advice — it identifies exactly
what requires legal review before any implementation begins, per the
brief's explicit instruction.**

| Area | Status from this research | Requires legal review? |
|---|---|---|
| Terms of use (data.gov.in platform-wide) | NDSAP-associated open license found and quoted directly (Section 2) — favorable | **Yes, still** — to confirm the specific "Company Master Data" dataset page carries this same license tag, not assumed identical to every OGD dataset |
| API licensing | Free registration confirmed; specific API terms-of-service document was not independently retrieved and read in full during this research pass | **Yes** — the actual API ToS document should be read in full, not inferred from secondary sources |
| Redistribution rights | The license text found explicitly permits derivative works/redistribution | **Yes, still** — confirm this applies to the specific dataset, and confirm what "redistribution" means in context (ForgeX would be transforming/serving derived data, not republishing the raw dataset verbatim — a distinction worth explicit confirmation) |
| Database rights | Not researched in this pass — India's specific legal treatment of compiled government datasets was not verified | **Yes** |
| Personal information | MCA Company Master Data as scoped in Section 2 does not appear to include individual directors' personal contact details in the fields this pilot would collect (company-level fields only) — but this should be explicitly confirmed, not assumed, especially if any future field expansion touches director-level data | **Yes, if scope ever expands beyond company-level fields** |
| Scraping restrictions | Not applicable to Candidate A as selected (structured API/CSV, not scraping) — but directly disqualifying for Candidate B, which is exactly why B was not selected |
| robots.txt | Not applicable to an API-based collection method |
| Commercial use restrictions | The license text found explicitly includes "commercial... purposes" — favorable, but per-dataset confirmation still recommended alongside the redistribution-rights review above |

**Overall determination: Candidate A is the strongest available
option, with real, confirmed evidence of a favorable licensing
framework — but is not asserted as fully legally cleared.** Per the
brief's own instruction ("if licensing or terms cannot be verified,
mark the source: LEGAL REVIEW REQUIRED"), the specific items above
requiring confirmation are marked accordingly, and **no real collection
should begin until they are confirmed**, even though this pilot's
architecture is otherwise ready.

---

## 11. Operational Design

Using Module 5B's existing architecture exactly as built (Section 1) —
nothing new proposed here beyond configuration values for this
specific pilot:

- **Acquisition frequency**: manual/on-demand for the pilot (a human
  triggers each `AcquisitionJob` via the existing admin-gated API) —
  not scheduled, matching this phase's small, deliberately-supervised
  scope. Scheduled refresh (Phase 5's general architecture document,
  Section 13) is future work, not this pilot.
- **Rate limits**: since data.gov.in's specific numeric limits weren't
  confirmed in this research (Section 2), the real adapter's
  `validate_config`/`collect` implementation (Section 15, not built
  yet) must read whatever limit the API's own documentation or
  response headers indicate at implementation time, and respect it
  conservatively until confirmed — this document does not invent a
  specific number.
- **Retry behavior**: reuses Module 5B's existing bounded retry
  (`MAX_RETRIES = 3`) and `RetryableCollectorError`/
  `NonRetryableCollectorError` distinction unchanged — an API timeout
  or 5xx response would be retryable; an invalid/expired API key would
  not be.
- **Failure handling**: reuses Module 5B's existing per-item
  `AcquisitionJobEvent` outcome tracking unchanged — a malformed
  individual record fails that one item without aborting the whole
  job, exactly as already built and tested.
- **Logging**: structured logging, matching this codebase's existing
  `structlog` convention (used throughout Modules 1–5B) — job start/
  end, record counts, and failures logged with the job's real ID for
  traceability, never with raw API key values (Section 13).
- **Credentials**: the data.gov.in API key would be provided via
  environment variable, following this codebase's established
  `.env`/`.env.example` convention (every prior module) — never
  hardcoded, never committed.
- **Monitoring**: Section 12.
- **Source availability**: if data.gov.in is unreachable, this is a
  `RetryableCollectorError` under Module 5B's existing model — no new
  handling needed.

---

## 12. Observability

Pilot-specific metrics, layered on Module 5B's existing
`AcquisitionJob` fields (`result_count`, `skipped_count`,
`failed_count`, `retry_count` — all real, already built) plus new
pilot-specific tracking a future real adapter's implementation would
need to surface:

- Records requested (how many the API/CSV pull targeted)
- Records received (how many the source actually returned)
- Records accepted (passed Section 8's minimum quality gates)
- Records rejected (failed those gates — with the specific reason,
  reusing `AcquisitionJobEvent.error_message`, already built)
- Duplicates detected, per confidence tier (Section 7)
- Failures, per Module 5B's existing categorization
- Processing time (job `started_at`/`completed_at`, already real
  fields)
- Source errors (API-level error responses, distinct from ForgeX-side
  processing failures)
- Provenance coverage: the fraction of accepted records that produced
  at least one `ProvenanceRecord` per mapped field (Section 4) — a
  real, checkable completeness metric specific to this pilot's success
  criteria (Section 16)

---

## 13. Security

- **API credential storage**: environment variable, per this
  codebase's established convention — never in Git, never in
  `requested_scope` as stored on `AcquisitionJob` (Module 5B's
  existing `redact_config` mechanism, already built and tested,
  applies unchanged to any future real adapter's configuration).
- **Secret redaction**: reuses Module 5B's existing
  `app/collectors/secrets.py` fixed-key-name-denylist redaction
  unchanged — no new redaction logic is proposed for this pilot.
- **Access control**: reuses Module 5B's existing `Role.ADMIN` gate
  unchanged — a future real India-source adapter's jobs would be
  created and monitored through the exact same restricted API surface
  already built.
- **Audit trail**: `AcquisitionJob.created_by` (already a real field,
  Module 5B) plus this codebase's existing `AuditLog` mechanism
  (Module 2) — the natural extension point, matching Phase 5's general
  architecture document's own Section 20 recommendation, not a new
  mechanism invented here.

**No credentials may be committed to Git** — restated as a hard rule
this document does not relax in any way for this pilot.

---

## 14. Future Enrichment

How Candidate A's pilot data would eventually combine with other
sources, **without blindly overwriting trusted information**:

- **Company website**: once a pilot Company has a real `cin` and
  `name`, a *future* (not this module's scope) website-discovery step
  could locate and collect from the company's own site — adding
  `website`, richer `industry` detail, and branding-adjacent fields
  Candidate A doesn't provide (Section 4). Per Phase 5's general
  architecture document's own conflict-handling design (Section 14 of
  that document, unmodified here), a website-sourced value that
  disagrees with an MCA-sourced value for the *same* field would enter
  a conflict state, not silently overwrite the government-sourced
  value — government registry data is a plausible candidate for
  *higher* source precedence on legal-identity fields specifically
  (name, registration date), by that same document's own
  per-field-type precedence principle.
- **Company documents**: Module 3B's existing document-upload system
  is untouched by this pilot — a claimed company (Section 12 of the
  general Phase 5 architecture document, not built in this module)
  could later supply documents corroborating or extending pilot data.
- **Company-submitted data**: per that same document's Section 12
  principle (also unmodified, not built here): a company claiming a
  pilot-created record would have their self-submitted edits enter the
  *same* review pipeline as any other source, not silently overwrite
  MCA-sourced legal-identity fields.
- **Other licensed sources**: Candidate D (Section 2) remains a future
  possibility once its licensing is independently confirmed — this
  pilot's field-mapping approach (Section 4: explicit, no invented
  values, clear "unavailable" marking) is the template any future
  source's mapping would follow, not a one-off.

---

## 15. Implementation Plan (Not Built Yet)

Proposed sequence, for a **future, separately-approved** implementation
phase — not built, not started, in this document:

| Step | Scope |
|---|---|
| 5C.1 Source adapter | A real `SourceAdapter` implementation for Candidate A's confirmed API/CSV mechanism, registered in `app/collectors/registry.py` alongside (not replacing) `MockSourceAdapter` |
| 5C.2 Configuration | The API key, base URL, and (once confirmed, Section 10/11) rate-limit handling, via `SourceRegistry` + environment-variable credentials (Section 13) |
| 5C.3 Field mapping | Implementing Section 4's mapping table as real extraction/normalization logic, producing `ProvenanceRecord` candidates |
| 5C.4 Pilot acquisition | Running a real `AcquisitionJob` against Section 9's 25–50-record target |
| 5C.5 Validation | Section 8's quality gates, applied for real |
| 5C.6 Review | A human review step turning accepted, non-duplicate candidates into an actual decision — this is where "Candidate Company" (Section 5) becomes a real, reviewed judgment, not an automatic pipeline output |
| 5C.7 Canonical Company creation | Only after 5C.6 — a real `Company` row created via the existing Module 3A creation path, with its originating `ProvenanceRecord`s linked, still `unverified` per Module 3B's own status model unless independently verified |
| 5C.8 Monitoring | Section 12's metrics, wired to real data |

**Do not implement these now** — restated per the brief's explicit
instruction. This table exists to make the next phase's scope legible
in advance, not to authorize starting it.

---

## 16. Success Criteria

Module 5C (architecture) is complete now; a **future** implementation
phase would be considered successful only once all of the following
are true:

- ✓ A legally approved source (Section 10's open items resolved, not
  just Section 3's recommendation accepted provisionally)
- ✓ Real source access proven (a real API call or CSV pull actually
  succeeds against Candidate A)
- ✓ 25–50 real records collected (Section 9)
- ✓ Every record has real provenance (a `RawObservation` and at least
  one `ProvenanceRecord` per mapped field, per Section 5 — checkable
  via Section 12's provenance-coverage metric)
- ✓ Every record has a stable source identifier (CIN present and
  structurally valid, Section 6/8)
- ✓ No fabricated fields (Section 4's "unavailable" fields remain
  unavailable — never backfilled with invented values)
- ✓ Duplicate behavior understood and observed at all three confidence
  tiers (Section 7) — not just designed, but actually exercised
  against real data
- ✓ Failed requests handled safely (Module 5B's existing retry/failure
  model, exercised against a real source's real failure modes, not
  just the mock adapter's simulated ones)
- ✓ Repeat acquisition is idempotent (Module 5B's existing idempotency
  key, proven against real CINs — a second pull of the same source
  window produces skips, not duplicates)
- ✓ Existing Company/Product tests remain green (no regression to
  Modules 3A/3B/4B/5A/5B's own test suites)

---

## 17. What Must Not Happen

Explicitly prohibited, restated verbatim from the brief as hard
boundaries this document does not relax:

- ❌ Mass scraping
- ❌ Unlicensed data redistribution
- ❌ Automatic verification
- ❌ Automatic unsafe merging
- ❌ Fabricated enrichment
- ❌ Bypassing source protections
- ❌ Storing credentials in Git
- ❌ Connecting arbitrary external APIs
- ❌ Changing Company/Product architecture

---

## 18. Final Self-Review

- ✓ **Module 5A unchanged** — confirmed via direct inspection in
  Section 1; no model, service, or migration referenced was modified.
- ✓ **Module 5B unchanged** — same; `SourceAdapter`, collector
  registry, `AcquisitionJob`, idempotency, and retry logic are all
  reused exactly as built, never altered.
- ✓ **No implementation code** — this document, and only this
  document, was created this phase.
- ✓ **No migration** — none created.
- ✓ **No external connection** — every claim about Candidate A's API
  was established via web research about its public documentation,
  not by connecting to it.
- ✓ **One pilot source selected**, with explicit, itemized items still
  marked **LEGAL REVIEW REQUIRED** (Section 10) rather than glossing
  over uncertainty — the brief's "or explicitly say so" alternative
  wasn't fully triggered (a source *was* selected), but neither was
  full legal clearance overclaimed.
- ✓ **India-first** — Candidate A is India's own national company
  registry, republished through India's own official open-data
  platform.
- ✓ **Provenance preserved** — Section 5 routes every pilot record
  through Module 5A's real, unmodified `RawObservation`/
  `ProvenanceRecord` model, with the OBSERVED/EXTRACTED/VERIFIED
  distinction explicitly upheld (Section 5's closing paragraph).
- ✓ **Company/Product/Offering architecture preserved** — Section 4's
  field mapping works entirely within `Company`'s existing real
  columns; where no column fits, the value is marked unavailable, not
  forced in or used to justify a schema change.
- ✓ **ForgeX branding used everywhere** — no prior naming appears
  anywhere in this document.
- ✓ **Future global expansion remains possible** — Section 2's source
  taxonomy and Section 6/7's identifier/duplicate-tier framework are
  the same general shapes Phase 5's own architecture document already
  established generically (not India-specific in their *design*, only
  in this pilot's *application* of them) — a future non-Indian
  registry would slot into the identical structure.

**Stop after this architecture document. Awaiting explicit approval
before implementing Module 5C.**
