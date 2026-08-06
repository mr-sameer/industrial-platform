"""
Regression tests for the CSP fix to the Module 2.5 /docs blank-page bug.
See docs/adr/0021-docs-csp-exception.md for the full incident writeup.
"""

import pytest


@pytest.mark.asyncio
async def test_docs_gets_relaxed_csp_allowing_swagger_cdn(client):
    response = await client.get("/docs")
    assert response.status_code == 200
    csp = response.headers["content-security-policy"]
    assert "cdn.jsdelivr.net" in csp
    assert csp != "default-src 'none'; frame-ancestors 'none'"


@pytest.mark.asyncio
async def test_redoc_gets_relaxed_csp_allowing_its_cdn(client):
    response = await client.get("/redoc")
    assert response.status_code == 200
    csp = response.headers["content-security-policy"]
    assert "cdn.jsdelivr.net" in csp


@pytest.mark.asyncio
async def test_regular_api_routes_keep_the_strict_csp(client):
    response = await client.get("/health")
    assert (
        response.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    )


@pytest.mark.asyncio
async def test_auth_routes_keep_the_strict_csp_too(client):
    response = await client.get("/api/v1/auth/me")  # 401, but headers still apply
    assert (
        response.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    )
