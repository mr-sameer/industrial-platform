"""
Email verification tests. Since the email sender is a logging stub in
Module 2.5 (see app.services.email_service and docs/adr/0019), tests
extract the verification token directly from the database rather than
parsing an email — the token generation/consumption logic is exactly the
same either way.
"""

import pytest

from app.core.opaque_tokens import encode_opaque_token, hash_opaque_secret, new_opaque_secret
from app.db.session import AsyncSessionLocal
from app.models.email_verification_token import EmailVerificationToken


def _register_payload(email: str = "ada@example.com") -> dict:
    return {"email": email, "password": "correct-horse-9", "full_name": "Ada Lovelace"}


async def _issue_known_verification_token(user_id) -> str:
    """Bypasses email sending: writes a token row directly and returns the equivalent opaque string."""
    from datetime import UTC, datetime, timedelta

    secret = new_opaque_secret()
    async with AsyncSessionLocal() as db:
        row = EmailVerificationToken(
            user_id=user_id,
            token_hash=hash_opaque_secret(secret),
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return encode_opaque_token(row.id, secret)


@pytest.mark.asyncio
async def test_new_user_is_not_verified_by_default(client):
    response = await client.post("/api/v1/auth/register", json=_register_payload())
    assert response.json()["data"]["user"]["is_email_verified"] is False


@pytest.mark.asyncio
async def test_verify_email_with_valid_token_marks_user_verified(client):
    register_res = await client.post("/api/v1/auth/register", json=_register_payload())
    user_id = register_res.json()["data"]["user"]["id"]

    token = await _issue_known_verification_token(user_id)
    response = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert response.status_code == 200
    assert response.json()["data"]["is_email_verified"] is True


@pytest.mark.asyncio
async def test_verify_email_token_is_single_use(client):
    register_res = await client.post("/api/v1/auth/register", json=_register_payload())
    user_id = register_res.json()["data"]["user"]["id"]
    token = await _issue_known_verification_token(user_id)

    first = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert first.status_code == 200

    second = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "INVALID_VERIFICATION_TOKEN"


@pytest.mark.asyncio
async def test_verify_email_rejects_malformed_token(client):
    response = await client.post("/api/v1/auth/verify-email", json={"token": "garbage"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_VERIFICATION_TOKEN"


@pytest.mark.asyncio
async def test_resend_verification_is_idempotent_once_verified(client):
    register_res = await client.post("/api/v1/auth/register", json=_register_payload())
    access_token = register_res.json()["data"]["access_token"]
    user_id = register_res.json()["data"]["user"]["id"]

    token = await _issue_known_verification_token(user_id)
    await client.post("/api/v1/auth/verify-email", json={"token": token})

    response = await client.post(
        "/api/v1/auth/resend-verification", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 204  # no error even though already verified


@pytest.mark.asyncio
async def test_resend_verification_requires_authentication(client):
    response = await client.post("/api/v1/auth/resend-verification")
    assert response.status_code == 401
