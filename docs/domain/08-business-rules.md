# 8. Business Rules

Organized by the entity/context they primarily govern. Each rule states
**what**, **why**, and — where relevant — **what it deliberately does
NOT restrict**, per the brief's instruction to avoid hardcoding
unnecessary restrictions.

## Company & membership

**A company must have exactly one Owner at all times.**
*Why:* accountability — every Company needs one unambiguous decision-
maker for high-stakes actions (ownership transfer, account deletion,
verification requests). *Enforcement:* the last Owner cannot leave or be
removed without first transferring ownership to another `CompanyMember`
in the same transaction (see Section 5's Company aggregate boundary).
*Does NOT restrict:* how many Admins/Editors/Viewers a company has (no
upper bound) — only Owner is singular.

**A user may own multiple companies.**
*Why:* real-world sourcing agents, trading companies, and conglomerates
legitimately operate several distinct legal entities on the platform;
forcing one-user-one-company would misrepresent that reality and block
legitimate use cases. *Does NOT restrict:* a user simultaneously being an
Owner of one Company and merely a Viewer-level member of another.

**A company may have multiple factories (or zero).**
*Why:* trading/distribution companies are legitimate Sellers without
owning production sites; multi-site manufacturers are equally legitimate
and shouldn't be modeled as multiple separate Company accounts. *Does NOT
restrict:* factories from being shared/referenced across companies (not
supported at Stage 1 — each Factory belongs to exactly one Company —
this may need revisiting for joint-venture scenarios, flagged in Section
18, not solved here).

**Company ownership transfer is a first-class, audited action.**
*Why:* changes to who has ultimate authority over a Company are
high-stakes and must be reconstructable during a dispute. *Enforcement:*
requires the current Owner's explicit action (or Platform Admin
intervention in a dispute/account-recovery scenario) and writes an
`AuditLog` entry with both the previous and new Owner's identity.

## Products

**Products belong to exactly one company.**
*Why:* unambiguous catalog ownership is required for both
authorization (who can edit this Product) and trust attribution (this
Product's credibility inherits from its Company's verification status).
*Does NOT restrict:* the same physical item type being listed by
multiple different companies (each as their own independent Product
record) — the platform does not attempt cross-company product
deduplication at Stage 1.

**A Product may exist with zero Product Variants.**
*Why:* simple/undifferentiated products shouldn't be forced into
variant modeling they don't need — see Section 3's Product Variant
entry.

## Certificates & Verification

**Certificates expire.**
*Why:* an industrial certification's validity is inherently
time-bound (ISO recertification cycles, test report validity periods) —
treating a Certificate as permanently valid once uploaded would
misrepresent real-world compliance status. *Enforcement:* a Certificate
past its `expiry_date` must not contribute to a Company's displayed trust
signal or Search ranking boost, even if its `verification_status` was
previously `verified` — expiry is checked independent of, and in
addition to, verification status.

**Verification can be revoked.**
*Why:* trust is not a one-time grant — fraud discovered after initial
approval, or a certificate found to have lapsed/been falsified, must be
reflected immediately, not just at the next renewal cycle. *Enforcement:*
`Verification.status` can transition from `approved`/`active` to
`revoked` (not just from `requested`/`under_review` to `rejected`) —
see Section 4.2's ER diagram and Section 7's event flow. Revocation must
propagate to Search's trust-signal index synchronously enough that no
buyer sees a stale "verified" badge (a Stage 1 hard requirement, not a
nice-to-have — this is the platform's core credibility promise).

**Verification tiers exist and are ordered, not binary.**
*Why:* "verified" vs. "not verified" loses valuable signal — a company
with 5 independently-verified ISO certifications and 3 verified
factories represents meaningfully more trust than one with a single
verified business-registration document. *Design (Stage 1):* a small,
platform-defined ordered set of tiers (e.g. Basic → Standard → Premium),
each with defined evidence requirements — the exact tier definitions are
a product/commercial decision outside this document's scope, but the
*shape* (ordered enum, not boolean) is specified here because it affects
the data model.

## Saved Suppliers & Collections

**Saved suppliers are private.**
*Why:* a Buyer's research/shortlisting activity is competitively
sensitive information (revealing it would tell a Seller which Buyers are
evaluating them, and could bias a Seller's behavior toward "watched"
Buyers) — privacy here is a trust-building feature for the Buyer side of
the platform, not an incidental default. *Enforcement:* no API, UI, or
analytics aggregation may expose to a Company (or its members) which
Users have saved it, individually or in any way a Company could
reasonably de-anonymize from aggregate counts at low volume (e.g. "1
buyer saved you" is still identifying) — see Section 17 for the
aggregation-threshold implication this creates for Analytics.

## AI

**AI recommendations are generated from verified information (where
verification exists), and must disclose their basis.**
*Why:* an AI recommendation carries platform credibility — if it
surfaces an unverified company's unverified claims with the same
confidence as verified data, it undermines the entire trust layer the
platform is built around. *Enforcement:* `AIRecommendation` must be able
to express which underlying Company/Product/Certificate data it drew on
and that data's verification status (Section 3's AIRecommendation entry;
Section 11 details the mechanism) — this does not mean the AI can
*never* surface unverified companies (that would make the platform
useless for newly-onboarded Sellers), but it must never *imply* verified
confidence where none exists.

## Reviews

**A user may submit at most one active review per company.**
*Why:* prevents review-bombing and vote-stuffing that would undermine
review credibility (see Section 3's Review entry and Section 17's
"review-bombing" risk). *Does NOT restrict:* a user updating/withdrawing
and later resubmitting a review about the same Company over time (one
*active* review, not one *ever*).

**A company cannot edit or delete reviews about itself.**
*Why:* review integrity requires that the subject of a review has no
unilateral control over it — only a flag-for-moderation action, decided
by an independent Moderator. This is the load-bearing rule that makes
Reviews a credible trust signal at all.

## Cross-cutting

**Every state-changing action on Verification, Company ownership, and
Review moderation writes an AuditLog entry.**
*Why:* these three areas are where disputes are most likely (a rejected
Seller, a contested ownership transfer, a removed review) — an
immutable, reconstructable record is the platform's defense against
"who decided this and why" disputes. *Does NOT restrict:* lower-stakes
actions (e.g. reordering gallery images) from skipping audit-logging —
audit trail cost/volume should scale with actual dispute risk, not apply
uniformly to every write (see Section 17's audit-log-growth
consideration, inherited from Module 2.5's own experience with this
exact tradeoff).

**Platform-level `Role` (Module 2/2.5) and company-scoped `Role`
(this document) are independent and both apply.**
*Why:* a user's platform-level role (`admin`/`analyst`/`viewer` from
ADR-0013) governs platform-operations authority (Platform Admin/Support/
Moderator capability, Section 9); their company-scoped role (`Owner`/
`Admin`/`Editor`/`Viewer` per `CompanyMember`) governs what they can do
*within a specific company's data*. A platform `admin` is not
automatically a `Company Owner` of every company — the two systems
compose, they don't collapse into one. See Section 9's full matrix and
Section 18's recommendation for how Module 3A should implement this
composition cleanly.
