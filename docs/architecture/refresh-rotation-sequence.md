# Sequence — Refresh Token Rotation & Reuse Detection

Two flows, matching [ADR-0014](../adr/0014-refresh-token-and-session-model.md)
and verified directly by `tests/test_sessions.py`.

## Normal rotation

```mermaid
sequenceDiagram
    participant C as Client (web BFF or mobile)
    participant A as API (/auth/refresh)
    participant DB as Postgres

    C->>A: POST /auth/refresh { refresh_token: T1 }
    A->>DB: SELECT refresh_tokens WHERE id = T1.id
    DB-->>A: row found, used_at IS NULL, hash matches
    A->>DB: UPDATE refresh_tokens SET used_at = now(), replaced_by_id = T2.id WHERE id = T1.id
    A->>DB: INSERT INTO refresh_tokens (id=T2.id, session_id, token_hash=hash(T2))
    A->>DB: UPDATE sessions SET last_active_at = now(), expires_at = now() + 7d
    A-->>C: 200 { access_token, refresh_token: T2, user }
    Note over C,A: T1 is now dead. Only T2 is valid for this session.
```

## Reuse detected (stolen token replayed)

```mermaid
sequenceDiagram
    participant U as Legitimate user
    participant X as Attacker (holds stolen T1)
    participant A as API (/auth/refresh)
    participant DB as Postgres

    U->>A: POST /auth/refresh { refresh_token: T1 }
    A->>DB: T1 valid (used_at IS NULL) → rotate
    A-->>U: 200 { refresh_token: T2 }
    Note over U,A: T1 is now marked used_at = now()

    X->>A: POST /auth/refresh { refresh_token: T1 }
    A->>DB: SELECT refresh_tokens WHERE id = T1.id
    DB-->>A: row found, used_at IS NOT NULL — already rotated away!
    A->>DB: UPDATE sessions SET revoked_at = now(), revoked_reason = 'reuse_detected' WHERE id = session_id
    A-->>X: 401 REFRESH_TOKEN_REUSE_DETECTED

    U->>A: POST /auth/refresh { refresh_token: T2 }
    Note over U,A: T2 was legitimately issued, but its session is now revoked
    A-->>U: 401 INVALID_REFRESH_TOKEN
    Note over U: User must log in again — session is dead for everyone,<br/>attacker included. This is intentional: once reuse is<br/>detected, the session can no longer be trusted at all.
```
