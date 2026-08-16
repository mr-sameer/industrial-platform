"""
Regression tests for the CSP fix to the Module 2.5 /docs blank-page bug.
See docs/adr/0021-docs-csp-exception.md for the full incident writeup.
"""

import pytest


@pytest.mark.asyncio
async def test_docs_gets_relaxed_csp_with_no_external_origins(client):
    """
    Was test_docs_gets_relaxed_csp_allowing_swagger_cdn — renamed and
    rewritten. The old assertion (cdn.jsdelivr.net present in the CSP)
    encoded the exact assumption that caused a real bug: this app's
    /docs used to depend on that CDN, which returns a real 403 from
    this sandbox's network — the CSP allowed it, but the CDN itself was
    unreachable, so Swagger UI never rendered despite /docs returning
    200. Fixed by self-hosting every asset /docs needs
    (docs/adr/0034-self-hosted-api-docs.md) — the correct assertion now
    is that NO external origin appears in the CSP at all.
    """
    response = await client.get("/docs")
    assert response.status_code == 200
    csp = response.headers["content-security-policy"]
    assert "cdn.jsdelivr.net" not in csp
    assert "http://" not in csp
    assert "https://" not in csp
    assert csp != "default-src 'none'; frame-ancestors 'none'"


@pytest.mark.asyncio
async def test_redoc_gets_relaxed_csp_with_no_external_origins(client):
    """Was test_redoc_gets_relaxed_csp_allowing_its_cdn — same reasoning as above."""
    response = await client.get("/redoc")
    assert response.status_code == 200
    csp = response.headers["content-security-policy"]
    assert "cdn.jsdelivr.net" not in csp
    assert "http://" not in csp
    assert "https://" not in csp


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


@pytest.mark.asyncio
async def test_swagger_ui_assets_are_served_locally(client):
    """
    Regression test for the actual bug this ADR fixes: /docs returning
    200 was never sufficient — the assets the page depends on to
    actually render must be servable too. If these ever 404 (e.g. the
    vendored files under app/static/swagger-ui/ get accidentally
    deleted), /docs silently breaks again exactly as it did before.
    """
    js = await client.get("/docs/assets/swagger-ui-bundle.js")
    css = await client.get("/docs/assets/swagger-ui.css")
    assert js.status_code == 200
    assert css.status_code == 200


@pytest.mark.asyncio
async def test_redoc_assets_are_served_locally(client):
    js = await client.get("/redoc/assets/redoc.standalone.js")
    assert js.status_code == 200


@pytest.mark.asyncio
async def test_docs_csp_allows_inline_script_and_worker(client):
    """
    Regression test for the second real bug: FastAPI's Swagger UI HTML
    embeds an inline <script> that actually initializes the UI, and
    ReDoc spins up a blob: Web Worker — script-src 'self' alone (no
    'unsafe-inline') blocked the former; no worker-src directive
    (falling back to script-src) blocked the latter. Both silently
    produced a blank/broken page despite /docs and /redoc returning 200.
    """
    response = await client.get("/docs")
    csp = response.headers["content-security-policy"]
    assert "'unsafe-inline'" in csp
    assert "worker-src 'self' blob:" in csp
