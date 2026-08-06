# 0017 — Audit Logging

## Status
Accepted

## Context
Structured application logs (structlog, `docs/standards/logging-standard.md`)
exist for operational visibility, but there was no durable, queryable
record of security-relevant events (architecture review weakness #5) —
needed for incident response ("show me every login for this account in
the last 30 days") independent of whatever retention policy the log
aggregator enforces.

## Decision
A dedicated `audit_logs` table (`app.models.audit_log.AuditLog`),
written via `app.services.audit_service.log_event`. Logged events as of
Module 2.5: `user_registered`, `login_succeeded`, `login_failed`,
`login_blocked_lockout`, `logout_all_devices`, `session_revoked`,
`email_verified`, `verification_email_resent`,
`password_reset_requested`, `password_reset_completed`,
`password_changed`, `refresh_token_reuse_detected`. Each row carries
`user_id` (nullable — e.g. a failed login with an unknown email),
`event`, `ip_address`, `user_agent`, `device`, and a JSONB
`event_metadata` field for anything event-specific.

`log_event` commits independently and swallows its own failures (logged
via structlog, not raised) — a failure to write an audit row must never
break the user-facing request it's describing.

## Alternatives considered
- **Reuse structlog's JSON output as the audit trail**: rejected — log
  aggregator retention is an ops decision independent of audit
  requirements, and querying "every login for user X" against a log
  search tool is a worse experience than `SELECT * FROM audit_logs WHERE
  user_id = ...`.
- **Append-only event store / event sourcing**: significantly more
  architecture than this platform's current needs justify; audit_logs is
  a plain table, not a source of truth for replaying state.

## Consequences
- **Known limitation, not hidden**: `log_event` shares the caller's
  request-scoped DB session and calls `commit()` on it. In the current
  code, this is safe because every call site either already committed
  its own preceding work or has nothing left to roll back — but it does
  mean an audit-log commit can flush other pending changes on that
  session earlier than the caller might expect. A fully isolated audit
  write (separate connection/session) would remove this coupling; not
  done in Module 2.5 to avoid a second DB connection per audited request.
  Flagged in Phase 15's Code Quality Review.
- **No retention/partitioning policy yet.** `audit_logs` grows
  unboundedly. Acceptable at current expected scale; partitioning by
  month or an archival job is a deployment-time decision for later.
- No admin UI/endpoint exists to query audit logs yet — they're
  currently operator-accessible only via direct DB query. A `GET
  /admin/audit-logs` endpoint (gated by `require_role(Role.ADMIN)`,
  already available per ADR-0013) is natural future work.
