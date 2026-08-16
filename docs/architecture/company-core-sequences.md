# Company Core Sequences — Module 3A

## Company creation → automatic Owner membership

```mermaid
sequenceDiagram
    participant U as User (verified email)
    participant API as POST /companies
    participant Svc as company_service.create_company
    participant DB as Postgres

    U->>API: POST /companies { name, legal_name, ... }
    API->>API: require_verified_email (403 if not verified)
    API->>Svc: create_company(user_id, payload)
    Svc->>DB: generate unique slug (candidate_slugs loop)
    Svc->>DB: INSERT companies (status=active)
    Svc->>DB: INSERT company_members (role=owner, status=active, joined_at=now)
    Note over Svc,DB: One transaction — a Company must never exist<br/>even momentarily without an Owner (docs/domain/05)
    Svc-->>API: Company
    API->>DB: AuditLog: company_created
    API-->>U: 201 { ...CompanyDetail, my_role: "owner" }
```

## Member invite → self-service accept

```mermaid
sequenceDiagram
    participant Admin as Company Admin/Owner
    participant Invitee as Invited user
    participant API as /companies/{id}/members

    Admin->>API: POST /members { user_id, role: "editor" }
    API->>API: require_company_role(ADMIN)
    API-->>Admin: 201 { status: "pending", joined_at: null }

    Note over Invitee: Invitee is now a company_members row,<br/>status=pending — sees it via GET /members

    Invitee->>API: PATCH /members/{member_id} { status: "active" }
    API->>API: is_self_service_accept? (pending -> active, no role change)
    API-->>Invitee: 200 { status: "active", joined_at: <now> }
```

## Ownership transfer (see ADR-0024, ADR-0026)

```mermaid
sequenceDiagram
    participant Owner as Current Owner
    participant API as PATCH /members/{member_id}
    participant Svc as company_service.update_member
    participant DB as Postgres

    Owner->>API: PATCH /members/{target_id} { role: "owner" }
    API->>API: require_company_role(ADMIN) — Owner qualifies
    API->>Svc: update_member(new_role=OWNER)
    Svc->>DB: SELECT current owner for this company
    Svc->>DB: UPDATE current owner SET role='admin'
    Note over Svc,DB: Explicit flush here (ADR-0026) — without it,<br/>SQLAlchemy's executemany batching can run the<br/>promote-UPDATE first, transiently violating the<br/>single-Owner constraint
    Svc->>DB: UPDATE target member SET role='owner', status='active'
    Svc->>DB: COMMIT
    API->>DB: AuditLog: company_ownership_transferred
    API-->>Owner: 200 { role: "owner" }
```

## Guard rails that reject, rather than silently allow

```mermaid
sequenceDiagram
    participant Owner as Current Owner
    participant API as PATCH or DELETE /members/{owner_id}

    Owner->>API: PATCH /members/{self} { role: "admin" }
    API-->>Owner: 409 CANNOT_DEMOTE_LAST_OWNER

    Owner->>API: PATCH /members/{self} { status: "suspended" }
    API-->>Owner: 409 CANNOT_DEMOTE_LAST_OWNER

    Owner->>API: DELETE /members/{self}
    API-->>Owner: 409 CANNOT_REMOVE_OWNER

    Note over Owner,API: All three only succeed after a prior<br/>role: "owner" transfer to someone else
```
