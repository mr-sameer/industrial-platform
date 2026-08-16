# Minimal convenience targets for local development. Intentionally
# small — not a build system, just short names for scripts that
# already exist under apps/api/scripts/.

.PHONY: reset-rate-limit bootstrap-postgres

## Clears ONLY the auth rate-limiter's Redis keys (never a full flush).
## See apps/api/scripts/reset_dev_rate_limits.sh and
## docs/adr/0036-dev-rate-limit-reset-workflow.md for when/why.
reset-rate-limit:
	@cd apps/api && bash scripts/reset_dev_rate_limits.sh

## Creates the local Postgres role/database a bare (non-Docker) run of
## the API expects. See apps/api/scripts/bootstrap_local_postgres.sh.
bootstrap-postgres:
	@cd apps/api && bash scripts/bootstrap_local_postgres.sh
