"""
Core register/login/refresh/logout/me integration tests, exercised
against a real Postgres + Redis (see conftest.py). Session/reuse-detection,
email verification, and password reset get their own test modules.
"""

import pytest


def _register_payload(email: str = "ada@example.com") -> dict:
    return {"email": email, "password": "correct-horse-9", "full_name": "Ada Lovelace"}


@pytest.mark.asyncio
async def test_register_creates_user_and_returns_tokens(client):
    response = await client.post("/api/v1/auth/register", json=_register_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["user"]["email"] == "ada@example.com"
    assert body["data"]["user"]["role"] == "viewer"
    assert body["data"]["user"]["is_email_verified"] is False
    assert "access_token" in body["data"]
    assert "refresh_token" in body["data"]
    assert "hashed_password" not in body["data"]["user"]


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(client):
    await client.post("/api/v1/auth/register", json=_register_payload())
    response = await client.post("/api/v1/auth/register", json=_register_payload())
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"


@pytest.mark.asyncio
async def test_register_rejects_weak_password(client):
    payload = _register_payload()
    payload["password"] = "short"
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_register_rejects_common_password(client):
    """See docs/adr/0018 — the common-password blacklist runs even when composition rules pass."""
    payload = _register_payload()
    payload["password"] = "password123"  # 11 chars, has letters+digit, but blacklisted
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_login_with_correct_credentials_succeeds(client):
    await client.post("/api/v1/auth/register", json=_register_payload())
    response = await client.post(
        "/api/v1/auth/login", json={"email": "ada@example.com", "password": "correct-horse-9"}
    )
    assert response.status_code == 200
    assert response.json()["data"]["user"]["email"] == "ada@example.com"


@pytest.mark.asyncio
async def test_login_with_wrong_password_fails_generically(client):
    await client.post("/api/v1/auth/register", json=_register_payload())
    response = await client.post(
        "/api/v1/auth/login", json={"email": "ada@example.com", "password": "wrong-password9"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_login_with_unknown_email_returns_same_error_as_wrong_password(client):
    """Guards against user-enumeration: unknown email must not be distinguishable from wrong password."""
    response = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "whatever123"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_me_requires_authentication(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_current_user_with_valid_token(client):
    register_res = await client.post("/api/v1/auth/register", json=_register_payload())
    access_token = register_res.json()["data"]["access_token"]

    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    assert response.json()["data"]["email"] == "ada@example.com"


@pytest.mark.asyncio
async def test_me_rejects_malformed_bearer_token(client):
    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_issues_a_new_token_pair(client):
    register_res = await client.post("/api/v1/auth/register", json=_register_payload())
    old_refresh_token = register_res.json()["data"]["refresh_token"]

    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh_token})
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["access_token"] != register_res.json()["data"]["access_token"]
    assert body["refresh_token"] != old_refresh_token


@pytest.mark.asyncio
async def test_refresh_rejects_a_jwt_access_token_used_as_refresh_token(client):
    """
    As of Module 2.5, refresh tokens are opaque (see docs/adr/0014), not
    JWTs — an access token (which IS a JWT) is simply malformed as an
    opaque token and fails at the decode step, well before any DB lookup.
    """
    register_res = await client.post("/api/v1/auth/register", json=_register_payload())
    access_token = register_res.json()["data"]["access_token"]

    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"


@pytest.mark.asyncio
async def test_logout_revokes_the_session_for_that_device(client):
    register_res = await client.post("/api/v1/auth/register", json=_register_payload())
    refresh_token = register_res.json()["data"]["refresh_token"]

    logout_res = await client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    assert logout_res.status_code == 204

    # The session is now revoked — this exact refresh token must no longer work.
    refresh_res = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_res.status_code == 401


@pytest.mark.asyncio
async def test_login_with_unknown_email_still_calls_verify_password(
    client, monkeypatch: pytest.MonkeyPatch
):
    """
    Regression test for a timing side-channel: the unknown-email path must
    not short-circuit password verification, or its response time becomes
    measurably faster than the wrong-password path — reintroducing email
    enumeration via timing instead of the response body. See
    docs/security/threat-model.md, threat #11, and
    app.services.auth_service.authenticate_user's _DUMMY_HASH.

    Asserted deterministically via a call-count spy rather than wall-clock
    timing, which would be flaky in CI.
    """
    import app.services.auth_service as auth_service_module

    calls: list[tuple[str, str]] = []
    original_verify = auth_service_module.verify_password

    def spy_verify_password(plain: str, hashed: str) -> bool:
        calls.append((plain, hashed))
        return original_verify(plain, hashed)

    monkeypatch.setattr(auth_service_module, "verify_password", spy_verify_password)

    await client.post(
        "/api/v1/auth/login",
        json={"email": "never-registered@example.com", "password": "whatever123"},
    )

    assert len(calls) == 1
    assert calls[0][1] == auth_service_module._DUMMY_HASH
