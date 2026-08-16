"""
Forgot/reset password tests. Like email verification, the token is
extracted directly from the database rather than parsed from a stubbed
email — see tests/test_email_verification.py's docstring for the same
rationale.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.opaque_tokens import encode_opaque_token, hash_opaque_secret, new_opaque_secret
from app.db.session import AsyncSessionLocal
from app.models.password_reset_token import PasswordResetToken


def _register_payload(email: str = "marie@example.com") -> dict:
    return {"email": email, "password": "correct-horse-9", "full_name": "Marie Curie"}


async def _issue_known_reset_token(user_id) -> str:
    secret = new_opaque_secret()
    async with AsyncSessionLocal() as db:
        row = PasswordResetToken(
            user_id=user_id,
            token_hash=hash_opaque_secret(secret),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return encode_opaque_token(row.id, secret)


@pytest.mark.asyncio
async def test_forgot_password_returns_204_for_known_and_unknown_email_alike(client):
    """Must not reveal account existence — see docs/adr/0019."""
    await client.post("/api/v1/auth/register", json=_register_payload())

    known = await client.post("/api/v1/auth/forgot-password", json={"email": "marie@example.com"})
    unknown = await client.post(
        "/api/v1/auth/forgot-password", json={"email": "nobody@example.com"}
    )
    assert known.status_code == 204
    assert unknown.status_code == 204


@pytest.mark.asyncio
async def test_reset_password_with_valid_token_changes_password_and_allows_new_login(client):
    register_res = await client.post("/api/v1/auth/register", json=_register_payload())
    user_id = register_res.json()["data"]["user"]["id"]

    token = await _issue_known_reset_token(user_id)
    response = await client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": "brand-new-pw-1"}
    )
    assert response.status_code == 204

    old_password_login = await client.post(
        "/api/v1/auth/login", json={"email": "marie@example.com", "password": "correct-horse-9"}
    )
    assert old_password_login.status_code == 401

    new_password_login = await client.post(
        "/api/v1/auth/login", json={"email": "marie@example.com", "password": "brand-new-pw-1"}
    )
    assert new_password_login.status_code == 200


@pytest.mark.asyncio
async def test_reset_password_revokes_all_existing_sessions(client):
    """A password reset must be assumed to follow a compromise — every session dies with it."""
    register_res = await client.post("/api/v1/auth/register", json=_register_payload())
    user_id = register_res.json()["data"]["user"]["id"]
    original_refresh_token = register_res.json()["data"]["refresh_token"]

    token = await _issue_known_reset_token(user_id)
    await client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": "brand-new-pw-1"}
    )

    refresh_attempt = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": original_refresh_token}
    )
    assert refresh_attempt.status_code == 401


@pytest.mark.asyncio
async def test_reset_password_token_is_single_use(client):
    register_res = await client.post("/api/v1/auth/register", json=_register_payload())
    user_id = register_res.json()["data"]["user"]["id"]
    token = await _issue_known_reset_token(user_id)

    first = await client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": "brand-new-pw-1"}
    )
    assert first.status_code == 204

    second = await client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": "another-new-pw-2"}
    )
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "INVALID_RESET_TOKEN"


@pytest.mark.asyncio
async def test_reset_password_rejects_reused_password(client):
    register_res = await client.post("/api/v1/auth/register", json=_register_payload())
    user_id = register_res.json()["data"]["user"]["id"]
    token = await _issue_known_reset_token(user_id)

    response = await client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": "correct-horse-9"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PASSWORD_REUSED"


@pytest.mark.asyncio
async def test_change_password_requires_correct_current_password(client):
    register_res = await client.post("/api/v1/auth/register", json=_register_payload())
    access_token = register_res.json()["data"]["access_token"]

    response = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "wrong-current-1", "new_password": "brand-new-pw-1"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_change_password_succeeds_and_revokes_other_sessions(client):
    register_res = await client.post("/api/v1/auth/register", json=_register_payload())
    access_token = register_res.json()["data"]["access_token"]
    refresh_token = register_res.json()["data"]["refresh_token"]

    response = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "correct-horse-9", "new_password": "brand-new-pw-1"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 204

    refresh_attempt = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert refresh_attempt.status_code == 401

    new_login = await client.post(
        "/api/v1/auth/login", json={"email": "marie@example.com", "password": "brand-new-pw-1"}
    )
    assert new_login.status_code == 200
