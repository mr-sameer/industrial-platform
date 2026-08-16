# 18. Architecture Review

This section reviews the preceding seventeen sections critically,
following the same discipline Module 2.5's threat model and production
readiness report used: name real weaknesses plainly, don't inflate
scores or completeness, and distinguish "genuinely unresolved" from
"deliberately deferred with a stated reason."

## Weaknesses

### 1. The platform-level `Role` (Module 2/2.5) vs. company-scoped `Role` (this document) overlap is flagged repeatedly but never given a concrete resolution
Sections 3, 8, 9, and 17 all note this reconciliation is needed; none of
them actually specifies it. **Concrete recommendation, made here rather
than deferred again:** rename Module 2's `Role` enum's *concept* (not
necessarily the DB column, to avoid an unnecessary migration) to
`PlatformRole` in all new documentation and code going forward, and
introduce a distinct `CompanyRole` enum (`owner`/`admin`/`editor`/
`viewer`) for `CompanyMember.role`. Never let a single `Role` type serve
both purposes — this is the single highest-priority naming
recommendation in this entire document, precisely because it's the
mistake most likely to actually happen (Section 17).

### 2. `Gallery`/`Document`'s polymorphic ownership is a known, accepted tradeoff — but Section 3 and 4.1 present it more matter-of-factly than the risk warrants
Section 17 does flag it as a database risk, but the entity definition in
Section 3 doesn't warn a first-time reader before they've already
internalized the shape. **Recommendation:** Module 3A should prototype
both approaches (polymorphic vs. three join tables) against a realistic
query — "show me all images across a Company's profile, factories, and
products in one gallery view" — before committing, since that query
pattern is exactly where the two approaches' tradeoffs (one query vs.
three unioned) become concrete rather than theoretical.

### 3. Buyer/Seller as "roles" (per the brief) required a reinterpretation that a reader skimming only Section 9 might miss
Section 9 explains the three-axis reconciliation, but a reader who
jumps straight to the permission matrix table without reading the intro
could reasonably ask "where's the Seller column?" **Recommendation:**
this is a documentation-clarity issue, not a modeling one — already
mitigated by the explicit intro paragraph, but Module 3A's own
permission-check implementation should use `business_type` and
`CompanyRole` as the actual enforced fields, never a literal `"Seller"`
string anywhere in code, to avoid the ambiguity leaking past this
document into implementation.

### 4. Certificate scope ambiguity: company-wide vs. factory-specific certificates aggregate into Verification tier in an unspecified way
Section 3's Certificate entry allows both; Section 8's tier system
doesn't specify how a factory-specific certificate should (or shouldn't)
count toward the parent Company's overall verification tier. **This is a
genuine open question, not resolved here** — flagged rather than
guessed at, since the answer likely depends on commercial/trust-policy
decisions (does a multi-factory company need *every* factory certified
to reach the top tier, or just *some*?) outside this document's
authority to decide.

## Missing entities

### `Message` (Messaging bounded context has no entity)
Section 2 names Messaging as a bounded context ("direct communication
between Buyer and Seller"), but neither the brief's own minimum entity
list nor Section 3 defines a `Message`/`Conversation` entity for it —
this is a genuine gap in the brief itself, inherited into this document,
now named explicitly rather than silently left unfilled. **Recommended
minimal shape for Module 3A:** a `Conversation` entity (buyer_user_id,
seller_company_id, started_at) containing `Message` entities (sender,
body, sent_at, read_at) — deliberately scoped narrower than
`AIConversation` (no AI involvement, no recommendations) since it's a
plain human-to-human channel. Whether this is in Module 3A's actual
scope or a later module is a planning decision, not a modeling one — but
the domain model should not have silently omitted it.

### `NotificationPreference`
Section 3's `Notification` entry notes that per-channel, per-event-type
preferences are "a User-level setting... flagged here so it isn't
missed" — but no entity was actually defined for it. **Recommended
minimal shape:** a `NotificationPreference` entity (user_id, event_type,
channel, enabled) or a simpler JSONB preference bag on `User` — a Module
3A implementation choice, but the entity's *existence* should be
acknowledged in the model, not just implied.

## Over-engineering (things this document may have over-specified for Stage 1)

### `SearchHistory` as a distinct entity
Section 3's own definition admits `SearchHistory` is "effectively a view
over that User's SearchQuery records" — if that's true, it may not need
to be a separate stored entity/table at all, just a query pattern
(`SELECT * FROM search_query WHERE user_id = ?`) with a retention/
clearing policy attached. **Recommendation:** Module 3A should default
to *not* building `SearchHistory` as its own table unless a concrete
requirement emerges that a plain filtered query over `SearchQuery`
can't satisfy (e.g. a materialized/denormalized history view for
performance at scale) — named here as a specific instance of Section
17's "don't pre-pay for flexibility nobody needs" principle.

### `Activity` as a fourth parallel record of "things that happened"
Section 3 already flags that `Activity` must defer to `AuditLog` if they
ever disagree, and is "a projection, not a separate source of truth."
Given `AuditLog` (compliance-grade) and `Notification` (delivery-grade)
already exist, a third read-oriented `Activity` feed may be one entity
too many for Stage 1 specifically — a "recent activity" UI feature could
plausibly be built by querying `AuditLog` directly (filtered to
UI-appropriate event types) rather than maintaining a third synchronized
projection. **Recommendation:** defer building `Activity` as its own
table until/unless `AuditLog`'s query patterns prove insufficient for a
user-facing feed (e.g. because AuditLog's retention/access patterns are
tuned for compliance, not UI responsiveness) — flagged as a legitimate
"maybe don't build this yet" candidate, not a hard removal
recommendation.

## Under-engineering (things that may need more design than this document gave them)

### Search's ranking algorithm (Section 12) is a documented list of factors, not a scoring formula
This is appropriate for a domain model (the exact weighting is a tuning/
product decision, not a domain-modeling one), but Module 3A should not
mistake the *factor list* for a complete *ranking specification* —
real ranking work (weighting, A/B testing, handling ties) remains
substantial and is explicitly out of this document's scope, not
accidentally covered by it.

### Verification tier definitions (Section 8/10) are named as "a small, platform-defined ordered set" without actually naming the tiers or their evidence requirements
This is a deliberate deferral to product/commercial decision-making, but
it means Module 3A cannot actually implement `Verification.tier` from
this document alone — it needs a follow-up decision (likely a short,
separate product document, not a re-opening of this domain model) before
implementation can start on that specific field.

### Review moderation workflow (Section 9's footnote 7 and elsewhere) leaves Moderator's exact authority over Verification (vs. just content) unresolved
Named as an open question in Section 9; repeated here because it's
significant enough to also appear in this review rather than only as a
matrix footnote easy to skim past.

## Simplification opportunities

- **Collapse `Location` and the brief's separately-named "Geo Location"** —
  already done in Section 6, restated here as a concrete example of
  this review practicing what it preaches (simplify where the brief
  named near-duplicates).
- **Consider whether `Permission` (Section 3) needs to be a stored,
  queryable entity at all at Stage 1**, given Section 9's actual matrix
  is enum-and-table-driven, not a dynamic permission-row system. Section
  3 already scoped this cautiously ("not necessarily its own stored
  entity... at Stage 1") — this review confirms that caution was
  correct and recommends Module 3A implement `Permission` as a compiled
  concept (code constants derived from Section 9's matrix), not a
  database table, unless/until Enterprise custom roles (Section 10)
  become a funded requirement.

## Recommended improvements, prioritized

1. **(High)** Resolve the `PlatformRole`/`CompanyRole` naming split
   before any implementation begins (Weakness #1) — this is the one
   recommendation in this document most likely to prevent a real,
   confusing bug if acted on early.
2. **(High)** Decide the `Message` entity's shape and which module owns
   building it (Missing Entity) — currently a silent gap between
   Section 2's context list and Section 3's entity list.
3. **(Medium)** Resolve factory-specific vs. company-wide certificate
   aggregation into Verification tier (Weakness #4) before
   `VerificationService` (Section 14) is implemented — this affects the
   service's core logic, not just an edge case.
4. **(Medium)** Prototype `Gallery`'s polymorphic-ownership query pattern
   before committing to it at scale (Weakness #2).
5. **(Low)** Default to *not* building `SearchHistory` and `Activity` as
   independent tables at Stage 1 (Over-engineering) — revisit only when
   a concrete requirement a simpler approach can't satisfy emerges.

## What this review does NOT find

No fundamental bounded-context boundary (Section 2) or aggregate-root
choice (Section 5) is flagged as wrong — the core shape (Identity →
Company → Verification/Products, with Search/AI as read-only projecting
consumers) held up under this review's scrutiny. The weaknesses found
are real but are refinements and open decisions within a sound
structure, not evidence the structure itself needs rethinking. That
distinction matters for how Module 3A should treat this document: build
on it, resolve the five items above early, and update this document (or
supersede specific sections, following the ADR precedent) as real
implementation experience surfaces anything this review didn't catch.
