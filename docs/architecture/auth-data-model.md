# Auth Data Model — Module 2.5

```mermaid
erDiagram
    USERS ||--o{ SESSIONS : "has"
    USERS ||--o{ EMAIL_VERIFICATION_TOKENS : "has"
    USERS ||--o{ PASSWORD_RESET_TOKENS : "has"
    USERS ||--o{ PASSWORD_HISTORY : "has"
    USERS ||--o{ AUDIT_LOGS : "generates"
    SESSIONS ||--o{ REFRESH_TOKENS : "rotation history"
    REFRESH_TOKENS |o--o| REFRESH_TOKENS : "replaced_by"

    USERS {
        uuid id PK
        string email UK
        string hashed_password
        string full_name
        enum role
        bool is_active
        bool is_email_verified
        timestamp email_verified_at
        timestamp created_at
    }

    SESSIONS {
        uuid id PK
        uuid user_id FK
        string device_name
        string browser
        string platform
        string user_agent
        string ip_address
        timestamp created_at
        timestamp last_active_at
        timestamp expires_at
        timestamp revoked_at
        enum revoked_reason
    }

    REFRESH_TOKENS {
        uuid id PK
        uuid session_id FK
        string token_hash "sha256, never plaintext"
        timestamp created_at
        timestamp used_at "null = currently valid"
        uuid replaced_by_id FK "self-reference"
    }

    EMAIL_VERIFICATION_TOKENS {
        uuid id PK
        uuid user_id FK
        string token_hash
        timestamp created_at
        timestamp expires_at "24h"
        timestamp used_at
    }

    PASSWORD_RESET_TOKENS {
        uuid id PK
        uuid user_id FK
        string token_hash
        timestamp created_at
        timestamp expires_at "1h"
        timestamp used_at
    }

    PASSWORD_HISTORY {
        uuid id PK
        uuid user_id FK
        string hashed_password
        timestamp created_at
    }

    AUDIT_LOGS {
        uuid id PK
        uuid user_id FK "nullable"
        string event
        string ip_address
        string user_agent
        string device
        jsonb event_metadata
        timestamp created_at
    }
```

**Reading the model:** a `SESSIONS` row is one login/device. Its
`REFRESH_TOKENS` rows are the rotation history for that session — exactly
one has `used_at IS NULL` at any time (the currently valid token); every
prior one points at its replacement via `replaced_by_id`. See
[ADR-0014](../adr/0014-refresh-token-and-session-model.md) for the full
rotation/reuse-detection design this shape supports.
