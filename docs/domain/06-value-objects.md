# 6. Value Objects

A value object has no identity of its own — two value objects with the
same field values are interchangeable, unlike two entities with the same
attributes but different ids. Value objects are immutable (a change
produces a new value object, never a mutation) and are defined entirely
by their attributes, with no independent lifecycle or audit trail.

## Why each of these is a value object, not an entity

### Address
**Fields:** street line 1/2, city, region/state, postal code, country
(ISO 3166 code).

**Why VO:** two addresses with identical fields *are* the same address —
there's no meaningful sense in which "123 Main St, Springfield" has an
identity independent of its content. Used by `Company` (headquarters)
and `Factory` (site address).

---

### Phone Number
**Fields:** country code, national number, extension (optional).

**Why VO:** validated and formatted as a unit (e.g. E.164 normalization);
storing/comparing by value, not by a synthetic id, is both simpler and
correct — the business meaning of a phone number is entirely its digits.

---

### Money
**Fields:** amount (fixed-point, never float — see Section 17's
technical-debt note on why), currency code (ISO 4217).

**Why VO:** `Money` must always travel with its currency — a bare number
is meaningless/dangerous in a multi-currency system (Section 10). Two
`Money(100, "USD")` values are identical regardless of which `Product`
or future `Quotation` they're attached to. Not used anywhere in Stage 1's
built entities yet (no pricing is transactional yet), but `ProductVariant`
price range fields should use this shape from day one — see Section 13.

---

### Coordinates
**Fields:** latitude, longitude.

**Why VO:** a geographic point's identity *is* its coordinates — no
separate id needed. Embedded within `Location` (below) and used directly
for map display/distance queries.

---

### Location
**Fields:** `Coordinates`, plus the human-readable city/region/country
(overlaps partially with `Address` but is oriented toward map/search use
— e.g. "near me" queries — rather than mail delivery).

**Why VO, and why distinct from Address:** `Address` is postal/legal in
purpose (used for verification documents, business registration);
`Location` is geospatial/search in purpose (used for map pins, proximity
search/filtering in Section 12). They frequently hold overlapping data
for the same physical place but serve different query patterns —
collapsing them into one type would force every consumer to carry fields
it doesn't need.

---

### Business Hours
**Fields:** a structured weekly schedule (day → open/close time pairs, or
"closed"), timezone.

**Why VO:** a schedule's identity is its content — used by `Company`/
`Factory` for buyer-facing "when can I expect a response" display; not
used for any hard business-rule enforcement at Stage 1 (e.g. no
"messaging only during business hours" restriction).

---

### Email
**Fields:** the address string, validated/normalized (lowercase, format-
checked).

**Why VO:** already implicitly treated this way in Module 2's `User`
entity (validated via Pydantic `EmailStr`) — formalized here as a
reusable shape so `Company` contact emails, `CompanyMember` invitations,
and any future entity needing an email field all validate/normalize
identically rather than each re-implementing the check.

---

### Website
**Fields:** URL string, validated format, optionally a verification flag
(has the platform confirmed this URL actually belongs to the Company? —
a lightweight signal distinct from full `Verification`).

**Why VO:** a URL's identity is its string value; no independent
lifecycle.

---

### Geo Location
Treated as synonymous with `Location` above in this document — the brief
lists both "Coordinates" and "Geo Location" as examples; this model
collapses them into one `Location` VO (which contains `Coordinates`) to
avoid two near-identical types. Flagged explicitly here rather than
silently picking one, since the brief named both.

---

### Social Links
**Fields:** a structured set of (platform, url) pairs (LinkedIn, company
WeChat, industry-specific B2B platform profiles, etc.) — an open/extensible
list rather than a fixed set of named fields (linkedin_url,
facebook_url, ...), so adding a new platform doesn't require a schema
change.

**Why VO:** the set of links, as a whole, describes the Company's social
presence with no independent identity of its own.

---

### Confidence Score *(AI domain — see Section 11)*
**Fields:** a normalized float (0.0–1.0) plus an optional explanation
string (which factors contributed).

**Why VO:** used by `AIRecommendation` and future risk-scoring features;
a bare float would lose the "why" that makes a confidence score
actionable/auditable (Section 8's rule that AI recommendations must be
traceable to verified data).

---

## Value objects NOT included (deliberately)

- **"Rating"** (for `Review`) is treated as a plain constrained integer
  (1–5), not a value object — it has no internal structure worth
  encapsulating beyond a range check.
- **"Tier"** (for `Verification`) is treated as an enum, not a value
  object — see Section 8/10 for the tier definitions; an enum is the
  right shape for a small, closed, platform-defined set of options.

## Summary table

| Value Object | Used by | Immutable fields |
|---|---|---|
| Address | Company, Factory | street, city, region, postal code, country |
| Phone Number | Company, CompanyMember (contact) | country code, number, extension |
| Money | ProductVariant (future pricing), Stage 3 entities | amount, currency |
| Coordinates | Location | latitude, longitude |
| Location | Company, Factory | Coordinates + city/region/country |
| Business Hours | Company, Factory | weekly schedule, timezone |
| Email | User, Company, CompanyMember invitations | validated address string |
| Website | Company | URL, verified flag |
| Social Links | Company | list of (platform, url) |
| Confidence Score | AIRecommendation | float 0.0–1.0, explanation |
