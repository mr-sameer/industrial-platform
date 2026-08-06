# 14. Domain Services

A domain service holds business logic that doesn't naturally belong to
any single entity/aggregate — typically because it coordinates across
multiple aggregates, or represents a process rather than a thing. Each
service below is described by **responsibility**, not implementation
(no code, per this document's scope) — Module 3A will decide the actual
class/module shape (this platform's existing pattern, per
`docs/standards/coding-standards.md`, is a thin router → service →
repository layering, which these map onto directly).

## Company Service
**Responsibility:** Company lifecycle orchestration — creation
(including establishing the creator as Owner in the same transaction),
profile updates, member invitation/role changes, ownership transfer, and
enforcing the "exactly one Owner" invariant (Section 8) across all of
these operations. Coordinates the `Company` aggregate (Section 5) and
publishes its domain events (Section 7).

## Product Service
**Responsibility:** Product/Variant catalog management — creation,
publishing/unpublishing, variant management. Coordinates the `Product`
aggregate and publishes `ProductAdded`/`ProductUpdated` events. Enforces
that a Product's `company_id` matches the acting user's authorized
Company context (an authorization concern this service is responsible
for checking, even though the actual permission rules live in Section 9's
matrix / the platform's RBAC dependency, per Module 2.5's
`require_role` pattern).

## Verification Service
**Responsibility:** the Verification state machine — requesting,
reviewing, approving, rejecting, revoking (Section 8's rules), and the
atomic "approve Verification + mark considered Certificates verified"
transaction (Section 5's Verification aggregate boundary). This is the
service most directly responsible for the platform's core value
proposition and should have the platform's most thorough test coverage
when implemented, mirroring the priority Module 2.5 gave to
`session_service.py`'s reuse-detection logic.

## Certificate Service
**Responsibility:** Certificate upload, expiry tracking (a background/
scheduled concern — flagging or auto-transitioning Certificates past
their `expiry_date`, similar in spirit to Module 2.5's
`cleanup_expired_tokens.py` pattern for a different kind of expiry), and
providing the Verification Service with the current evidence set for a
Company.

## Search Service
**Responsibility:** executing `SearchQuery`s against the denormalized
Search index, applying ranking (Section 12's documented factors),
managing `SavedSearch` execution, and consuming domain events from
Company/Product/Verification to keep that index fresh. Does not own
Company/Product/Verification data — reads through Repository Interfaces
(Section 15) like every other consumer.

## AI Service
**Responsibility:** orchestrating `AIConversation` turns — receiving a
Prompt, retrieving relevant Company/Product/Verification context (via
Search Service and/or Repository Interfaces, read-only), calling the
underlying AI/LLM provider (an Anti-Corruption Layer boundary — Section
16), and producing `AIRecommendation`/`RiskScore`/`DocumentSummary`
records with proper source-and-verification-status attribution (Section
11's traceability requirement). Never writes to Company/Product/
Verification.

## Notification Service
**Responsibility:** subscribing to domain events (Section 7) across every
other context and fanning them out to `Notification` records per the
recipient's channel preferences, using the existing `EmailSender`
abstraction pattern from Module 2.5 (ADR-0019) for the email channel —
this service is the natural place a *real* email provider integration
finally gets wired in, closing that Module 2.5 gap as a side effect of
Module 3A's build-out, not a separate effort.

## Audit Service
**Responsibility:** already exists (`app.services.audit_service`,
Module 2.5) for auth events. This document's recommendation: extend its
usage, not its shape — Verification decisions, Company ownership
transfers, and Review moderation actions (Section 8) should call the
same `log_event` function already built, keeping one audit trail instead
of a parallel one per bounded context.

## Authentication Service
**Responsibility:** already fully built (Module 2/2.5). No changes
proposed. Listed here only for completeness of the service inventory the
brief requested.

## Analytics Service
**Responsibility:** aggregating Search Analytics (Section 12), 
Verification funnel metrics, and platform-wide usage reporting — always
read-only over other contexts' data, and responsible for enforcing the
privacy-aggregation-threshold rule (Section 8/17) before any data reaches
a Company-facing or Platform-Admin-facing report.

## Review Service
**Responsibility:** Review submission (enforcing the "one active review
per company, not by the company about itself" rules — Section 8/9),
moderation queue management, and publishing `ReviewSubmitted`/
`ReviewPublished`/`ReviewFlagged` events.

## Service responsibility boundaries (avoiding overlap)

| Question | Answered by |
|---|---|
| "Can this user do X to this Company?" | The permission matrix (Section 9), enforced via the platform's existing RBAC dependency pattern (`require_role`, extended for company-scoped roles) — not re-implemented per-service |
| "Is this Certificate still valid?" | Certificate Service (expiry), Verification Service (verification status) — two different questions, two different services, composed by whichever caller needs both |
| "Should this Company rank higher than that one?" | Search Service exclusively — Verification Service does not compute ranking, it only produces the trust-signal data Search Service consumes |
| "What did the AI base this recommendation on?" | AI Service exclusively — no other service touches `AIRecommendation` |
