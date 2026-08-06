# 4. Entity Relationship Diagram

Split into four diagrams for readability — a single 26-entity diagram
renders illegibly. Read them as one connected model; entities that
appear in more than one diagram (e.g. `Company`, `User`) are the seams.

## 4.1 — Identity, Company & Product core

```mermaid
erDiagram
    USER ||--o{ COMPANY_MEMBER : "holds membership via"
    COMPANY ||--o{ COMPANY_MEMBER : "has members"
    COMPANY_MEMBER }o--|| ROLE : "assigned"
    COMPANY ||--o{ FACTORY : "operates"
    COMPANY ||--o{ PRODUCT : "catalogs"
    COMPANY ||--o{ GALLERY : "displays"
    FACTORY ||--o{ GALLERY : "displays"
    PRODUCT ||--o{ GALLERY : "displays"
    PRODUCT ||--o{ PRODUCT_VARIANT : "offered as"
    INDUSTRY ||--o{ CATEGORY : "contains"
    INDUSTRY ||--o{ COMPANY : "classifies"
    CATEGORY ||--o{ PRODUCT : "classifies"

    USER {
        uuid id PK
        string email UK
        string full_name
        enum platform_role "admin|analyst|viewer"
        bool is_email_verified
    }
    COMPANY {
        uuid id PK
        string legal_name
        string display_name
        enum business_type "buyer|seller|both"
        uuid industry_id FK
        address headquarters
        enum status
    }
    COMPANY_MEMBER {
        uuid id PK
        uuid user_id FK
        uuid company_id FK
        enum role "owner|admin|editor|viewer"
        enum status "invited|active|removed"
    }
    FACTORY {
        uuid id PK
        uuid company_id FK
        string name
        location site_location
        address site_address
    }
    INDUSTRY {
        uuid id PK
        string name
        string slug
    }
    CATEGORY {
        uuid id PK
        uuid industry_id FK
        string name
        string slug
    }
    PRODUCT {
        uuid id PK
        uuid company_id FK
        uuid category_id FK
        string name
        enum status
    }
    PRODUCT_VARIANT {
        uuid id PK
        uuid product_id FK
        string sku
        jsonb spec_attributes
    }
    GALLERY {
        uuid id PK
        enum owner_type "company|factory|product"
        uuid owner_id FK
        string image_url
        int display_order
    }
```

**Reading notes:** `COMPANY_MEMBER` is the many-to-many join between
`USER` and `COMPANY`, carrying the company-scoped `ROLE`. `GALLERY`'s
`owner_type`/`owner_id` pair is a polymorphic reference (see Section 3's
note and Section 18's critique of this choice) rather than three
separate foreign keys.

## 4.2 — Verification & trust

```mermaid
erDiagram
    COMPANY ||--o{ CERTIFICATE : "holds"
    FACTORY |o--o{ CERTIFICATE : "holds (optional, factory-specific)"
    CERTIFICATE ||--|| DOCUMENT : "evidenced by"
    COMPANY ||--o{ VERIFICATION : "requests"
    VERIFICATION }o--o{ CERTIFICATE : "considers"
    USER ||--o{ VERIFICATION : "requests as"
    USER |o--o{ VERIFICATION : "reviews as (admin)"
    COMPANY ||--o{ DOCUMENT : "uploads (general)"
    VERIFICATION ||--o{ AUDIT_LOG : "records"

    CERTIFICATE {
        uuid id PK
        uuid company_id FK
        uuid factory_id FK "nullable"
        string certificate_type
        string issuing_body
        date issue_date
        date expiry_date
        enum verification_status
    }
    VERIFICATION {
        uuid id PK
        uuid company_id FK
        uuid requested_by FK
        uuid reviewed_by FK "nullable"
        enum tier
        enum status "requested|under_review|approved|rejected|revoked"
        timestamp requested_at
        timestamp decided_at
        timestamp expiry
    }
    DOCUMENT {
        uuid id PK
        enum owner_type "company|certificate"
        uuid owner_id FK
        string file_url
        string file_type
    }
    AUDIT_LOG {
        uuid id PK
        uuid user_id FK "nullable"
        string event
        jsonb event_metadata
        timestamp created_at
    }
```

**Reading notes:** `VERIFICATION }o--o{ CERTIFICATE` is deliberately
many-to-many (a Verification decision may consider multiple Certificates
at once, and a Certificate may be referenced by more than one
Verification event over its life, e.g. initial verification + a later
renewal). `AUDIT_LOG` already exists (Module 2.5) — this diagram shows
its extended relationship to `VERIFICATION`, not a redesign.

## 4.3 — Buyer-side: saving, reviewing, organizing

```mermaid
erDiagram
    USER ||--o{ SAVED_SUPPLIER : "saves"
    COMPANY ||--o{ SAVED_SUPPLIER : "is saved (privately)"
    USER ||--o{ COLLECTION : "owns"
    COLLECTION |o--o{ SAVED_SUPPLIER : "groups"
    COLLECTION |o--o{ PRODUCT : "groups (referenced, not owned)"
    USER ||--o{ REVIEW : "authors"
    COMPANY ||--o{ REVIEW : "is subject of"
    USER |o--o{ REVIEW : "moderates as"
    USER ||--o{ NOTIFICATION : "receives"

    SAVED_SUPPLIER {
        uuid id PK
        uuid user_id FK
        uuid company_id FK
        uuid collection_id FK "nullable"
        string private_notes
    }
    COLLECTION {
        uuid id PK
        uuid user_id FK
        string name
    }
    REVIEW {
        uuid id PK
        uuid company_id FK
        uuid author_id FK
        int rating
        enum status "submitted|published|flagged|removed"
        uuid moderated_by FK "nullable"
    }
    NOTIFICATION {
        uuid id PK
        uuid user_id FK
        string type
        enum channel "in_app|email|push"
        bool read
    }
```

**Reading notes:** `COMPANY ||--o{ SAVED_SUPPLIER` is drawn as a normal
relationship for completeness, but the *business rule* (Section 8) is
that the Company side of this relationship is never queryable by the
Company itself — an enforcement rule, not a schema shape.

## 4.4 — Search & AI

```mermaid
erDiagram
    USER |o--o{ SEARCH_QUERY : "executes (nullable — anonymous OK)"
    SEARCH_QUERY ||--o| SEARCH_HISTORY : "recorded as"
    USER ||--o{ AI_CONVERSATION : "owns"
    AI_CONVERSATION ||--o{ AI_RECOMMENDATION : "generates"
    USER ||--o{ AI_RECOMMENDATION : "receives"
    AI_RECOMMENDATION }o--o{ COMPANY : "references"
    AI_RECOMMENDATION }o--o{ PRODUCT : "references"

    SEARCH_QUERY {
        uuid id PK
        uuid user_id FK "nullable"
        string raw_query
        jsonb parsed_filters
        int result_count
    }
    AI_CONVERSATION {
        uuid id PK
        uuid user_id FK
        string title
        enum status
    }
    AI_RECOMMENDATION {
        uuid id PK
        uuid conversation_id FK "nullable"
        uuid user_id FK
        enum type "supplier_match|product_match|risk_flag"
        float confidence_score
    }
```

**Reading notes:** `AI_RECOMMENDATION`'s references to `COMPANY`/
`PRODUCT` are read-only pointers, never foreign keys the AI context can
cascade-affect — see Section 11's anti-coupling explanation for why this
matters architecturally, not just as a diagram note.

## Cross-diagram entities (appear in more than one)

| Entity | Appears in | Role |
|---|---|---|
| `USER` | 4.1, 4.2, 4.3, 4.4 | The universal actor — every context ultimately traces back to a User |
| `COMPANY` | 4.1, 4.2, 4.3 | The universal subject — every context ultimately traces back to a Company |
| `PRODUCT` | 4.1, 4.3, 4.4 | Referenced by Collections and AI Recommendations without being owned by them |

## Future extensibility notes (not drawn, to avoid clutter)

- **Stage 3 (Procurement):** a future `RFQ` entity attaches to `COMPANY`
  (buyer side) and `PRODUCT`/`PRODUCT_VARIANT` (what's being requested),
  with `QUOTATION` attaching to `RFQ` and `COMPANY` (seller side). See
  Section 13 for the full shape — deliberately not drawn into these
  diagrams since it doesn't exist yet, but the foreign-key attachment
  points above are exactly where it will connect.
- **Stage 2+ (Multi-currency/region):** `Money` value objects (Section 6)
  used in future `PRODUCT_VARIANT.price` and any Stage 3 financial entity
  carry a currency code from day one, so this ER shape doesn't need
  retrofitting when multi-currency support activates.
