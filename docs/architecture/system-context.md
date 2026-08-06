# System Context — Module 1

Scope: infrastructure and app shells only. No authentication, no domain
features (asset tracking, procurement, trust scoring) exist yet — those
are represented as "future modules" for orientation only.

```mermaid
C4Context
    title System Context — Industrial Intelligence Platform (Module 1 scope)

    Person(user, "Platform User", "Analyst / operations user (web or mobile)")

    System_Boundary(platform, "Industrial Intelligence Platform") {
        System(web, "Web App", "Next.js 14 — dashboards, reports")
        System(mobile, "Mobile App", "Flutter — field/on-the-go access")
        System(api, "API", "FastAPI — business logic, data access")
        SystemDb(postgres, "PostgreSQL", "System of record")
        SystemDb(redis, "Redis", "Cache / ephemeral state")
    }

    System_Ext(future_ai, "AI/ML Services", "Future module — not implemented yet")
    System_Ext(future_auth, "Auth Provider", "Future module — not implemented yet")

    Rel(user, web, "Uses", "HTTPS")
    Rel(user, mobile, "Uses", "HTTPS")
    Rel(web, api, "Calls", "JSON/HTTPS")
    Rel(mobile, api, "Calls", "JSON/HTTPS")
    Rel(api, postgres, "Reads/writes", "asyncpg / SQL")
    Rel(api, redis, "Reads/writes", "Redis protocol")
    Rel(api, future_ai, "Will call", "planned")
    Rel(web, future_auth, "Will call", "planned")
```
