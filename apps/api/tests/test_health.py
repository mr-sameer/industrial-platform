"""
Health endpoint tests. Database/Redis are not mocked here — in CI these
run against the docker-compose postgres/redis services (see
.github/workflows/ci.yml), so a "down" dependency status is a legitimate,
assertable outcome rather than a failure of the test itself.
"""

import pytest


@pytest.mark.asyncio
async def test_health_endpoint_returns_envelope(client):
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["service"] == "industrial-platform-api"
    assert body["data"]["status"] in {"ok", "degraded", "down"}
    assert "database" in body["data"]["dependencies"]
    assert "redis" in body["data"]["dependencies"]
    assert "requestId" not in body  # snake_case at the API boundary; web layer maps it


@pytest.mark.asyncio
async def test_liveness_probe(client):
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_versioned_health_alias(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["success"] is True
