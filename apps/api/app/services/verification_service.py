"""Email verification token lifecycle. See docs/adr/0019."""

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
from app.models.email_verification_token import EmailVerificationToken
from app.models.user import User
from app.services.email_service import get_email_sender, render_verification_email

settings = get_settings()

_TOKEN_TTL = timedelta(hours=24)


class InvalidVerificationTokenError(Exception):
    pass


class AlreadyVerifiedError(Exception):
    pass


async def issue_verification_token(db: AsyncSession, user: User) -> str:
    secret = new_opaque_secret()
    token_row = EmailVerificationToken(
        user_id=user.id,
        token_hash=hash_opaque_secret(secret),
        expires_at=datetime.now(UTC) + _TOKEN_TTL,
    )
    db.add(token_row)
    await db.flush()
    await db.commit()
    return encode_opaque_token(token_row.id, secret)


async def send_verification_email(user: User, token: str) -> None:
    verification_url = f"{settings.web_app_base_url}/verify-email?token={token}"
    html = render_verification_email(full_name=user.full_name, verification_url=verification_url)
    await get_email_sender().send(
        to=user.email, subject="Verify your email", html_body=html, action_url=verification_url
    )


async def resend_verification(db: AsyncSession, user: User) -> None:
    if user.is_email_verified:
        raise AlreadyVerifiedError()
    token = await issue_verification_token(db, user)
    await send_verification_email(user, token)


async def verify_email(db: AsyncSession, token: str) -> User:
    decoded = decode_opaque_token(token)
    if decoded is None:
        raise InvalidVerificationTokenError("Malformed token")
    token_id, secret = decoded

    result = await db.execute(
        select(EmailVerificationToken).where(EmailVerificationToken.id == token_id)
    )
    token_row = result.scalar_one_or_none()
    if token_row is None or token_row.token_hash != hash_opaque_secret(secret):
        raise InvalidVerificationTokenError("Unknown token")
    if token_row.used_at is not None:
        raise InvalidVerificationTokenError("Token already used")
    if token_row.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise InvalidVerificationTokenError("Token expired")

    user_result = await db.execute(select(User).where(User.id == token_row.user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise InvalidVerificationTokenError("User no longer exists")

    token_row.used_at = datetime.now(UTC)
    user.is_email_verified = True
    user.email_verified_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(user)
    return user
