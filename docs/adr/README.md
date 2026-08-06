# Architecture Decision Records

Each ADR is numbered sequentially and immutable once accepted — if a
decision changes later, write a new ADR that supersedes the old one
(update the old one's status to `Superseded by ADR-00XX`), don't edit
history in place.

| # | Title | Status |
|---|-------|--------|
| [0001](0001-monorepo-strategy.md) | Monorepo strategy (pnpm + Turborepo) | Accepted |
| [0002](0002-nextjs-for-web.md) | Next.js 14 App Router for the web app | Accepted |
| [0003](0003-fastapi-for-backend.md) | FastAPI for the backend service | Accepted |
| [0004](0004-flutter-for-mobile.md) | Flutter for the mobile app | Accepted |
| [0005](0005-postgresql-as-system-of-record.md) | PostgreSQL as the system of record | Accepted |
| [0006](0006-redis-for-cache-and-ephemeral-state.md) | Redis for cache and ephemeral state | Accepted |
| [0007](0007-health-check-design.md) | Health-check endpoint design | Accepted |
| [0008](0008-api-response-envelope.md) | Standard API response envelope | Accepted |
| [0009](0009-auth-deferred-to-module-2.md) | Deferring authentication to Module 2 | Accepted |
| [0010](0010-jwt-authentication-strategy.md) | JWT authentication strategy | Accepted (refresh-token portion superseded by 0014) |
| [0011](0011-password-hashing-bcrypt.md) | Password hashing: bcrypt via passlib | Superseded by 0018 |
| [0012](0012-web-session-strategy.md) | Web session strategy: BFF pattern with httpOnly refresh cookie | Accepted |
| [0013](0013-rbac-model.md) | RBAC model: flat platform-wide roles | Accepted |
| [0014](0014-refresh-token-and-session-model.md) | Refresh token & session model: opaque, rotating, reuse-detected | Accepted — supersedes refresh-token half of 0010 |
| [0015](0015-email-verification.md) | Email verification | Accepted |
| [0016](0016-password-reset.md) | Forgot / reset password | Accepted |
| [0017](0017-audit-logging.md) | Audit logging | Accepted |
| [0018](0018-argon2id-password-hashing.md) | Argon2id password hashing, history, strength rules | Accepted — supersedes 0011 |
| [0019](0019-email-sending-stub.md) | Email sending: stub implementation | Accepted |
| [0020](0020-rate-limiting-and-security-headers.md) | Rate limiting, account lockout, security headers | Accepted |
| [0021](0021-docs-csp-exception.md) | Scoped CSP exception for /docs and /redoc | Accepted |
| [0022](0022-company-role-naming.md) | CompanyRole as a distinct enum from the platform-level Role | Accepted |
| [0023](0023-module-3a-scope-simplifications.md) | Module 3A scope simplifications (industry as string, verification placeholder) | Accepted |
| [0024](0024-ownership-transfer-mechanism.md) | Ownership transfer via PATCH member role=owner | Accepted |
| [0025](0025-enum-values-callable-bugfix.md) | Fix: SQLAlchemy Enum columns must set values_callable | Accepted — critical bugfix |
| [0026](0026-ownership-transfer-flush-ordering.md) | Explicit flush ordering in ownership transfer | Accepted — bugfix |
| [0027](0027-logger-transport-crash-fix.md) | Fix: remove pino's transport option to stop the pino-pretty crash | Superseded by 0028 |
| [0028](0028-docker-dev-script-must-not-require-pino-pretty.md) | Docker's dev script must not require pino-pretty | Accepted — critical bugfix |
