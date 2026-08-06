# Naming Conventions

Consistent naming across three languages (TypeScript, Python, Dart) is the
single highest-leverage thing for reducing "where does this live / what do
I call it" friction. When in doubt, match the pattern already used at the
API boundary (`docs/standards/api-response-standard.md`).

## Case conventions by boundary

| Context                                   | Convention              | Example                          |
|--------------------------------------------|--------------------------|-----------------------------------|
| JSON over the wire (HTTP bodies)           | `camelCase`              | `requestId`, `createdAt`          |
| Python internals (variables, functions)    | `snake_case`             | `request_id`, `get_settings()`    |
| Python classes / Pydantic models           | `PascalCase`             | `HealthCheckResponse`             |
| TypeScript variables / functions           | `camelCase`              | `apiFetch`, `isApiSuccess`        |
| TypeScript types / interfaces / components | `PascalCase`             | `ApiResponse`, `StatusBadge`      |
| Dart variables / functions                 | `camelCase`              | `apiBaseUrl`, `fetchHealth()`     |
| Dart classes / widgets                     | `PascalCase`             | `HealthScreen`, `ApiClient`       |
| Constants (all languages)                  | `SCREAMING_SNAKE_CASE` for module-level env/config keys; `camelCase`/`snake_case` const values otherwise | `DATABASE_URL`, `defaultTimeout` |
| Files: TS/TSX                              | `kebab-case.ts(x)`, except Next.js reserved files (`page.tsx`, `layout.tsx`, `route.ts`) | `api-client.ts` |
| Files: Python                              | `snake_case.py`          | `redis_client.py`                 |
| Files: Dart                                | `snake_case.dart`        | `health_screen.dart`              |
| Directories                                | `kebab-case` (TS) / `snake_case` (Python, Dart) | `shared-types`, `db`, `network` |

**Important:** the API deliberately speaks `snake_case` Python internally
but serializes `camelCase`-free, i.e. it does **not** auto-convert casing
today — the current wire format is whatever Pydantic's default alias
produces (`snake_case`, matching the Python field names, e.g.
`uptime_seconds`). The TS/Dart clients read that shape directly (see
`HealthCheckResponse` in `packages/shared-types` vs.
`app/schemas/health.py`) rather than assuming camelCase. If this becomes a
friction point, introduce Pydantic `alias_generator=to_camel` in a
dedicated ADR rather than converting ad hoc per-endpoint.

## Error codes

Machine-readable error codes (`ApiErrorDetail.code`) are always
`SCREAMING_SNAKE_CASE` and namespaced loosely by category:

- `VALIDATION_ERROR` — request payload failed schema validation
- `NOT_FOUND` — requested resource does not exist
- `HTTP_<status>` — generic fallback for unhandled HTTP exceptions
- `NETWORK_ERROR` — client could not reach the server at all
- `INTERNAL_SERVER_ERROR` — unhandled exception on the server

Add new codes as UPPER_SNAKE_CASE nouns/verbs describing the failure, not
the HTTP status alone (`INSUFFICIENT_INVENTORY`, not `ERROR_409`).

## Database

- Tables: plural `snake_case` (`users`, and future tables like
  `suppliers`, `trust_scores`).
- Columns: `snake_case`, foreign keys as `<singular_table>_id`
  (`supplier_id`).
- Alembic revision messages: imperative mood, present tense
  (`"add suppliers table"`, not `"added"` or `"adding"`) — see
  `alembic/versions/..._0001_add_users_table.py` for the pattern.
- Enum-backed columns (e.g. `users.role`): Postgres native enum, values as
  lowercase `snake_case` strings (`admin`, `analyst`, `viewer`), the enum
  type itself named `<column>_<table-singular>` only when ambiguous —
  otherwise just `<column>` (see `user_role` in
  `app/models/user.py`/the Module 2 migration).

## Branches

`<type>/<short-description>`, matching Conventional Commit types:
`feat/health-check-endpoint`, `fix/redis-timeout`, `docs/adr-0006`.
