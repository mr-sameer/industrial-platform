# Company Verification & Industrial Identity Data Model — Module 3B (as implemented)

Purely additive to `docs/architecture/company-core-data-model.md` (Module
3A) — no existing column is altered or dropped. See
`docs/adr/0029-module-3b-verification-and-identity.md` for why several
fields the module brief lists aren't new columns (they reuse Module 3A's
`gst_number`, `description`, and `website`).

```mermaid
erDiagram
    COMPANIES ||--o{ VERIFICATION_DOCUMENTS : "has"
    COMPANIES ||--o{ COMPANY_SOCIAL_LINKS : "has"
    VERIFICATION_DOCUMENTS |o--o| VERIFICATION_DOCUMENTS : "superseded_by (versioning)"

    COMPANIES {
        uuid id PK
        string name "Module 3A"
        string gst_number "Module 3A — reused as GSTIN, see ADR-0029"
        string description "Module 3A — reused as long description"
        string website "Module 3A — reused as the Website social link"
        enum legal_entity_type "private_limited|llp|proprietorship|partnership|public_limited|government|ngo|other"
        enum business_type "manufacturer|trader|both"
        bool export_capable
        string pan
        string cin
        string msme_number
        string iec_number
        string tax_registration
        date business_registration_date
        string logo_url
        string logo_thumbnail_url "256x256, center-cropped"
        string cover_image_url "largest responsive variant"
        string short_description
        string mission
        string vision
        string_array core_values
        string_array capabilities
        string_array manufacturing_expertise
        string_array secondary_industries
        string_array product_categories
        string_array manufacturing_categories
        string_array export_categories
        string naics_sic_code "placeholder"
        string_array ai_tags "placeholder"
    }

    VERIFICATION_DOCUMENTS {
        uuid id PK
        uuid company_id FK
        enum document_type "gst_certificate|msme|iso|ce|bis|factory_license|import_export_code|business_registration|other"
        enum file_type "pdf|image"
        string file_url
        enum status "pending|verified|rejected|expired — only pending is ever set by this module, see ADR-0029"
        uuid uploaded_by FK
        timestamp uploaded_at
        timestamp verified_at "placeholder, always null"
        uuid verified_by FK "placeholder, always null"
        date expiry_date
        int version
        uuid superseded_by_id FK "self-reference, set on replace"
        bool is_deleted
        timestamp deleted_at
        uuid deleted_by FK
    }

    COMPANY_SOCIAL_LINKS {
        uuid id PK
        uuid company_id FK
        enum platform "linkedin|youtube|facebook|instagram|x — NOT website, see ADR-0029"
        string url
    }
```

## The verification score is NOT a column

Deliberately absent from this diagram: there is no
`verification_percentage` or `verification_level` column anywhere.
`docs/adr/0029`'s decision #1 explains why — the score is computed live,
every request, by `app.services.verification_score_service.calculate`,
from the data shown above plus `users.is_email_verified` (via the
company's Owner). This is what makes "no manual editing" a structural
guarantee rather than a policy nobody enforces.

## Constraints enforced at the database level

| Constraint | Enforced by |
|---|---|
| One social link per `(company_id, platform)` | Unique constraint — matches `docs/architecture/company-core-data-model.md`'s style of enforcing business rules in the schema, not just application code |
| `verification_documents.company_id` / `company_social_links.company_id` → `companies.id` | FK, `ON DELETE CASCADE` |
| `verification_documents.superseded_by_id` → `verification_documents.id` | Self-referencing FK, nullable |
