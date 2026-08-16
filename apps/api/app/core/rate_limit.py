"""
Redis-backed rate limiting for auth endpoints. Fixed-window counters
(simple, sufficient for this stage — see docs/security/module-2.5-architecture-review.md's
"Technical Debt" section for why a sliding-window/leaky-bucket algorithm
was not chosen here) plus a progressive account-lockout mechanism for
repeated failed logins.
"""

from dataclasses import dataclass

import redis.asyncio as redis

_LOCKOUT_THRESHOLD = 5  # failed attempts before the first lockout kicks in
_LOCKOUT_BASE_SECONDS = 30  # first lockout duration; doubles per additional strike, capped below
_LOCKOUT_MAX_SECONDS = 15 * 60


@dataclass
class RateLimitExceededError(Exception):
    retry_after_seconds: int


async def check_rate_limit(
    client: redis.Redis, key: str, max_attempts: int, window_seconds: int
) -> None:
    """
    Fixed-window limiter: increments a counter keyed by `key`, expiring
    after `window_seconds`. Raises RateLimitExceededError once `max_attempts`
    is exceeded within the current window.
    """
    current = await client.incr(key)
    if current == 1:
        await client.expire(key, window_seconds)
    if current > max_attempts:
        ttl = await client.ttl(key)
        raise RateLimitExceededError(retry_after_seconds=max(ttl, 1))


def _lockout_key(email: str) -> str:
    return f"auth:lockout:{email.lower()}"


def _strikes_key(email: str) -> str:
    return f"auth:login_strikes:{email.lower()}"


async def is_account_locked(client: redis.Redis, email: str) -> int:
    """Returns remaining lockout seconds (0 if not locked)."""
    ttl = await client.ttl(_lockout_key(email))
    return max(int(ttl), 0)


async def register_failed_login(client: redis.Redis, email: str) -> None:
    """
    Tracks failed logins per account and applies a progressively longer
    lockout once the failure threshold is crossed, independent of the
    per-IP rate limit (an attacker rotating IPs still hits this).
    """
    strikes_key = _strikes_key(email)
    strikes = await client.incr(strikes_key)
    if strikes == 1:
        await client.expire(strikes_key, 24 * 60 * 60)  # forget strikes after a day of no failures

    if strikes >= _LOCKOUT_THRESHOLD:
        extra_strikes = strikes - _LOCKOUT_THRESHOLD
        lockout_seconds = min(_LOCKOUT_BASE_SECONDS * (2**extra_strikes), _LOCKOUT_MAX_SECONDS)
        await client.set(_lockout_key(email), "1", ex=lockout_seconds)


async def clear_failed_logins(client: redis.Redis, email: str) -> None:
    await client.delete(_strikes_key(email), _lockout_key(email))
