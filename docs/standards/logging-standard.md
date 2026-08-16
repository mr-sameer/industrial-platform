# Logging Standard

## Goals

- Structured (JSON in prod) so logs are queryable in an aggregator, not
  just readable in a terminal.
- Correlated: every log line tied to a request can be found via
  `request_id`, matching the `x-request-id` HTTP header and the
  `meta.request_id` field in every API response (see
  `api-response-standard.md`).
- No secrets, tokens, or full request/response bodies logged, ever.

## API (`apps/api`) — structlog

Configured in `app/core/logging.py`, initialized once in the FastAPI
`lifespan` in `app/main.py`.

- **Development:** colorized, human-readable console output
  (`structlog.dev.ConsoleRenderer`).
- **Production / staging:** JSON lines (`structlog.processors.JSONRenderer`)
  — one object per line, ready for Loki/CloudWatch/Datadog ingestion.
- **Access logs:** `RequestContextMiddleware` (`app/core/middleware.py`)
  logs one `request_completed` event per request with `method`, `path`,
  `status_code`, `duration_ms`, `request_id`.
- **Usage in application code:**

  ```python
  from app.core.logging import get_logger
  logger = get_logger(__name__)
  logger.info("supplier_verified", supplier_id=supplier.id, score=score)
  ```

  Prefer structured key-value fields over string interpolation — `logger.info("x", user_id=1)`,
  not `logger.info(f"user {1}")` — so fields stay queryable.

- **Log levels:**
  - `debug` — verbose, local-dev-only detail (disabled by default via
    `LOG_LEVEL=info`).
  - `info` — normal operational events (request completed, service
    started, health check performed).
  - `warning` — recoverable problems (a dependency health check failed but
    the service still degrades gracefully).
  - `error` — unhandled exceptions and anything that needs human attention.

## Web (`apps/web`) — pino

Configured in `src/lib/logger.ts`. Same level/format philosophy as the API:
pretty-printed via `pino-pretty` in development, raw JSON in production.
Use it in Server Components, Route Handlers, and middleware:

```ts
import { logger } from "@/lib/logger";
logger.info({ userId }, "dashboard_viewed");
```

Never import `logger` into a `"use client"` component — server-side
logging only in Module 1; client-side error reporting (Sentry or similar)
is a separate, later concern.

## Mobile (`apps/mobile`) — logger package

`ApiClient` logs network failures via the `logger` package
(`lib/core/network/api_client.dart`). Verbose/debug logging should never
ship to release builds — gate anything beyond warnings behind
`kDebugMode` when adding new log statements.

## What not to log

- Passwords, tokens, API keys, full Authorization headers (reserved for
  Module 2, but the rule starts now).
- Full request/response bodies containing user-submitted data — log
  identifiers (`user_id`, `order_id`), not payloads.
- Anything that would violate data-residency or privacy requirements once
  those are defined for this platform's target industries.
