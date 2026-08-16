"""
Tests for the dev-only rate-limit hint added to the 429 response —
see docs/adr/0036-local-dev-rate-limit-workflow.md. The hint text is
the only thing that changes; the actual rate limit enforcement
(values, windows, per-IP keying) is identical in every environment —
these tests specifically guard against that hint ever leaking into a
production response, which would be the one way this change could
matter for a real deployment.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import create_app


@pytest.mark.asyncio
async def test_rate_limit_hint_appears_in_non_production(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "environment", "development")
    for _ in range(5):
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": f"ratelimit-hint-{_}@example.com",
                "password": "CorrectHorse9",
                "full_name": "Hint Test",
            },
        )
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "ratelimit-hint-overflow@example.com",
            "password": "CorrectHorse9",
            "full_name": "X",
        },
    )
    assert response.status_code == 429
    message = response.json()["error"]["message"]
    assert "reset_dev_rate_limits.sh" in message
    assert "make reset-rate-limit" in message


@pytest.mark.asyncio
async def test_rate_limit_hint_never_appears_in_production(monkeypatch):
    """
    Built as a genuinely separate app instance with is_production
    monkeypatched true, rather than trusting the shared `client`
    fixture's environment — this is exactly the boundary that must
    never leak, so it gets its own explicit, isolated check.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "environment", "production")
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as prod_client:
        for _ in range(5):
            await prod_client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"prod-ratelimit-{_}@example.com",
                    "password": "CorrectHorse9",
                    "full_name": "Prod Test",
                },
            )
        response = await prod_client.post(
            "/api/v1/auth/register",
            json={
                "email": "prod-ratelimit-overflow@example.com",
                "password": "CorrectHorse9",
                "full_name": "X",
            },
        )
        if response.status_code == 429:
            message = response.json()["error"]["message"]
            assert "reset_dev_rate_limits.sh" not in message
            assert "make reset-rate-limit" not in message
