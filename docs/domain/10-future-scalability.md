# 10. Future Scalability

For each concern, this section states **what today's model already
supports without change**, and **what would need to be added** —
distinguishing the two explicitly rather than implying everything is
already handled.

## Multi-company users
**Already supported:** `CompanyMember` is a many-to-many join (Section
3/5) — a User holding memberships in multiple Companies, with different
roles in each, requires no model change. **Would need adding:** a
"switch active company context" UX concept at the application layer
(not a domain-model concern) and possibly a default/last-used company
preference on `User`.

## Multi-factory companies
**Already supported:** `Factory` is a one-to-many child of `Company`
(Section 3/4.1) with no cardinality limit.

## Global suppliers
**Already supported:** `Address`/`Location` value objects (Section 6)
carry a country code from day one; `Company` and `Factory` are not
assumed to be in any single country. **Would need adding:** country-
specific validation rules (e.g. registration-number formats vary by
country) — a Module 3A concern, not a model-shape concern, since the
fields already accommodate arbitrary countries.

## Multiple languages
**Not yet supported, and deliberately not designed in detail here** —
i18n/l10n for entity content (Company descriptions, Product names) needs
either (a) a translations table pattern (entity_id, field, locale,
value) or (b) locale-suffixed columns, and picking between them is an
implementation decision better made with Module 3A's actual i18n
requirements in hand. **What today's model does that helps:** no entity
assumes a single global "name" field is sufficient for search/display in
a way that would be expensive to retrofit — `Company.display_name`,
`Product.name` etc. are already separate fields per entity (not a shared
lookup table) which is compatible with adding translation rows later
per-field.

## Multiple currencies
**Already supported:** the `Money` value object (Section 6) always
carries a currency code — no field in this design stores a bare numeric
price. **Would need adding:** exchange-rate handling and
display-currency preference, both application/Stage-3 concerns (pricing
doesn't exist as a transactional concept until Stage 3 — see Section
13) — but the *shape* is multi-currency-ready today.

## Multiple countries / regional regulations
**Already supported:** `Industry`/`Category` taxonomy is global,
not region-locked, so a supplier's classification doesn't need
region-specific duplication. **Would need adding:** region-specific
compliance/certificate *types* (a certification meaningful in the EU may
not exist or may differ in the US) — `Certificate.certificate_type` is
already a flexible field (not a hardcoded enum limited to one region's
certification schemes), so this is additive data, not a model change.

## Enterprise organizations
**Not yet designed — flagged as a real gap, not solved here.** An
"Enterprise" tier likely needs: (a) custom roles beyond the fixed
Owner/Admin/Editor/Viewer set (Section 3's Role entity notes this
possibility), (b) organization-level billing/seats distinct from
individual Company records, (c) potentially a parent/holding-company
relationship between multiple `Company` records under one Enterprise
account. **Recommendation for Module 3A:** do not build this
speculatively now — the Company aggregate's boundary (Section 5) doesn't
preclude adding a nullable `parent_organization_id` later, so deferring
is safe.

## Teams
**Partially supported via CompanyMember**, but "Teams" as a sub-grouping
*within* a large Company (e.g. a "Procurement Team" vs. a "Quality Team"
both being Company Admins, but scoped to different Product categories)
is not designed. **Would need adding:** a `Team` entity between `User`
and `Company`, with its own scoped permissions — a genuine Stage 2+/
Enterprise feature, consistent with the brief's own stage sequencing
(this is a "Global Industrial Network"-stage concern more than a Stage 1
one).

## SSO
**Not designed here — an Identity-context concern, not a domain-model
one.** SSO (SAML/OIDC) affects *how* a `User` authenticates, not the
`User` entity's business shape — Module 2/2.5's `User` entity already
has an `email` as its natural key, which is SSO-compatible (SSO
typically maps an external identity to an internal user by verified
email). No changes needed to this document's model; flagged as an
Identity-context (not Company-context) future work item.

## API integrations
**Already supported structurally:** every entity has a stable `id`
(UUID) and the domain-event system (Section 7) is designed to be
broker-ready — an external API integration is, architecturally, just
another event consumer/producer. **Would need adding:** API-key/service-
account authentication (an Identity-context extension) and rate-limiting
per integration (Module 2.5 already has the Redis-based rate-limiting
pattern to extend — see `app.core.rate_limit`).

## ERP integrations *(SAP, Oracle, Dynamics, etc.)*
See Section 16 (Anti-Corruption Layer) for the detailed integration
strategy — summarized here: ERP systems will map to this domain via
translation adapters at the boundary, not by this domain model adopting
ERP-native shapes internally.

## Summary table

| Concern | Stage 1 model supports today | Needs future work |
|---|---|---|
| Multi-company users | ✅ Fully | UX only |
| Multi-factory companies | ✅ Fully | — |
| Global suppliers | ✅ Fully | Country-specific validation rules |
| Multiple languages | 🟡 Compatible shape | Translation storage pattern |
| Multiple currencies | ✅ Value-object shape ready | Exchange rates, display prefs (Stage 3) |
| Regional regulations | ✅ Flexible certificate typing | Region-specific compliance data |
| Enterprise organizations | ❌ Not designed | Custom roles, parent-org relationship |
| Teams | 🟡 Partial (CompanyMember) | Dedicated Team entity |
| SSO | ✅ Compatible (Identity context) | Identity-context implementation |
| API integrations | ✅ Event-system ready | Service-account auth |
| ERP integrations | ✅ ACL strategy defined (Section 16) | Per-system adapters |
