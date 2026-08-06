# 0006 — Redis for Cache and Ephemeral State

## Status
Accepted

## Context
The platform will need fast, ephemeral state for things Postgres is a
poor fit for: response caching for expensive AI-scoring calls, rate
limiting, and (in Module 2) session/token blocklist state. We want that
mechanism decided now so the health-check and connection-pooling patterns
are established before real features depend on them.

## Decision
Redis 7, accessed via `redis.asyncio` with a single shared connection
pool (`app/db/redis_client.py`), exposed as a FastAPI dependency
(`get_redis`) for request-scoped use.

## Alternatives considered
- **In-process caching (e.g. `functools.lru_cache`)**: fine for
  process-local, rarely-changing data (already used for `get_settings()`),
  but doesn't work across multiple API replicas, which this platform will
  need for horizontal scaling.
- **Memcached**: simpler, but Redis's richer data structures (sorted sets,
  pub/sub) are likely useful for future rate-limiting and real-time
  features, so standardizing on one system now avoids running two caches
  later.

## Consequences
- `docker-compose.yml` runs Redis with `--appendonly yes` for local
  durability across container restarts (not a production durability
  guarantee — revisit persistence strategy before production deployment).
- Health check treats Redis as a monitored-but-non-fatal dependency in
  Module 1 (see ADR-0007) since nothing depends on it yet.
