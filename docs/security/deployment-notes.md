# Deployment Notes — Module 2.5

Checklist for anyone taking this auth system past local development.
Cross-referenced against `docs/security/security-checklist.md`'s ⚠️ items
— this is the "how do I actually close these" companion.

## Must-do before any production deployment

1. **Wire up a real email provider.** `app.services.email_service.LoggingEmailSender`
   only logs verification/reset emails — nobody receives them. Implement
   `EmailSender` (SES, Postmark, Resend, etc. — see ADR-0019) and swap it
   in via `get_email_sender()`. **Without this, email verification and
   password reset are non-functional in any real environment.**
2. **Set `JWT_SECRET_KEY` to a real, unique secret.** The app refuses to
   start in production with the default (`app.core.config`'s
   `_guard_default_jwt_secret_in_production` validator) — generate one
   with `python -c "import secrets; print(secrets.token_urlsafe(64))"`.
3. **Set `API_CORS_ORIGINS` to your real web app origin(s), not a
   wildcard.** The app refuses to start in production with `*` in the
   list (`_guard_wildcard_cors_in_production`).
4. **Set `WEB_APP_SELF_URL`** (web app env) to the real deployed origin —
   used by the Origin-header CSRF check on the refresh/logout BFF routes
   (`apps/web/src/lib/auth/origin-check.ts`). Left at the localhost
   default, it will reject legitimate production requests.
5. **Run `alembic upgrade head`** as an explicit release step — don't
   rely on `docker-compose.yml`'s dev-only auto-migrate command in a real
   deployment pipeline.
6. **Schedule `scripts/cleanup_expired_tokens.py`** to run periodically
   (cron, CI scheduled workflow, or a k8s CronJob) — nothing invokes it
   automatically yet.

## Should-do soon after

7. Decide on and implement audit-log retention/partitioning
   (`audit_logs` grows unboundedly — see ADR-0017).
8. Consider a real common-password blacklist source
   (`app.core.password_policy.COMMON_PASSWORDS` is a small illustrative
   set — see ADR-0018) or a live HIBP k-anonymity check.
9. Consider a Redis-backed access-token/refresh-token revocation list if
   "immediate, guaranteed revocation on demand" (vs. the current
   rotate-and-detect model) becomes a hard requirement — see ADR-0010's
   consequences.

## Environment variables reference

All variables are documented with defaults in the root `.env.example`,
`apps/api/.env.example`, and `apps/web/.env.example`. The ones that
**must** change from their local-dev defaults before production are
marked above (1–4); everything else has a reasonable production default
or is genuinely environment-specific (database/Redis connection strings).

## Observability

- Structured JSON logs in production (`app.core.logging` /
  `apps/web/src/lib/logger.ts`) — ship these to whatever aggregator this
  platform's deployment target uses.
- `audit_logs` table — query directly until an admin UI/endpoint exists
  (natural next step: `GET /admin/audit-logs` gated by
  `require_role(Role.ADMIN)`, already available per ADR-0013).
- No metrics/tracing (Prometheus, OpenTelemetry, etc.) wired up yet —
  out of scope for this auth-hardening module.

## Rollback

Both Module 2 and Module 2.5 migrations (`0001`, `0002`) have verified
`downgrade()` implementations — `alembic downgrade -1` twice returns the
schema to its Module 1 state. Verified in this module's development
process by actually running upgrade → downgrade → upgrade against a real
database, not assumed from reading the code.
