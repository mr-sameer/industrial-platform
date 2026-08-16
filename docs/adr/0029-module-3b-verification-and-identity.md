# 0029 — Module 3B: Company Verification & Industrial Identity

## Status
Accepted

## Context
Module 3B extends the Company domain (Module 3A) with business identity,
branding, industry classification, and a verification-scoring engine,
without modifying Module 3A's schema or router. This ADR consolidates
every scope/design decision made across the module — kept as one entry
rather than five or six small ones, since they're all facets of the same
underlying question: how much of the long-term domain model
(`docs/domain/`) does this module actually build versus defer.

## Decisions

### 1. Verification is always computed live, never stored as an editable field
The module brief is explicit: "Verification must be calculated
automatically. No manual editing." `app.services.verification_score_service.calculate`
computes percentage/level/missing-requirements fresh, every call, from
current data (owner email verification, business info completeness,
document presence, branding, etc.) — there is no `PATCH
.../verification` endpoint anywhere, and there must never be one. Module
3A's existing `Company.verification_status` (a coarse two-state field)
is kept, unmodified in schema, and now kept in sync automatically by the
same computation (`sync_legacy_verification_status`) — never manually
settable either.

### 2. Scoring weights live in one config module, not scattered
`app.core.verification_rules.VERIFICATION_REQUIREMENTS` is the single
source of every weight/threshold (asserted to sum to 100 at import
time). Per the brief's "never hardcode scores, use configuration."
Today this is a Python-level config, not a database table or admin-
editable setting — no product requirement yet justifies runtime-editable
scoring, and moving it to a DB table later doesn't change
`VerificationScoreService`'s logic, only where the list is loaded from.

### 3. No admin-approval workflow for documents — `verified_by`/`verified_at` are genuinely unset placeholders
The module brief lists these fields explicitly as placeholders, and the
"Admin Features" section only lists Company Owner actions (upload/
delete/replace/view progress) — no Platform-Admin review UI or endpoint
is in scope. Consequently, `VerificationScoreService` counts a document
as satisfying a requirement once **uploaded** (`status != rejected/expired`),
not once **approved** — requiring admin approval for scoring would make
every document-gated requirement permanently unreachable in this module,
since nothing here can ever set `status = verified`. This is a
deliberate, load-bearing design choice: the score today measures
*profile/evidence readiness*, not admin-confirmed *ground truth* — a
future admin-review module can tighten this (e.g. require `status ==
verified`) without changing the requirement list or weights, only the
one `_has_document_of_type` check.

### 4. "Company Owner" in the brief's Admin Features section is read as "Owner and Admin"
Document upload/delete/replace requires `CompanyRole.ADMIN` or above
(Owner qualifies), not literally Owner-only — matching Module 3A's own
established Certificate-upload permission pattern
(`docs/domain/09-permission-matrix.md` footnote 6) rather than
introducing a stricter, inconsistent rule for conceptually the same
action. Flagged explicitly since the brief's literal wording says
"Company Owner," not "Owner and Admin."

### 5. Existing Module 3A fields are reused, not duplicated
- `Company.gst_number` (3A) **is** GSTIN — the brief's Business
  Information section lists GSTIN separately, but adding a second column
  for the same concept would be worse than reusing the existing one.
  `BusinessInfoUpdate` accepts `gst_number`, not a new `gstin` field.
- `Company.description` (3A) **is** the long-form description — Module
  3B only adds `short_description`, not a duplicate "long_description."
- `Company.website` (3A) **is** the "Website" social link — the new
  `company_social_links` table covers exactly the remaining platforms
  the brief lists (LinkedIn, YouTube, Facebook, Instagram, X), not
  Website again.
- "Business License" (listed under both Business Information and
  Verification Documents in the brief) is modeled as a
  `DocumentType.BUSINESS_REGISTRATION` upload only — no separate
  `business_license` column exists on `Company`.

### 6. "Factory Verified" exists as a level without a Factory entity
Neither Module 3A nor 3B's DATABASE section lists a `Factory` table —
that entity is deferred (per `docs/domain/18-architecture-review.md`'s
own "design attachment points, not the future feature" principle, and
Module 3A's precedent of deferring Industry/Category). The
`factory_verified` level is still meaningful today: it's satisfied by
`business_type` being set, a `factory_license` document being uploaded,
and manufacturing categories being specified — a reasonable proxy for
"this looks like a real manufacturer" without needing a Factory
entity/address/location to exist yet. When a future module builds
Factory, this level's requirements should be revisited to include real
factory records, not just document/category proxies.

### 7. File storage: local disk today, S3-shaped interface from day one
`app.core.storage.StorageBackend` is a `Protocol` with exactly the
methods an S3 client naturally has (`save`/`delete`/`get_url`, all
key-based, never path-based). `LocalStorageBackend` is the only
implementation shipped — explicitly not the intended backend for a
real multi-replica production deployment (local disk isn't shared across
replicas; `docker-compose.yml`'s `uploads-data` named volume works for a
single-instance deployment only). Swapping in an `S3Backend` later means
implementing the same three methods and changing `get_storage_backend()`
— zero changes to any service or router.

### 8. Validation is content-based, never trusts client-declared type/filename
Every upload (logo, cover, document) is validated by actually decoding
it (Pillow for images, magic-byte check for PDFs) — never by trusting
the `Content-Type` header or file extension, both trivially spoofable.
Virus scanning is a documented placeholder (`app.core.file_validation.scan_for_viruses`)
— no scanning engine is integrated, matching this project's established
pattern for out-of-scope integrations (Module 2.5's `EmailSender` stub).

### 9. Static file serving via a StaticFiles mount, not a signed-URL scheme
Uploaded files are served back at `/uploads/*` via FastAPI's
`StaticFiles`, mounted over `LocalStorageBackend`'s storage directory.
No access control on that mount — every uploaded file is publicly
fetchable by anyone who knows (or guesses) its URL. Acceptable for this
module: nothing uploaded here (logos, cover images, verification
documents) is confidential in the sense of "must never be seen by a
non-member" — a verification document's whole *purpose* is eventually to
be evidence a Buyer or Platform Admin can see. If a future document type
needs real access control, that's a new requirement for the storage
layer (signed, expiring URLs), not a retrofit of this module's shape.

## Consequences
- `docs/domain/18-architecture-review.md`'s Weakness #4 (factory-specific
  vs. company-wide certificate aggregation into verification tier) is
  effectively answered by this module's scoring design: a document's
  `company_id` scope is all that matters today (no factory-specific
  documents exist since no Factory entity does) — revisit when Factory
  lands.
- The single biggest deferred piece of trust infrastructure this module
  leaves for later is admin-side document review — flagged repeatedly
  above, not hidden. A Platform Admin reviewing/approving/rejecting
  documents (and the scoring implications of switching from
  "uploaded" to "approved" as the bar) is natural Module 3C+ work.
