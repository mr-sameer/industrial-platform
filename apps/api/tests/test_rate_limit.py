"""
Rate limiting and progressive account-lockout tests. See
docs/adr/0020-rate-limiting-and-security-headers.md and app.core.rate_limit.
Uses small, test-only limits monkeypatched onto settings so tests run fast
without waiting on real 5-minute lockout windows.
"""

import pytest

from app.core.config import get_settings


def _register_payload(email: str) -> dict:
    return {"email": email, "password": "correct-horse-9", "full_name": "Test User"}


@pytest.fixture(autouse=True)
def _tight_limits(monkeypatch: pytest.MonkeyPatch):
    """Shrinks rate limits so tests don't need dozens of requests to trigger them."""
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_login_per_ip", 3)
    monkeypatch.setattr(settings, "rate_limit_register_per_ip", 3)


@pytest.mark.asyncio
async def test_login_is_rate_limited_per_ip(client):
    email = "ratelimit-login@example.com"
    await client.post("/api/v1/auth/register", json=_register_payload(email))

    responses = [
        await client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-pw-1"})
        for _ in range(4)
    ]
    assert responses[-1].status_code == 429
    assert responses[-1].json()["error"]["code"] == "RATE_LIMITED"
    assert "Retry-After" in responses[-1].headers


@pytest.mark.asyncio
async def test_register_is_rate_limited_per_ip(client):
    responses = []
    for i in range(4):
        responses.append(
            await client.post(
                "/api/v1/auth/register", json=_register_payload(f"ratelimit-reg-{i}@example.com")
            )
        )
    assert responses[-1].status_code == 429
    assert responses[-1].json()["error"]["code"] == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_repeated_failed_logins_lock_the_account(client, monkeypatch: pytest.MonkeyPatch):
    """
    Progressive lockout is per-account, independent of the per-IP limit —
    it must trigger well before rate_limit_login_per_ip would, and the
    account stays locked even for the *correct* password.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_login_per_ip", 100)  # isolate from the IP limit

    email = "lockout-test@example.com"
    await client.post("/api/v1/auth/register", json=_register_payload(email))

    # _LOCKOUT_THRESHOLD in app.core.rate_limit is 5.
    for _ in range(5):
        await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "definitely-wrong-1"}
        )

    locked_response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-horse-9"}
    )
    assert locked_response.status_code == 429
    assert locked_response.json()["error"]["code"] == "ACCOUNT_LOCKED"
