#!/usr/bin/env bash
#
# Clears ONLY the authentication rate-limiter's Redis keys — never a
# blanket FLUSHALL/FLUSHDB. This is a development-only escape hatch,
# not a fix to the rate limiter itself: the limits (5 registrations/
# hour/IP, 10 logins/minute/IP, etc.) are unchanged in every
# environment, including this one. See docs/adr/0036 for the full
# root-cause writeup this script exists to work around.
#
# When to use this: in pure local development (bare `next dev`, no
# reverse proxy or CDN in front of it), every request the Next.js BFF
# makes to FastAPI is indistinguishable from every other — there is no
# X-Forwarded-For to forward because nothing sits in front of Next.js
# to have set one. A normal afternoon of manually testing the
# register/login flow will exhaust the real, unweakened rate limits
# faster than a real deployment (behind a real proxy, where distinct
# users get distinct IPs) ever would. This is expected, not a bug —
# and this script is the intended way to keep developing without
# touching the limiter's actual configuration.
#
# Never run this against a real deployment's Redis — it refuses to run
# if ENVIRONMENT=production is set, as a safety net, but the stronger
# guarantee is operational: point REDIS_URL at a real environment and
# this becomes a real security-relevant action, not a dev convenience.
#
# Usage (from apps/api):
#   bash scripts/reset_dev_rate_limits.sh
#
# Or via the Makefile target, from the repo root:
#   make reset-rate-limit

set -euo pipefail

ENVIRONMENT="${ENVIRONMENT:-development}"
if [ "${ENVIRONMENT}" = "production" ]; then
  echo "Refusing to run: ENVIRONMENT=production." >&2
  echo "This script is a local-development convenience only — it must never" >&2
  echo "touch a real deployment's rate-limit state." >&2
  exit 1
fi

REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_DB="${REDIS_DB:-0}"

# Every Redis key namespace the auth rate limiter / lockout mechanism
# uses — confirmed directly against app/api/v1/auth.py and
# app/core/rate_limit.py, not guessed. If a future endpoint adds a new
# rate-limited namespace outside these three prefixes, add it here
# explicitly; this script intentionally never uses a bare `redis-cli
# FLUSHALL`/`FLUSHDB`, or an unscoped `KEYS *`, so nothing outside
# these three prefixes is ever at risk from running it.
PATTERNS=("ratelimit:*" "auth:lockout:*" "auth:login_strikes:*")

TOTAL_DELETED=0
for pattern in "${PATTERNS[@]}"; do
  # SCAN, not KEYS, in case this is ever pointed at a Redis instance
  # with enough keys for KEYS's O(N) blocking behavior to matter — not
  # a concern for a dev Redis today, but costs nothing to do correctly.
  keys=$(redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" -n "${REDIS_DB}" --scan --pattern "${pattern}")
  if [ -n "${keys}" ]; then
    count=$(echo "${keys}" | wc -l)
    echo "${keys}" | xargs redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" -n "${REDIS_DB}" DEL > /dev/null
    echo "Cleared ${count} key(s) matching '${pattern}'"
    TOTAL_DELETED=$((TOTAL_DELETED + count))
  else
    echo "No keys matching '${pattern}' — nothing to clear"
  fi
done

echo ""
echo "Done — cleared ${TOTAL_DELETED} rate-limit key(s) total."
echo "Nothing else in Redis was touched (no FLUSHALL/FLUSHDB was run)."
