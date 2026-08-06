# Request Lifecycle — Health Check (Module 1 reference flow)

```mermaid
sequenceDiagram
    participant U as User
    participant W as Web (/health page)
    participant A as API (/health)
    participant P as PostgreSQL
    participant R as Redis

    U->>W: GET /health
    W->>A: GET /health (apiFetch)
    activate A
    A->>P: SELECT 1 (check_database)
    P-->>A: ok / latency_ms
    A->>R: PING (check_redis)
    R-->>A: ok / latency_ms
    A-->>W: 200 { success, data: HealthCheckResponse, meta }
    deactivate A
    W-->>U: Rendered status badges (web, api, database, redis)
```

Every hop above already exists in code:
`apps/web/src/app/health/page.tsx` → `apps/web/src/lib/api-client.ts` →
`apps/api/app/api/v1/health.py` → `apps/api/app/db/health.py` /
`apps/api/app/db/redis_client.py`.
