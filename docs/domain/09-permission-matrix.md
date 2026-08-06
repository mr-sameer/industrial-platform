# 9. Permission Matrix

## Reconciling the nine listed roles

The brief lists nine roles: Buyer, Seller, Company Owner, Company Admin,
Company Editor, Company Viewer, Platform Admin, Support, Moderator. Read
literally as nine peers, these overlap awkwardly — "Seller" and "Company
Owner" both seem to describe managing a supplier company. This document
resolves that by treating them as **three different axes**, not nine
peer roles, and says so explicitly rather than silently picking an
interpretation:

1. **Platform-context capability** — `Buyer` and `Seller`. These describe
   *which side of the platform a user is acting on*, derived from
   `Company.business_type` (Section 3) for company-related actions, or
   simply "any authenticated User" for buyer actions that don't require
   company membership at all (searching, saving, reviewing). A single
   User can be a Buyer in one moment (searching) and a Seller's Company
   Admin in another (managing their own supplier profile) — these are
   not mutually exclusive account types.
2. **Company management scope** — `Company Owner`, `Company Admin`,
   `Company Editor`, `Company Viewer`. These are exactly `CompanyMember.role`
   (Section 3) — they only apply to a User acting *within a specific
   Company they belong to*, and only make sense for Seller-side (or
   Both-type) companies managing their own data.
3. **Platform operations authority** — `Platform Admin`, `Support`,
   `Moderator`. These are platform-level roles, analogous to (and,
   per Section 8's reconciliation note, layered on top of) Module
   2/2.5's existing flat `Role` enum — recommended to extend that enum
   rather than create a fully separate system (Section 18).

The matrix below is organized by **resource**, with all nine roles as
columns, so the axis distinction is visible in practice: a row for
"Product: Update" shows `Buyer` as universally ❌ (buyers don't edit
products) and shows the Company-scope roles graduated (Owner/Admin/
Editor: ✅, Viewer: ❌) while Platform Admin retains override capability
for moderation purposes.

## Legend

✅ = full capability · 🟡 = partial/conditional (see footnote) · ❌ = no
capability

## Company

| Action | Buyer | Seller* | Owner | Admin | Editor | Viewer | Platform Admin | Support | Moderator |
|---|---|---|---|---|---|---|---|---|---|
| Read (own company) | — | — | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Read (public profile, any company) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Create (new company) | ✅¹ | ✅¹ | — | — | — | — | ✅ | ❌ | ❌ |
| Update (profile, industry, etc.) | ❌ | — | ✅ | ✅ | 🟡² | ❌ | ✅ | ❌ | ❌ |
| Delete (archive company) | ❌ | — | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| Invite (member) | ❌ | — | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Manage (member roles) | ❌ | — | ✅ | 🟡³ | ❌ | ❌ | ✅ | ❌ | ❌ |
| Export (company data) | ❌ | — | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ |
| Suspend/Reinstate | ❌ | — | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |

\* "Seller" is not a distinct capability row here — see reconciliation
note; a Seller's actual capabilities on their own company are entirely
governed by their `CompanyMember.role` (Owner/Admin/Editor/Viewer).
¹ Any authenticated User can create a Company and becomes its Owner —
Company creation is not gated by an existing role.
² Editor may update product/catalog-adjacent fields but not legal/
identity fields (name, registration number) — see the Products table
below for where Editor's real authority lives.
³ Admin may invite and manage Editor/Viewer members but not promote
another member to Owner or remove the Owner (Section 8's "exactly one
Owner" rule).

## Products & Product Variants

| Action | Buyer | Owner | Admin | Editor | Viewer | Platform Admin | Support | Moderator |
|---|---|---|---|---|---|---|---|---|
| Read (published) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Read (draft/unpublished) | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Create | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Update | ❌ | ✅ | ✅ | ✅ | ❌ | 🟡⁴ | ❌ | ❌ |
| Delete | ❌ | ✅ | ✅ | ❌ | ❌ | ✅⁵ | ❌ | ❌ |
| Export (catalog) | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |

⁴ Platform Admin can update only moderation-relevant fields (e.g.
unpublishing a policy-violating listing), not general product content —
this is a moderation override, not general edit access.
⁵ Platform Admin delete is reserved for policy violations, distinct from
a Seller's own catalog-management delete.

## Certificates & Verification

| Action | Buyer | Owner | Admin | Editor | Viewer | Platform Admin | Support | Moderator |
|---|---|---|---|---|---|---|---|---|
| Read (verification status, public) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Read (certificate documents, if published) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Create (upload certificate) | ❌ | ✅ | ✅ | 🟡⁶ | ❌ | ❌ | ❌ | ❌ |
| Update (replace/renew) | ❌ | ✅ | ✅ | 🟡⁶ | ❌ | ❌ | ❌ | ❌ |
| Delete | ❌ | ✅ | ✅ | ❌ | ❌ | ✅⁵ | ❌ | ❌ |
| Request Verification | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Approve Verification | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | 🟡⁷ |
| Reject Verification | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | 🟡⁷ |
| Revoke Verification | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| Export (verification history) | ❌ | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ |

⁶ Editor's certificate-upload capability is a product/policy decision
this document flags rather than settles — reasonable to allow (an
Editor is often the person actually handling documentation day-to-day)
or reasonable to restrict to Admin+ (verification evidence is
higher-stakes than product content). Recorded as 🟡 pending that
decision, not silently defaulted either way.
⁷ Moderator approve/reject authority for Verification specifically
(as opposed to Review moderation) is a scope decision for Module 3A —
plausible that Verification decisions require Platform Admin exclusively
given their trust-critical nature, while Moderator's authority stays
scoped to content (Reviews, Gallery, Product listings). Flagged, not
decided, here.

## Reviews

| Action | Buyer (author) | Any Company Member | Platform Admin | Support | Moderator |
|---|---|---|---|---|---|
| Read (published) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Create | ✅ | ❌⁸ | ❌ | ❌ | ❌ |
| Update (own review) | ✅⁹ | — | ❌ | ❌ | ❌ |
| Delete (own review) | ✅ | ❌ | ✅ | ❌ | ✅ |
| Flag (for moderation) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Approve/Reject (moderation queue) | ❌ | ❌ | ✅ | ❌ | ✅ |
| Export (review data) | ❌ | 🟡¹⁰ | ✅ | ❌ | ❌ |

⁸ A Company Member cannot review their own company (conflict of
interest) — enforced at the business-rule level (Section 8's "one
review per company" rule implicitly assumes the author isn't the
subject; Module 3A should make this an explicit check, not just an
inherited assumption).
⁹ Subject to the "one active review per company" rule (Section 8) —
updating replaces the existing active review, it doesn't create a
second one.
¹⁰ A Company can export/view its own aggregate rating and review text
(read access, covered in the Read row) but not any reviewer-identifying
metadata beyond what's already publicly displayed.

## User/Membership administration (Platform-level)

| Action | Any User | Platform Admin | Support | Moderator |
|---|---|---|---|---|
| Read (own profile) | ✅ | ✅ | ✅ | ✅ |
| Read (any user, for support purposes) | ❌ | ✅ | ✅ | 🟡¹¹ |
| Update (own profile) | ✅ | — | ❌ | ❌ |
| Update (any user — support action, e.g. unlock account) | ❌ | ✅ | ✅ | ❌ |
| Delete/Deactivate (own account) | ✅ | — | ❌ | ❌ |
| Delete/Deactivate (any user — policy violation) | ❌ | ✅ | ❌ | 🟡¹¹ |
| Manage (platform-level Role assignment) | ❌ | ✅ | ❌ | ❌ |

¹¹ Moderator's user-level authority should be scoped to what's needed
for content moderation (e.g. seeing who authored a flagged review), not
general account administration — a narrower read/deactivate capability
than Support's, recommended for Module 3A to model as a distinct,
smaller permission set rather than reusing Support's.

## Notes on this matrix's completeness

This matrix covers the resources with the clearest, most load-bearing
permission needs (Company, Products, Verification, Reviews, User
administration). It deliberately does not enumerate every entity from
Section 3 (e.g. `Gallery`, `Document`, `Notification`) at the same
granularity — those inherit their permission model from their owning
aggregate (Section 5): Gallery/Document follow whatever entity owns
them (Company/Factory/Product's permission rules apply directly),
Notification is always self-scoped (a User only ever manages their own).
Enumerating every entity at full matrix granularity here would pad this
document without adding decision-relevant information — Section 18
revisits this completeness tradeoff explicitly.
