# 0039 — Module 5C: India Company Data Acquisition Pilot (Implementation)

## Status
Accepted.

## Context
Implements the pilot approved in
`docs/product/phase-5c-india-company-data-source-architecture.md`:
MCA Company Master Data via data.gov.in, plugged into Module 5A
(frozen, `80f4335cb6ce693e21198992bfd2ac2e0f6134ce`) and Module 5B
(frozen, `bb0d377111ae7b42e5c0cae49292db74f0538f0b`) exactly as they
exist, with zero modification to either.

## The network constraint, investigated and documented, not assumed

Before writing any collector code, connectivity to `data.gov.in` was
tested directly rather than assumed either way:

- `bash_tool`'s network returns `HTTP 403` from the egress proxy on
  every subdomain tried (`data.gov.in`, `www.data.gov.in`,
  `api.data.gov.in`) — a policy-level block, confirmed via a full TLS
  handshake completing before the 403, not a DNS or routing failure.
- `web_fetch` separately reports `ROBOTS_DISALLOWED` for the specific
  catalog page — a distinct, independent confirmation that automated
  access to this exact resource is blocked from this environment by a
  second, different mechanism.

**Conclusion, stated plainly: a real, live pilot run against the real
external source is not achievable from this sandbox, through any tool
available in it.** This is not a design choice or a workaround — it is
a hard environmental fact, checked directly rather than inferred, and
it shapes everything below. No run in this session claims to have
reached the live API; every test uses `monkeypatch` at the exact
`httpx.get` call site, with response payloads built from data.gov.in's
own **confirmed, published field list** (verified via web research
while writing the approved architecture document) — a real schema,
mocked network, stated exactly that way throughout.

## Decisions

1. **No new database tables, no new migration.** `SourceRegistry`,
   `RawObservation`, `ProvenanceRecord`, `DataConflict` (Module 5A) and
   `AcquisitionJob`, `AcquisitionJobEvent` (Module 5B) are all reused
   completely unchanged. Still at migration `0007` after this phase —
   confirmed directly, not assumed.
2. **`MCADataGovInAdapter`** (`app/collectors/mca_data_gov_in_adapter.py`)
   implements `SourceAdapter` exactly as Module 5B defined it, registered
   in `app/collectors/registry.py` alongside (not replacing)
   `MockSourceAdapter`. Real `httpx` calls, real status-code-based
   retryable/non-retryable classification (401/403 → non-retryable,
   429/5xx/timeout/connection error → retryable), a hard config-level
   ceiling of 50 records (this pilot's approved size), and defensive
   multi-casing field extraction since the exact JSON key casing
   wasn't independently confirmable via a live call.
3. **A real bug found and fixed in address normalization**
   (`app/collectors/normalization.py`): the first version of
   `attempt_city_from_address` returned `"Maharashtra"` (the *state*)
   as the extracted city for an address shaped `"...City, State
   PINCODE"` — found by directly testing the function, not by
   inspection. Fixed by using the source's own already-structured
   `Registered State` field to disambiguate the segment nearest the
   PIN code from the actual city segment before it; without a known
   state to disambiguate against, the function now returns `None`
   rather than risk the same silently-wrong guess.
4. **A real architectural constraint found and resolved, not papered
   over**: Module 5A's `ProvenanceRecord` has an enforced `CHECK`
   constraint requiring an already-existing `company_id` or
   `product_id` — it cannot be created "standalone." The ticket's own
   pipeline diagram (`RAW OBSERVATION → PROVENANCE → ... → CANONICAL
   COMPANY`) implies provenance exists before the Company row does,
   which isn't achievable without modifying Module 5A (prohibited).
   `company_promotion_service.promote_raw_observation_to_company`
   resolves this the only way consistent with both constraints: the
   Company row is created first (directly from the raw observation's
   content, after the CIN duplicate check), and `ProvenanceRecord`s
   are created immediately afterward inside the same call, linking
   each mapped field to the company that was just created — so a
   Company never exists, even momentarily, without its provenance from
   the caller's perspective. This is a real, documented deviation from
   the literal diagram ordering, made for a confirmed reason, not a
   convenience shortcut — see `company_promotion_service.py`'s own
   module docstring for the full reasoning.
5. **Every raw field is preserved as provenance, even fields with no
   Company column.** `company_status`, `company_class`,
   `company_category`, `sub_category`, `authorized_capital`,
   `paid_up_capital`, `registrar_of_companies`, and the full
   `registered_office_address` all get a `ProvenanceRecord`
   (`extraction_method=manual`, `status=observed`) even though none of
   them map to an existing `Company` column — confirmed by a dedicated
   test, matching the ticket's explicit "do NOT silently discard
   provenance."
6. **CIN is the sole automatic duplicate gate, and it only ever
   blocks — never merges.** `find_existing_company_by_cin` runs before
   any Company is created; a match raises `DuplicateCinError` → `409`,
   requiring a human to resolve manually. No fuzzy name/address
   matching is implemented in this phase at all (explicitly out of
   scope per the ticket), so nothing below CIN-exact-match can ever
   auto-block or auto-merge either — there is no lower-confidence
   automation to accidentally trigger.
7. **The data trust rule is enforced by construction, not convention.**
   `promote_raw_observation_to_company` never touches
   `Company.verification_status` — a promoted company's verification
   status is whatever `Company`'s own model default is (`unverified`),
   identical to a company created through the ordinary `POST
   /companies` flow. Confirmed directly by a test asserting
   `verification_status == "unverified"` immediately after promotion,
   and a second test confirming every created `ProvenanceRecord`'s
   status is `observed` or `extracted`, never `verified`.
8. **A found gap in `CompanyDetail`, worked around correctly, not by
   modifying Module 3A.** The reused `CompanyDetail` response schema
   doesn't include `cin` at all — that field lives on Module 3B's
   separate business-info endpoint, confirmed by direct schema
   inspection after a test failed on exactly this. Verified via that
   existing endpoint instead of adding `cin` to `CompanyDetail`, which
   would have been a real, prohibited Company-domain schema change.
9. **RBAC: `Role.ADMIN`, matching Module 5B's own established
   pattern**, for both new routes (`GET .../observations/{id}`,
   `POST .../observations/{id}/promote`) — reviewing and promoting
   acquired data is exactly the kind of consequential action that
   pattern exists for.
10. **New API routes live in a new file** (`app/api/v1/acquisition_review.py`),
    not added to `app/api/v1/provenance.py` (Module 5A) or
    `app/api/v1/acquisition.py` (Module 5B) — both frozen files have
    zero diff from this phase, confirmed directly.

## Verification
- Full backend suite: **211/211 passing** (189 pre-existing + 22 new,
  `tests/test_mca_pilot.py`), `ruff`/`mypy --strict` clean across all
  92 backend source files.
- Frontend `tsc`, ESLint, Vitest (12/12, untouched), and a production
  build all clean — route list and bundle sizes byte-identical to
  before this module (backend-only, per the ticket's explicit
  instruction).
- No migration created — confirmed directly (`alembic/versions/`
  still ends at `0007`).
- `docs/architecture/openapi.json` regenerated: 54 → 56 paths.

## Known limitations (stated directly, not hidden)
- **No live pilot run against the real source was performed or
  claimed** — see the network-constraint section above. Every test
  uses a real, confirmed field schema against a mocked network
  boundary.
- **Exact JSON key casing from a live data.gov.in response was never
  confirmed** — the adapter defends against multiple plausible
  casings, but the first real run (by an operator with actual network
  access) should confirm this and simplify the extraction logic once
  confirmed.
- **Address→city parsing remains a best-effort heuristic**, honestly
  bounded (returns `None` rather than guess when it can't disambiguate
  against a known state) — not a general address parser.
- **The reviewing admin becomes the promoted Company's technical
  Owner** (`create_company`'s existing, unmodified contract requires
  an owner) — this is an administrative placeholder for an
  acquisition-sourced company pending a real company representative
  claiming it later (a future phase's scope, per the approved
  architecture's Section 12/14), not a claim that the admin is
  affiliated with the real company. Stated here so it's never mistaken
  for one.
- **Legal-review items from the approved architecture remain
  outstanding** — this implementation does not resolve them; it
  implements the pipeline that would use the source once they are
  resolved.

## Consequences
No architectural deviation beyond the one documented and justified
above (decision 4). Modules 5A and 5B remain frozen and unmodified,
confirmed directly, not assumed.
