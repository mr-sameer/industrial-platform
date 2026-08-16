# Company Verification Sequences — Module 3B

## Verification score computation (always live, never stored)

```mermaid
sequenceDiagram
    participant Client
    participant API as GET /companies/{id}/verification
    participant Score as VerificationScoreService
    participant DB as Postgres

    Client->>API: GET /companies/{id}/verification
    API->>Score: calculate(company)
    Score->>DB: is owner's email verified?
    Score->>DB: fetch non-deleted documents
    Score->>DB: any social links?
    Score->>Score: evaluate all 13 requirements against<br/>app.core.verification_rules (config, not hardcoded)
    Score-->>API: percentage, level, missing_requirements
    API->>Score: sync_legacy_verification_status(company, score)
    Score->>DB: UPDATE companies.verification_status<br/>(only if it actually changed)
    API-->>Client: 200 { percentage, level, next_level, missing_requirements }

    Note over Client,DB: Nothing here is a stored, editable field —<br/>every response is freshly computed from current data
```

## Document upload → replace (versioning)

```mermaid
sequenceDiagram
    participant Admin as Company Admin/Owner
    participant API as /companies/{id}/documents
    participant Validate as file_validation
    participant Storage as StorageBackend
    participant DB as Postgres

    Admin->>API: POST /documents (multipart: document_type, file)
    API->>Validate: validate_document(bytes)
    Validate-->>API: content_type (or raises FileValidationError → 422)
    API->>Storage: save(key, bytes, content_type)
    Storage-->>API: url
    API->>DB: INSERT verification_documents (status=pending, version=1)
    API-->>Admin: 201 { id, status: "pending", version: 1 }

    Note over Admin,DB: Later — a document needs updating
    Admin->>API: PATCH /documents/{id}/replace (multipart: file)
    API->>Validate: validate_document(new bytes)
    API->>Storage: save(new key, new bytes, content_type)
    API->>DB: INSERT new row (version=2, same document_type)
    API->>DB: UPDATE old row SET is_deleted=true, superseded_by_id=<new id>
    API-->>Admin: 200 { id: <new>, version: 2 }

    Note over Admin,DB: The old file itself is NOT deleted from storage —<br/>soft delete preserves the audit trail (docs/adr/0029)
```

## Logo upload (image processing off the event loop)

```mermaid
sequenceDiagram
    participant Editor as Company Editor+
    participant API as POST /companies/{id}/logo
    participant Validate as file_validation
    participant Threadpool as run_in_threadpool
    participant Storage as StorageBackend

    Editor->>API: POST /logo (multipart: file)
    API->>Validate: validate_image(bytes) — real Pillow decode, not just Content-Type
    Validate-->>API: content_type
    API->>Storage: save(original key, bytes)
    API->>Threadpool: make_thumbnail(bytes) — CPU-bound, never blocks the event loop
    Threadpool-->>API: thumbnail bytes (256x256, center-cropped)
    API->>Storage: save(thumbnail key, thumbnail bytes)
    API->>API: update company.logo_url, logo_thumbnail_url
    API->>Storage: best-effort delete of the PREVIOUS logo/thumbnail (if replacing)
    API-->>Editor: 200 { logo_url, logo_thumbnail_url }
```
