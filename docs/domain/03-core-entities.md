# 3. Core Business Entities

Every entity below follows the same template: **Purpose**, **Lifecycle**,
**Key Attributes** (conceptual, not a schema — types are indicative),
**Relationships**, **Ownership**, **Business Rules**. Value objects
(Address, Money, etc.) are covered separately in Section 6 and referenced
here by name.

Entities marked **(existing)** were built in Module 2/2.5 and are
described here for completeness/context, not redesigned.

---

## User *(existing)*

**Purpose:** the single human (or, in principle, service-account)
identity on the platform, authenticated once and usable across every
Company relationship it holds.

**Lifecycle:** Registered → Active → (Deactivated | Deleted). See
Module 2.5's session/auth lifecycle for the authentication side; this
entity's *business* lifecycle is simpler than its *auth* lifecycle.

**Key Attributes:** id, email, full name, platform `Role` (flat:
`admin`/`analyst`/`viewer` — see reconciliation note below),
is_email_verified, created_at.

**Relationships:** one User → many `CompanyMember` (a user can belong to
multiple companies); one User → many `SavedSupplier`, `Collection`,
`AIConversation`, `Review`, `SearchHistory`.

**Ownership:** owns its own profile data. Does not own Company data
merely by being its creator — see `CompanyMember`/`Company` below for how
company-level ownership is actually modeled.

**Business Rules:** see Section 8 ("a user may own multiple companies").

**Reconciliation with the existing platform `Role`:** Module 2's `Role`
enum (ADR-0013) is a **platform-level** role, answering "what can this
user do to the platform itself" (today: nothing differentiated yet — no
protected route uses it). It is orthogonal to the **company-scoped**
roles this document introduces (`Company Owner`/`Admin`/`Editor`/
`Viewer`) and the **platform-operations** roles (`Platform Admin`/
`Support`/`Moderator`). Section 18 recommends explicitly how these two
role systems should be reconciled at implementation time.

---

## Company

**Purpose:** the core unit of trust and business identity on the
platform — a Seller's storefront, a Buyer's organizational identity, or
both.

**Lifecycle:** Draft (created, incomplete profile) → Active (published,
searchable) → (Suspended | Archived). Verification status (Section 8) is
a separate, parallel lifecycle — a Company can be Active without being
Verified; visibility/ranking, not existence, is what verification gates.

**Key Attributes:** id, legal name, display name, description, industry
(FK to `Industry`), website (`Website` VO), business type (Buyer |
Seller | Both), founded year, employee count range, registration number,
tax id, headquarters `Address`, status.

**Relationships:** one Company → many `CompanyMember`; one Company → many
`Factory`; one Company → many `Product`; one Company → many `Certificate`
(via Verification); one Company → many `Gallery` images; one Company →
many `Document`; one Company → many `Review` (as subject); one Company →
many `SavedSupplier` (as target, from many Users).

**Ownership:** owned collectively by its `CompanyMember`s, with exactly
one holding the `Owner` role at any time (Business Rule, Section 8).

**Business Rules:** must have exactly one Owner; business_type determines
which features are relevant (a pure-Buyer company has no Products); see
Section 8 for the full list.

---

## Company Member

**Purpose:** the join entity between `User` and `Company`, carrying the
company-scoped role that determines what that user can do *within that
specific company's context*.

**Lifecycle:** Invited → Active → (Removed | Left). An invitation is
itself a sub-state worth tracking (see Domain Events, Section 7:
`UserInvited`).

**Key Attributes:** id, user_id (FK), company_id (FK), role (Owner |
Admin | Editor | Viewer), invited_by (FK to User), joined_at, status.

**Relationships:** many-to-one to both `User` and `Company` — this is the
entity that makes the User↔Company relationship many-to-many.

**Ownership:** owned by the Company (an Owner/Admin manages membership);
the underlying User does not unilaterally control their `CompanyMember`
row's role, but can unilaterally leave (subject to the "must have one
Owner" rule blocking the last Owner from leaving without transferring
ownership first).

**Business Rules:** exactly one `CompanyMember` per Company may hold
`Owner`; role changes and removals are themselves auditable events (see
`AuditLog`).

---

## Role *(company-scoped, distinct from User's platform Role)*

**Purpose:** the named permission level a `CompanyMember` holds. Modeled
as an enum at Stage 1 (Owner/Admin/Editor/Viewer — matches Section 9's
matrix), not a separate configurable-roles entity.

**Lifecycle:** static/enumerated, not instantiated per-company at Stage
1.

**Key Attributes:** name, an implicit ordered set of `Permission`s (see
Section 9's matrix — the source of truth is that matrix, not a separate
stored mapping, at Stage 1).

**Relationships:** referenced by `CompanyMember.role`.

**Ownership:** platform-defined, not company-customizable at Stage 1 (see
Section 10 for when/why this might change for Enterprise organizations).

**Business Rules:** see Section 9.

---

## Permission

**Purpose:** the atomic unit of "can do X" that a Role grants. Modeled
conceptually here (Section 9's matrix is the authoritative definition);
not necessarily its own stored/queryable entity at Stage 1 — see Section
18 on avoiding a fully dynamic permission system before there's a proven
need for one (e.g. Enterprise custom roles, Section 10).

**Key Attributes (conceptual):** resource (e.g. "Product"), action (Read/
Create/Update/Delete/Invite/Approve/Reject/Export/Manage — Section 9's
columns).

**Relationships:** many Permissions compose a Role.

---

## Industry

**Purpose:** the top level of the product/company taxonomy (e.g.
"Textiles & Apparel," "Industrial Machinery," "Electronics
Manufacturing"). Exists to make Company and Product both filterable and
comparable within a domain.

**Lifecycle:** platform-managed reference data — created/edited by
Platform Admin, not by Sellers.

**Key Attributes:** id, name, slug, description, parent industry
(nullable — allows a shallow hierarchy if needed later).

**Relationships:** one Industry → many `Category`; one Industry → many
`Company` (a company's primary industry).

**Ownership:** platform-owned reference data.

**Business Rules:** a Company's industry should be one of a controlled
set (not free text) so that Search/AI can reliably filter/compare across
companies — this is why Industry is a first-class entity, not a string
field.

---

## Category

**Purpose:** the second level of taxonomy, scoped under an `Industry`
(e.g. under "Textiles & Apparel": "Woven Fabrics," "Knitwear"). This is
what a `Product` is actually classified under.

**Lifecycle:** platform-managed reference data, same governance as
Industry.

**Key Attributes:** id, industry_id (FK), name, slug, description.

**Relationships:** many Category → one Industry; one Category → many
`Product`.

**Ownership:** platform-owned reference data.

**Business Rules:** a Category must belong to exactly one Industry
(no cross-industry categories at Stage 1 — see Section 18 for whether
this is too restrictive).

---

## Product

**Purpose:** a sellable/showcaseable item in a Company's catalog — the
unit a Buyer is ultimately searching for.

**Lifecycle:** Draft → Published → (Archived | Discontinued).

**Key Attributes:** id, company_id (FK), category_id (FK), name,
description, primary image, minimum order quantity, lead time,
status.

**Relationships:** many Product → one Company; many Product → one
Category; one Product → many `ProductVariant`; one Product → many
`Gallery` images; one Product → many `Review` (product-level reviews are
a Stage 1+ consideration — see Section 18).

**Ownership:** owned by the Company (managed by Owner/Admin/Editor per
Section 9).

**Business Rules:** belongs to exactly one Company (Section 8); a Product
with zero Variants is valid (simple/undifferentiated products don't need
variant complexity forced on them).

---

## Product Variant

**Purpose:** the specific, orderable configuration of a Product — the
granularity industrial buyers actually need (exact material grade,
dimension, tolerance, finish, packaging) that a single "Product" record
can't express.

**Lifecycle:** tied to its parent Product's lifecycle; can be individually
discontinued while the parent Product remains active.

**Key Attributes:** id, product_id (FK), sku, name/label (e.g. "304
Stainless, 2mm, Mirror Finish"), spec attributes (structured key-value —
see Section 18 for the tradeoff between structured attributes vs. a
flexible schema-less bag), price range or "quote on request" flag, unit
of measure.

**Relationships:** many ProductVariant → one Product.

**Ownership:** owned by the Company via the parent Product.

**Business Rules:** a Variant's spec attributes should be validated
against its Category's expected attribute set where that's defined (this
is a future data-quality feature, not a Stage 1 hard requirement).

---

## Certificate

**Purpose:** a claimed credential (ISO certification, industry-specific
compliance mark, test report) that a Company or Factory holds — the
primary evidence type that `Verification` evaluates.

**Lifecycle:** Uploaded → (Pending Review | Verified | Rejected) →
(Active | Expired | Revoked). Expiration is a first-class state, not an
afterthought — see Business Rules, Section 8 ("certificates expire").

**Key Attributes:** id, company_id (FK), factory_id (nullable FK — a
certificate can be company-wide or factory-specific), certificate type,
issuing body, certificate number, issue_date, expiry_date, document (FK
to `Document`), verification_status.

**Relationships:** many Certificate → one Company; many Certificate →
zero-or-one Factory; one Certificate → one `Document` (the uploaded
evidence file); many Certificate → related `Verification` records
(a certificate may be re-verified over time).

**Ownership:** owned by the Company; verification status is set by the
Verification context/Platform Admin, not self-reported by the Company.

**Business Rules:** an expired Certificate must not continue to
contribute to trust signal/ranking (see Section 8); a Certificate's
`verification_status` is independent of the parent Company's overall
verification tier — a Company can be partially verified (some
certificates verified, others pending).

---

## Verification

**Purpose:** the structured process and resulting state that establishes
trust in a Company's (or specific Certificate's) claims. The platform's
core differentiator — modeled with the architectural weight that implies.

**Lifecycle:** Requested → Under Review → (Approved | Rejected) →
(Active | Expired | Revoked). Revocation is reachable from Active, not
just from the initial review (see Business Rules, Section 8:
"verification can be revoked").

**Key Attributes:** id, company_id (FK), requested_by (FK to User),
reviewed_by (nullable FK to User — a Platform Admin/Support/Moderator),
tier (see Section 8/10 for tiering), status, requested_at, decided_at,
expiry (verification itself can expire and require renewal, distinct
from an individual Certificate's expiry), rejection_reason (nullable).

**Relationships:** many Verification → one Company; one Verification
references many `Certificate` (the evidence considered); one
Verification → many `AuditLog` entries (every state transition is
audited).

**Ownership:** requested by the Company (via an Owner/Admin), decided by
Platform Admin/authorized Moderator — this asymmetry (who requests vs.
who decides) is the entire point of the entity.

**Business Rules:** see Section 8 in full; most load-bearing rule: trust
signal shown to Buyers must always reflect the *current* Verification
state, including revocation, with no caching/staleness that could show a
revoked company as verified.

---

## Factory

**Purpose:** a physical production site belonging to a Company — the
thing a buyer actually wants evidence of when they ask "do you really
manufacture this, or are you a trading company?"

**Lifecycle:** Added → (Active | Inactive). Simpler lifecycle than
Company/Verification — a Factory's own trust weight comes from its
associated Certificates, not an independent Factory-level verification
state at Stage 1.

**Key Attributes:** id, company_id (FK), name, `Location` (VO), `Address`
(VO), production capacity (free text or structured — see Section 18),
established year, employee count.

**Relationships:** many Factory → one Company; one Factory → many
`Certificate` (factory-specific certifications); one Factory → many
`Gallery` images.

**Ownership:** owned by the Company.

**Business Rules:** a Company may have zero Factories (pure trading/
distribution companies are valid Sellers — Section 8) or many
(multi-site manufacturers — Section 10).

---

## Location

**Purpose:** a Value Object (see Section 6) representing a geographic
point — not an independent entity with its own identity/lifecycle. Listed
here because the brief's minimum entity list names it, and its usage
context (attached to Factory, Company headquarters) belongs in this
section for completeness.

**Key Attributes:** latitude, longitude, city, region/state, country,
postal code.

**Relationships:** embedded in `Company` (headquarters) and `Factory`
(site location) — not a separate table with foreign keys pointing to it
in a normalized sense, though it may be stored in its own columns/JSONB
depending on implementation (a Module 3A concern, not this document's).

---

## Gallery

**Purpose:** an ordered set of images/media attached to a Company,
Factory, or Product — the visual evidence layer that complements
Certificates (documents) and Reviews (text).

**Lifecycle:** images added/removed/reordered independently; no complex
state machine.

**Key Attributes:** id, owner type (Company | Factory | Product), owner
id, image url, caption, display order, uploaded_by.

**Relationships:** polymorphic — belongs to one of Company/Factory/
Product (see Section 18 for the tradeoff of polymorphic ownership vs.
three separate join tables).

**Ownership:** owned by whichever entity it's attached to.

**Business Rules:** none load-bearing at Stage 1 beyond standard
content-moderation rules (out of scope for this document — belongs to
Administration/Reviews context tooling).

---

## Document

**Purpose:** an uploaded file (PDF, image) that serves as evidence for a
`Certificate` or general company documentation (e.g. business
registration). Distinct from `Gallery` in that Documents are
evidence/compliance artifacts, not marketing media.

**Lifecycle:** Uploaded → (Active | Archived). May carry its own
review/verification sub-state when attached to a Certificate under
review.

**Key Attributes:** id, owner type (Company | Certificate), owner id,
file url, file type, uploaded_by, uploaded_at.

**Relationships:** one Certificate → one primary Document (the evidence
file); a Company may have general Documents not tied to a specific
Certificate (e.g. business license).

**Ownership:** owned by the Company.

**Business Rules:** Document content is never buyer-visible unless the
associated Certificate is Verified and the Company has chosen to display
it publicly (some evidence may be used for verification without being
published) — a privacy/visibility rule worth carrying into Module 3A's
schema design.

---

## Review

**Purpose:** buyer-authored, moderated feedback about a Company —
the platform's social-proof layer, separate from (and a check on)
self-reported Company data and even from Verification (a company can be
verified and still receive a poor review about service quality).

**Lifecycle:** Submitted → (Published | Flagged | Removed). Flagging can
happen post-publication (Moderator or community-flag driven).

**Key Attributes:** id, company_id (FK), author (FK to User), rating,
title, body, status, moderated_by (nullable), moderated_at (nullable).

**Relationships:** many Review → one Company; many Review → one User
(author).

**Ownership:** authored by the User, moderated by Moderator/Platform
Admin — the Company being reviewed has no edit/delete authority over a
Review about itself (only a flag-for-moderation action) — this asymmetry
is deliberate and load-bearing for review credibility.

**Business Rules:** a User should be limited to one active Review per
Company (prevents review-bombing); a Review requires the author to be
identifiable to Platform Admin even if displayed pseudonymously to other
Buyers (abuse accountability) — see Section 17.

---

## Notification

**Purpose:** a record of a message delivered (or queued for delivery) to
a User, triggered by a domain event from any other context.

**Lifecycle:** Created → (Delivered | Failed) → (Read | Unread, for
in-app notifications).

**Key Attributes:** id, user_id (FK), type, payload (structured, event-
specific), channel (in-app | email | push), status, created_at, read_at.

**Relationships:** many Notification → one User; conceptually triggered
by one `DomainEvent` (Section 7) each, though the triggering event isn't
necessarily a stored FK — implementation detail for Module 3A.

**Ownership:** owned by the recipient User (can mark read, cannot edit
content).

**Business Rules:** notification preferences (which event types a User
wants delivered via which channel) are a User-level setting, not
hardcoded per event type — this belongs to Module 3A's design, flagged
here so it isn't missed.

---

## Saved Supplier

**Purpose:** a private Buyer bookmark of a Company — the simplest
possible "I'm interested in this supplier" signal, intentionally without
any visibility to the bookmarked Company (see Business Rules, Section 8).

**Lifecycle:** Saved → (Removed). No intermediate states.

**Key Attributes:** id, user_id (FK), company_id (FK), collection_id
(nullable FK — see `Collection` below), saved_at, notes (private,
buyer-only free text).

**Relationships:** many SavedSupplier → one User; many SavedSupplier →
one Company; many SavedSupplier → zero-or-one `Collection`.

**Ownership:** exclusively owned by the User — the Company being saved
has no visibility into who saved it or that it was saved at all.

**Business Rules:** privacy is the entire point of this entity (Section
8) — this must not leak into any Company-facing analytics, even
aggregated/anonymized, without a deliberate, separate product decision
(flagged for Module 3A, not decided here).

---

## Collection

**Purpose:** a Buyer-owned, named grouping of Saved Suppliers and/or
Products — lightweight organization (e.g. "Q3 packaging RFQ
candidates"), not a transactional cart or RFQ draft (that's Stage 3, and
even then likely a distinct entity — see Section 13).

**Lifecycle:** Created → (Renamed | Items added/removed) → (Archived |
Deleted).

**Key Attributes:** id, user_id (FK), name, description, created_at.

**Relationships:** one Collection → many `SavedSupplier`; one Collection
→ many saved `Product` references (Products can be collected
independently of saving the whole supplying Company — worth supporting
from Stage 1 so Collections are genuinely useful for comparison
shopping).

**Ownership:** exclusively owned by the User, same privacy stance as
`SavedSupplier`.

**Business Rules:** a Collection is private by default; whether Buyers
can ever share a Collection (e.g. with a colleague) is a Stage 2+
question (Section 10's "Teams" scalability concern) not decided here.

---

## Search Query

**Purpose:** a single executed search — the atomic unit Search Analytics
(and, indirectly, AI) learns from.

**Lifecycle:** ephemeral at the individual-record level (executed, result
returned) but persisted for `SearchHistory`/analytics purposes.

**Key Attributes:** id, user_id (nullable — anonymous search is valid),
raw query text, parsed filters (structured), executed_at, result_count.

**Relationships:** many SearchQuery → zero-or-one User; feeds
`SearchHistory` and platform-level Search Analytics (Section 12).

**Ownership:** owned by the User if authenticated; anonymized/aggregated
if not.

**Business Rules:** see Section 12 for ranking/analytics implications.

---

## Search History

**Purpose:** the User-scoped, retained log of their own past
`SearchQuery` records — distinct from the platform-wide analytics
aggregate, and something the User can view/clear themselves (a privacy-
respecting design choice, not just a technical convenience).

**Key Attributes:** references SearchQuery records scoped to a User,
plus any User-specific retention/visibility settings.

**Relationships:** one User → many SearchHistory entries (effectively a
view over that User's SearchQuery records).

**Ownership:** owned by the User — must be user-clearable (a business
rule worth carrying forward even though not explicitly listed in Section
8, because it's implied by treating Saved Supplier privacy as a design
value).

---

## AI Conversation

**Purpose:** a structured, persisted chat session between a User and the
platform's AI assistant — distinct from a raw prompt/completion log
because a Conversation has continuity (context carries across turns) and
is itself a unit a User might revisit, rename, or delete.

**Lifecycle:** Started → (Active | Idle) → (Archived | Deleted).

**Key Attributes:** id, user_id (FK), title (auto-generated or
user-renamed), started_at, last_message_at, status.

**Relationships:** one AIConversation → many messages/turns (prompt +
response pairs — see Section 11 for the finer-grained `Prompt` shape);
one AIConversation → many `AIRecommendation` (recommendations generated
within that conversation's context).

**Ownership:** exclusively owned by the User.

**Business Rules:** see Section 11 — AI Conversations read from
Company/Product/Verification data but the platform's source-of-truth
entities are never written to by the AI context directly.

---

## AI Recommendation

**Purpose:** a specific, structured output — e.g. "these 5 suppliers
match your query" — generated by the AI domain, distinct from the
free-text conversational response it may accompany, so it can be
individually tracked, rated, and analyzed (did the Buyer act on this
recommendation?).

**Lifecycle:** Generated → (Presented | Acted On | Dismissed).

**Key Attributes:** id, conversation_id (nullable FK — a recommendation
can also be generated outside a conversation, e.g. proactively), user_id
(FK), type (supplier match | product match | risk flag), referenced
entity ids (Company/Product), confidence_score (VO — see Section 6),
generated_at.

**Relationships:** many AIRecommendation → zero-or-one AIConversation;
many AIRecommendation → one User; many AIRecommendation → referenced
Company/Product records (read-only reference, not ownership).

**Ownership:** owned by the platform (AI-generated), scoped to the User
it was generated for.

**Business Rules:** see Section 8 — "AI recommendations are generated
from verified information" — an AIRecommendation should be able to
express *which* underlying data it drew on and that data's verification
status, so a Buyer (and, if disputed, a Platform Admin) can audit why a
recommendation was made.

---

## Audit Log *(existing, extended)*

**Purpose:** Module 2.5 already built this for auth events
(`app.models.audit_log`). This document extends its *scope*, not its
shape: every state transition in Verification, Company ownership
changes, Review moderation, and Certificate status changes should also
write an AuditLog entry, using the same entity, not a parallel one.

**Business Rules:** an AuditLog entry is immutable once written (already
true in the existing implementation) and must capture enough context
(who, what, when, and — critically for Verification — *why*, via a
metadata field) to reconstruct a decision during a dispute.

---

## Session *(existing)*

**Purpose:** already fully designed and implemented in Module 2.5
(`app.models.session`) — a login/device record backing the rotating
refresh-token system. Included in this list only because the brief names
it; no redesign proposed. See
[ADR-0014](../adr/0014-refresh-token-and-session-model.md).

---

## Activity

**Purpose:** a lightweight, User- or Company-scoped feed of recent
actions (e.g. "You saved Acme Manufacturing," "Your certificate was
verified") — the human-readable narrative view that sits alongside the
more structured `AuditLog` (which is compliance/security-oriented) and
`Notification` (which is delivery-oriented). Activity is what populates
an activity-feed UI; it's derived from the same underlying Domain Events
(Section 7) as Notification and AuditLog, not a fourth independent
write path.

**Key Attributes:** id, actor (User or Company), verb, object (referenced
entity), occurred_at.

**Relationships:** derived from Domain Events; read-mostly.

**Ownership:** scoped to whoever the feed is "about" — a User's activity
feed shows their own actions; a Company's activity feed (visible to its
Owner/Admins) shows actions taken on/by the Company.

**Business Rules:** Activity is a *projection*, not a separate source of
truth — if it and AuditLog ever disagree, AuditLog wins (it's the
compliance-grade record). This ordering should be explicit in Module
3A's implementation to avoid two contexts silently drifting.
