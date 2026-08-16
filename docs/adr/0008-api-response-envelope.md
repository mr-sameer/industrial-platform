# 0008 — Standard API Response Envelope

## Status
Accepted

## Context
Three clients (web, mobile, and — indirectly — anything scripting against
the API later) need to handle success and error responses consistently
without per-endpoint bespoke parsing, and error handling needs a
machine-readable code alongside a human-readable message so UIs can
branch on `code` while still having something safe to display.

## Decision
Every endpoint returns `{ success, data, meta }` on success or
`{ success, error, meta }` on failure. Full spec:
`docs/standards/api-response-standard.md`. Implemented as:
- Python: `app/core/responses.py` (`ApiSuccess[T]`, `ApiError`,
  `success_response`, `error_response`).
- TypeScript: `packages/shared-types/src/api-response.ts`
  (`ApiSuccess<T>`, `ApiError`, `ApiResponse<T>`, `isApiSuccess`).
- Dart: `apps/mobile/lib/core/network/api_client.dart`
  (`ApiOk<T>`/`ApiErr<T>` sealed classes).

## Alternatives considered
- **Bare data responses + rely on HTTP status codes only**: rejected —
  loses the ability to attach a stable, greppable error `code` and a
  `request_id` for support/debugging without overloading HTTP status
  semantics.
- **JSON:API / GraphQL-style envelopes**: heavier specs than this
  platform's current needs justify; revisit only if/when the API grows
  complex relationship-graph responses that would benefit from JSON:API's
  compound-document model.

## Consequences
- Global FastAPI exception handlers (`app/main.py`) guarantee *every*
  response — including framework-level 422s and unhandled 500s — matches
  the envelope, so clients never need a fallback "unknown shape" path.
- Casing is **not** unified across the wire boundary yet (see
  `docs/standards/naming-conventions.md` for the current snake_case
  reality) — a deliberate, documented gap rather than an oversight.
