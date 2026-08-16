# 0033 — Phase 4B: Industrial Product Graph (Company Module #2)

## Status
Accepted.

## Context
Implements exactly the five entities
`docs/product/phase-4a-industrial-product-graph-architecture.md` scoped
for this phase: `ProductCategory`, `Product`, `ProductSpecification`,
`ProductAttribute`, `Offering`. This is the Product domain's first real
implementation — everything before this phase (Modules 1–3B, the
homepage, Discover, Consult) worked entirely within the Company domain
or against it via free-text substring matching.

## Decisions

1. **Offering is the bridge, never a copy.** Per this module's own
   ABSOLUTE RULE and Phase 4A Section 2: `Product` carries zero
   company-specific data. Role, MOQ, lead time, capacity, country, and
   a (deliberately simple, unscored) per-offering verification status
   all live on `Offering`. Verified directly: a real test creates one
   Product and three companies each offering it under a different role
   — the Product row never duplicates.
2. **Role is per-Offering, not per-Company** — a refinement of
   `Company.business_type` (Module 3A), which is company-wide. A
   company can be a `manufacturer` for one product and a `distributor`
   for another; `uq_offering_company_product_role` (a unique
   constraint on company+product+role, not just company+product) makes
   this expressible while still preventing a true duplicate.
3. **Industry stays free text on `Product`**, matching
   `Company.industry`'s existing Module 3A pattern (`docs/adr/0023`) —
   introducing a linked Industry entity is explicitly out of this
   phase's "Only these" entity scope.
4. **Specifications are Entity-Attribute-Value**, scoped per Category
   (`ProductSpecification` = definition, `ProductAttribute` = value) —
   Phase 4A Section 5's dynamic specification system. Adding a new spec
   to a category is one row insert, never a migration. Verified
   directly: Motors and Pumps get entirely independent specification
   sets in the same test run.
5. **Offering mutation routes live under `/companies/{company_id}/offerings`**,
   not `/offerings`, specifically so `company_id` is sourced from the
   URL path and `app.core.company_authorization.require_company_role`
   can be reused completely unchanged — that module's own documented
   rule is to never trust a company id claimed in a request body. An
   IDOR test confirms one company cannot mutate another's offering via
   this path.
6. **Products start in `DRAFT` and require no admin review to reach
   `PUBLISHED`** — the same deliberately-incomplete pattern as
   `VerificationDocument.verified_by`/`verified_at` (Module 3B,
   `docs/adr/0029`). Documented as a real, explicit gap here rather
   than quietly left unmentioned.
7. **No dedicated `GET /offerings/{id}` endpoint.** The Offering Detail
   frontend page resolves an offering by fetching its product's
   offering list and finding the match client-side — a deliberate,
   documented trade-off (`apps/web/src/lib/products.ts`) to avoid new
   API surface for a single, minimal, internal page. Worth adding
   directly if this page's usage grows beyond "admin/testing."

## Real bugs found during implementation (each via a failing test or a real API call, not review alone)

- **500 on product creation**: `ProductAttributePublic.specification_name`/`unit`
  aren't direct attributes on the `ProductAttribute` ORM row — only
  reachable via its `.specification` relationship. Pydantic's
  `from_attributes` couldn't resolve them. Fixed with an explicit
  `_to_detail()` builder in the router instead of a blind
  `model_validate()`.
- **An IDOR risk caught before merging**, not after: the first draft of
  `OfferingCreate` carried `company_id` in the request body. Corrected
  to source it from the URL path per `company_authorization.py`'s own
  rule — see decision 5.
- **Three compounding bugs in the attribute-replacement code path**
  (`product_service._set_attributes`), found via one test
  (`test_update_product_replaces_attributes`) that kept failing for
  three different reasons in sequence: a raw SQL `DELETE` left the
  ORM's in-memory relationship state stale (silently wrong data on
  read-back) → switching to the ORM relationship's own `.clear()`
  raised `MissingGreenlet` (a synchronous lazy-load attempted in an
  async session, since `create_product` calls this right after
  `db.flush()`, before `.attributes` has ever been loaded) → fixing
  that with an explicit `db.refresh()` first exposed a real
  `uq_product_attribute` unique-constraint violation, because the
  delete-orphan cascade's `DELETE` and the new row's `INSERT` could
  land in the same flush batch in the wrong order. Final, verified-
  working fix: `refresh()` → `clear()` → explicit `flush()` → `append()`.

## Consequences
- `docs/architecture/openapi.json` grew from 32 to 42 paths.
- No existing endpoint, model, migration, or test was modified —
  confirmed via a full 139-test run (118 pre-existing + 21 new) with
  zero regressions, and via file-mtime checks against the frontend
  homepage/Discover/Consult files.
- The seed script (`apps/api/scripts/seed_product_graph.py`) is
  idempotent by construction (checks by name/email before creating) —
  safe to re-run in any environment without duplicating data.
