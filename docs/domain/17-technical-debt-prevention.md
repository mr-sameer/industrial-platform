# 17. Technical Debt Prevention

Each risk below states the mistake, why it's tempting, and the specific
guardrail this document puts in place against it. This section is
written the same way Module 2.5's threat model was — naming real risks
plainly, not softening them into vague "best practices."

## Database risks

### Risk: polymorphic ownership (`Gallery`, `Document`) becomes a query/integrity nightmare
`Gallery.owner_type`/`owner_id` (Section 3) is convenient to model but
loses referential-integrity enforcement at the database level (a
foreign key can't point at "whichever table `owner_type` says") and
makes every query need a type-switch. **Guardrail:** Section 18 flags
this explicitly as a reviewed tradeoff, not an oversight, and recommends
Module 3A evaluate three separate join tables
(`company_gallery`, `factory_gallery`, `product_gallery`) if the
integrity cost proves worse in practice than the modeling convenience —
decide with real query patterns in hand, not preemptively either way.

### Risk: `Money` stored as floating point
A classic, well-known mistake in any system handling currency. **Guardrail:**
Section 6 explicitly specifies `Money.amount` as fixed-point (e.g.
integer minor-units or a decimal type), never a float — stated now, before
any Stage 3 entity that uses `Money` gets built, specifically so this
mistake has no opportunity to happen "by default."

### Risk: unbounded growth tables with no partitioning/retention plan
`AuditLog` (Module 2.5, already identified in ADR-0017), and now
`SearchQuery`/`SearchHistory` and `Activity` in this document, all grow
without bound. **Guardrail:** named explicitly here (not just in
Module 2.5's scope) so Module 3A's schema design budgets for eventual
partitioning-by-date or archival from the start, rather than treating it
as a to-do only when the table becomes slow.

### Risk: verification/certificate expiry silently not enforced
If "check expiry" is only done at read-time in application code (easy to
forget in a new query path added later), an expired Certificate could
silently keep contributing to trust signal somewhere the check was
missed. **Guardrail:** Section 8's rule is stated as a hard requirement
precisely so Module 3A treats it as a database-level or service-layer
*invariant* (e.g. a computed/materialized "is_currently_valid" derived
consistently in one place — the Certificate Service, Section 14 — rather
than reimplemented ad hoc wherever a certificate's status is checked).

## Performance risks

### Risk: Search becomes a bottleneck if it queries live Company/Product tables directly
**Guardrail:** Section 12's entire design (denormalized index, updated
via events) exists specifically to prevent this — named explicitly as
the reason that design was chosen, not an incidental benefit.

### Risk: `AIRecommendation` generation becomes synchronous and slow on the request path
If AI Service (Section 14) calls an LLM provider synchronously within a
user-facing request, latency will be unacceptable at any real traffic
volume. **Guardrail:** `AIConversation`'s aggregate design (Section 5)
already anticipates async/eventual patterns (a Prompt is appended, a
response arrives later) — Module 3A should treat AI response generation
as inherently async-capable from the first implementation, not bolt
async on after a performance problem.

### Risk: N+1 queries loading Company with all its Products/Certificates/Factories
**Guardrail:** Section 15's Repository Interface convention explicitly
distinguishes narrow methods (`get_by_id`, `search_public_profiles`) from
wide ones (`get_with_members`) — this naming discipline exists so
implementers reach for the narrow method by default and the wide one
only when genuinely needed, rather than one "get company" method that
always loads everything.

## Scalability risks

### Risk: company-scoped `Role` and platform-scoped `Role` (Module 2/2.5) get conflated during implementation
This is the single most likely near-term modeling mistake, because both
are literally named "Role" and both are enums with overlapping-sounding
values conceptually (Admin appears in both). **Guardrail:** Section 8's
explicit reconciliation rule and Section 18's implementation
recommendation both exist specifically to prevent Module 3A from
building one unified `Role` enum that tries to serve both purposes and
inevitably fails at one of them (either platform operations gets
awkwardly shoehorned into company-scoped semantics, or vice versa).

### Risk: "Enterprise" and "Teams" get bolted onto `CompanyMember` under time pressure
**Guardrail:** Section 10 explicitly defers both rather than
half-designing them now — a half-design under time pressure (e.g. adding
a nullable `team_id` to `CompanyMember` without the actual `Team` entity
existing) is worse than clearly deferring, because it creates a
misleading appearance of support without the actual capability.

## Migration risks

### Risk: this domain model gets implemented piecemeal and drifts from this document without anyone updating either
**Guardrail:** this document's own existence as the stated "single source
of truth" (per the brief) is only useful if Module 3A+ treat divergence
as something to reconcile explicitly (update this document, or
explicitly supersede a section the way Module 2.5's ADRs superseded
Module 2's) — the same discipline already established for ADRs
(`docs/adr/README.md`'s "don't edit an accepted ADR's decision, supersede
it" rule) should apply here too.

### Risk: `CompanyMember` role changes and Verification decisions get implemented without audit logging from day one
**Guardrail:** Section 8 states audit-logging as a business rule (not an
implementation nice-to-have) for exactly these two areas, precisely
because retrofitting audit trails after a real dispute has already
happened (with no historical record to reconstruct) is far more costly
than building it in from the first migration.

## Over-abstraction risk (naming the opposite failure mode too)

Not every risk here is "not enough guardrails" — Section 9 and Section
18 both flag the opposite risk explicitly: building a fully dynamic,
database-configurable permission system before Enterprise custom roles
are a proven, funded requirement (Section 10) would be over-engineering
that adds complexity and performance cost (a runtime permission-check
query instead of a compiled enum-based check) for a capability nobody
has asked to actually use yet. Technical debt prevention includes not
pre-paying for flexibility the platform doesn't need — this is addressed
further in Section 18.
