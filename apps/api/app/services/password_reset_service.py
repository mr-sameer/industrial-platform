"""Forgot/reset password flow. See docs/adr/0019 and docs/adr/0014 (session revocation on reset)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.opaque_tokens import (
    decode_opaque_token,
    encode_opaque_token,
    hash_opaque_secret,
    new_opaque_secret,
)
from app.core.password_policy import validate_password_strength
from app.models.password_reset_token import PasswordResetToken
from app.models.session import SessionRevokedReason
from app.models.user import User
from app.services import password_service
from app.services.email_service import get_email_sender, render_password_reset_email
from app.services.session_service import revoke_all_sessions_for_user

settings = get_settings()

_TOKEN_TTL = timedelta(hours=1)


class InvalidResetTokenError(Exception):
    pass


async def request_password_reset(db: AsyncSession, user: User | None) -> None:
    """
    No-op (but returns successfully) if user is None — the router always
    calls this for any submitted email to avoid revealing whether an
    account exists (see app/api/v1/auth.py's forgot-password endpoint).
    """
    if user is None:
        return

    secret = new_opaque_secret()
    token_row = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_opaque_secret(secret),
        expires_at=datetime.now(UTC) + _TOKEN_TTL,
    )
    db.add(token_row)
    await db.flush()
    await db.commit()

    token = encode_opaque_token(token_row.id, secret)
    reset_url = f"{settings.web_app_base_url}/reset-password?token={token}"
    html = render_password_reset_email(full_name=user.full_name, reset_url=reset_url)
    await get_email_sender().send(to=user.email, subject="Reset your password", html_body=html)


async def reset_password(db: AsyncSession, token: str, new_password: str) -> User:
    decoded = decode_opaque_token(token)
    if decoded is None:
        raise InvalidResetTokenError("Malformed token")
    token_id, secret = decoded

    result = await db.execute(select(PasswordResetToken).where(PasswordResetToken.id == token_id))
    token_row = result.scalar_one_or_none()
    if token_row is None or token_row.token_hash != hash_opaque_secret(secret):
        raise InvalidResetTokenError("Unknown token")
    if token_row.used_at is not None:
        raise InvalidResetTokenError("Token already used")
    if token_row.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise InvalidResetTokenError("Token expired")

    user_result = await db.execute(select(User).where(User.id == token_row.user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise InvalidResetTokenError("User no longer exists")

    validate_password_strength(
        new_password
    )  # raises WeakPasswordError, mapped to 422 by the router
    await password_service.assert_not_reused(db, str(user.id), new_password)

    token_row.used_at = datetime.now(UTC)
    await password_service.set_password(db, user, new_password)

    # A password reset means we must assume the old password (and anything
    # an attacker who knew it could have done) is no longer trustworthy —
    # every existing session is revoked, forcing re-login everywhere.
    await revoke_all_sessions_for_user(db, str(user.id), SessionRevokedReason.PASSWORD_RESET)

    await db.commit()
    await db.refresh(user)
    return user
