# API Response Standard

Every HTTP endpoint in this platform — FastAPI routes and Next.js Route
Handlers alike — returns one of exactly two shapes. Consumers (web, mobile)
never need endpoint-specific parsing logic; they check `success` and
narrow from there.

## Success

```json
{
  "success": true,
  "data": { "...": "endpoint-specific payload" },
  "meta": {
    "request_id": "b3f2c1a0-...",
    "timestamp": "2026-07-28T09:15:32.123Z"
  }
}
```

## Error

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "email must be a valid email address",
    "field": "email",
    "details": null
  },
  "meta": {
    "request_id": "b3f2c1a0-...",
    "timestamp": "2026-07-28T09:15:32.123Z"
  }
}
```

## Field rules

- `success` — boolean discriminator. Always present, always first logically.
- `data` — present only on success. Endpoint-specific shape, itself
  typed (Pydantic model server-side, TS interface client-side).
- `error.code` — machine-readable, `SCREAMING_SNAKE_CASE`, stable across
  releases (treat as part of the public contract — do not rename lightly).
- `error.message` — human-readable, safe to display directly in UI.
  Never leak stack traces, SQL, or internal file paths here.
- `error.field` — present only for field-level validation errors; omitted
  otherwise.
- `error.details` — optional structured context (e.g. the full list of
  validation errors). Treat as debug-only; UIs should not depend on its
  shape.
- `meta.request_id` — echoes the `x-request-id` header (see
  `app/core/middleware.py`), so a user-reported error can be grepped
  straight out of logs.
- `meta.timestamp` — ISO-8601 UTC, server-generated.

## HTTP status codes

The envelope shape is independent of the HTTP status code — always check
`success`, never infer it from the status code alone. That said, status
codes are still meaningful and CI/monitoring depend on them:

| Situation                        | Status | `success` |
|-----------------------------------|--------|-----------|
| Normal success                    | 200    | `true`    |
| Resource created                  | 201    | `true`    |
| Request validation failed         | 422    | `false`   |
| Not found                         | 404    | `false`   |
| Unhandled server exception         | 500    | `false`   |
| Health check: one dependency down | 200    | `true` (see `docs/adr/0007-health-check-design.md`) |

## Client-side usage

**Web** (`apps/web/src/lib/api-client.ts`):

```ts
const result = await apiFetch<HealthCheckResponse>("/health");
if (isApiSuccess(result)) {
  // result.data is typed as HealthCheckResponse
} else {
  // result.error is typed as ApiErrorDetail
}
```

**Mobile** (`apps/mobile/lib/core/network/api_client.dart`):

```dart
final result = await apiClient.getJson('/health');
switch (result) {
  case ApiOk(:final data): // handle success
  case ApiErr(:final code, :final message): // handle error
}
```

## Auth error codes (Module 2)

Introduced alongside `apps/api/app/api/v1/auth.py`:

| Code | HTTP status | Meaning |
|---|---|---|
| `VALIDATION_ERROR` | 422 | Request body failed schema validation (e.g. password too short) |
| `EMAIL_ALREADY_REGISTERED` | 409 | `POST /auth/register` with an email already on file |
| `INVALID_CREDENTIALS` | 401 | `POST /auth/login` with wrong email or password — deliberately identical for both cases (see ADR-0010) to avoid user enumeration |
| `ACCOUNT_INACTIVE` | 403 | Valid credentials/token, but `user.is_active` is `false` |
| `INVALID_REFRESH_TOKEN` | 401 | `POST /auth/refresh` with an expired, malformed, wrong-type, or unknown-user token |
| `HTTP_401` (generic, via `get_current_user`) | 401 | Missing or invalid `Authorization: Bearer` token on a protected route |

Clients should branch on `error.code`, not `error.message` — the message
text is for display, the code is the stable contract.

## What Module 1 does *not* define

Pagination envelopes, bulk-operation partial-success shapes, and
streaming/SSE response formats are intentionally out of scope until a
business feature actually needs one — adding structure speculatively
tends to guess wrong. Propose additions via a new ADR when the need is
concrete.
