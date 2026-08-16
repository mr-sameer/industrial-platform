#!/usr/bin/env bash
#
# Bootstraps the local PostgreSQL role and database this app expects
# for bare local development (uvicorn run directly, not via Docker).
#
# Root cause this fixes: Docker Compose's official postgres image
# auto-creates its role/database from POSTGRES_USER/POSTGRES_PASSWORD/
# POSTGRES_DB on first container start — but a bare local Postgres
# install (apt/Homebrew/etc.) has no such automatic bootstrapping.
# Nothing in this repo ever created that role for a non-Docker setup;
# this script is that missing step, made explicit and repeatable
# instead of a manual, undocumented one-off.
#
# Idempotent — safe to run more than once. Reads credentials from
# environment variables (same names, same defaults as .env.example) so
# nothing here is a new hardcoded secret; it just performs, for real,
# the role/database creation that value already implied but that
# nothing previously carried out.
#
# Usage:
#   ./scripts/bootstrap_local_postgres.sh
#   POSTGRES_USER=myuser POSTGRES_PASSWORD=mypass ./scripts/bootstrap_local_postgres.sh
#
# Connects via the local Unix socket as the OS `postgres` user (peer
# authentication) — the same method every other setup step in this
# project already relies on. A TCP connection with `-h` hit password
# authentication instead and hung waiting for input in a non-
# interactive shell — found by actually running this script, not
# assumed. Only used for a local target; a remote POSTGRES_HOST needs
# its own connection setup (a .pgpass file, etc.) this script doesn't
# manage.

set -euo pipefail

POSTGRES_USER="${POSTGRES_USER:-platform_user}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-change_me_locally}"
POSTGRES_DB="${POSTGRES_DB:-industrial_platform}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"

echo "Bootstrapping local Postgres for bare (non-Docker) development..."
echo "  role:     ${POSTGRES_USER}"
echo "  database: ${POSTGRES_DB}"
echo "  host:     ${POSTGRES_HOST}:${POSTGRES_PORT}"

IS_LOCAL=false
if [ "${POSTGRES_HOST}" = "localhost" ] || [ "${POSTGRES_HOST}" = "127.0.0.1" ]; then
  IS_LOCAL=true
fi

USE_SUDO=false
if [ "${IS_LOCAL}" = true ] && command -v sudo >/dev/null 2>&1 && sudo -n -u postgres true 2>/dev/null; then
  USE_SUDO=true
fi

run_psql() {
  # $1 = sql, $2 = optional flags (e.g. -tAc for a single scalar result)
  local sql="$1"
  local flags="${2:--c}"
  if [ "${IS_LOCAL}" = true ]; then
    if [ "${USE_SUDO}" = true ]; then
      sudo -u postgres psql "${flags}" "${sql}"
    else
      su postgres -c "psql ${flags} \"${sql}\""
    fi
  else
    PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U postgres "${flags}" "${sql}"
  fi
}

ROLE_EXISTS=$(run_psql "SELECT 1 FROM pg_roles WHERE rolname = '${POSTGRES_USER}'" "-tAc" | tr -d '[:space:]')

# Printed unconditionally, before any create/skip decision — this is
# the actual answer to "which Postgres instance is bootstrap touching":
# data_directory is a stronger disambiguator than host/port alone,
# since two different local installations (e.g. a native apt/Homebrew
# Postgres AND a separate Docker Postgres, both possibly reachable on
# localhost:5432 depending on port mapping) will always have different
# data directories even if their version and port happen to match.
# Compare this directly against what the running app itself prints at
# startup (app.main._verify_database_connection) to confirm or rule
# out "bootstrap and the app are hitting different servers" — the
# actual question this exists to answer, not just assert.
INSTANCE_INFO=$(run_psql "SELECT version(), current_setting('data_directory'), current_setting('port')" "-tAc")
echo ""
echo "Instance bootstrap is actually connected to:"
echo "  ${INSTANCE_INFO}" | sed 's/|/\n  port: /'
echo ""

if [ "${ROLE_EXISTS}" = "1" ]; then
  echo "Role '${POSTGRES_USER}' already exists — skipping."
else
  run_psql "CREATE ROLE ${POSTGRES_USER} WITH LOGIN SUPERUSER PASSWORD '${POSTGRES_PASSWORD}';"
  echo "Created role '${POSTGRES_USER}'."
fi

DB_EXISTS=$(run_psql "SELECT 1 FROM pg_database WHERE datname = '${POSTGRES_DB}'" "-tAc" | tr -d '[:space:]')
if [ "${DB_EXISTS}" = "1" ]; then
  echo "Database '${POSTGRES_DB}' already exists — skipping."
else
  run_psql "CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER};"
  echo "Created database '${POSTGRES_DB}'."
fi

echo "Done. Run 'alembic upgrade head' (from apps/api) next to apply migrations."
