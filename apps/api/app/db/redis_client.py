"""
Redis connection wiring, used for caching and (in later modules) session/
rate-limit state. A single connection pool is created at import time and
reused across requests via the FastAPI dependency below.
"""

import time
from collections.abc import AsyncGenerator
from typing import Annotated

import redis.asyncio as redis
from fastapi import Depends

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)

_pool: redis.ConnectionPool = redis.ConnectionPool.from_url(
    settings.redis_url, decode_responses=True
)


def get_redis_client() -> redis.Redis:
    return redis.Redis(connection_pool=_pool)


async def reset_pool_for_new_event_loop() -> None:
    """
    Disconnects every connection currently held by the module-level pool.
    In a running server there is exactly one event loop for the process's
    lifetime, so this is never needed there — it exists for the test
    suite, where pytest-asyncio gives each test function its own event
    loop by default: a connection opened under test A's loop cannot be
    reused under test B's loop (asyncio ties sockets/futures to the loop
    that created them). Calling this at the start of every test (see
    tests/conftest.py) forces the *next* command to open a fresh
    connection under whichever loop is currently running.
    """
    await _pool.disconnect()


async def get_redis() -> AsyncGenerator[redis.Redis, None]:
    """FastAPI dependency yielding a Redis client for the request."""
    client = get_redis_client()
    try:
        yield client
    finally:
        await client.aclose()


# Annotated alias — use this in route signatures (`redis_client: RedisClient`)
# instead of `redis_client: redis.Redis = Depends(get_redis)`, which
# ruff/bugbear (B008) flags. Matches app.db.session.DbSession.
RedisClient = Annotated[redis.Redis, Depends(get_redis)]


async def check_redis() -> tuple[str, float | None, str | None]:
    """Returns (status, latency_ms, message)."""
    start = time.perf_counter()
    client = get_redis_client()
    try:
        await client.ping()
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return "ok", latency_ms, None
    except Exception as exc:  # noqa: BLE001 — deliberately broad: this is a probe, not business logic
        logger.warning("redis_health_check_failed", error=str(exc))
        return "down", None, "Redis unreachable"
    finally:
        await client.aclose()
