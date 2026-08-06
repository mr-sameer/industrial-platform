"""
Auth business logic, kept out of the router per docs/standards/coding-standards.md
("route handlers stay thin"). Everything here operates on a request-scoped
AsyncSession injected by the caller. Rate limiting and lockout state (Redis)
are applied by the router (see app/api/v1/auth.py) *before* calling into
these functions, since they need the request's IP and don't belong to a
per-user-transaction concern the way session/password logic does.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.password_policy import validate_password_strength
from app.core.security import create_access_token, hash_password, verify_password
from app.models.session import Session, SessionRevokedReason
from app.models.user import User
from app.schemas.auth import AuthTokenPair, RegisterRequest, UserPublic
from app.services import session_service
from app.services.verification_service import issue_verification_token, send_verification_email

settings = get_settings()

# A real Argon2id hash of an arbitrary, never-used password — verified
# against on the unknown-email login path so that path costs the same
# CPU time as a real (wrong-password) verification. See authenticate_user.
_DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$AgAgZCxFaK1VSknpnXOuVQ$bsftg0IeFuaoIhRWK4WY26SEG3o57Wch0JIdCDSip6I"


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class InactiveUserError(Exception):
    pass


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


def _token_pair_for(user: User, session: Session, refresh_token: str) -> AuthTokenPair:
    return AuthTokenPair(
        access_token=create_access_token(str(user.id)),
        refresh_token=refresh_token,
        expires_in_minutes=settings.jwt_access_token_expire_minutes,
        user=UserPublic.model_validate(user),
    )


async def register_user(
    db: AsyncSession,
    payload: RegisterRequest,
    *,
    ip_address: str | None,
    user_agent: str | None,
    device_name: str | None = None,
) -> AuthTokenPair:
    existing = await get_user_by_email(db, payload.email)
    if existing is not None:
        raise EmailAlreadyRegisteredError(payload.email)

    # RegisterRequest already enforces basic composition (letter+digit,
    # length) via its field_validator; validate_password_strength adds the
    # common-password blacklist check on top (see docs/adr/0018).
    validate_password_strength(payload.password)

    user = User(
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    session, refresh_token = await session_service.create_session(
        db, str(user.id), ip_address=ip_address, user_agent=user_agent, device_name=device_name
    )

    verification_token = await issue_verification_token(db, user)
    await send_verification_email(user, verification_token)

    return _token_pair_for(user, session, refresh_token)


async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str,
    *,
    ip_address: str | None,
    user_agent: str | None,
    device_name: str | None = None,
) -> AuthTokenPair:
    user = await get_user_by_email(db, email)
    # Deliberately identical error for "no such user" and "wrong password" —
    # distinguishing them lets an attacker enumerate registered emails.
    # Just as important: verify_password runs even when user is None (against
    # a fixed dummy hash) so the two cases also take the same amount of time.
    # Argon2id is deliberately slow; short-circuiting it on the unknown-email
    # path would otherwise make that path measurably faster and reintroduce
    # the same enumeration vector via a timing side-channel instead of the
    # response body. See docs/security/threat-model.md, threat #11.
    password_matches = verify_password(password, user.hashed_password if user else _DUMMY_HASH)
    if user is None or not password_matches:
        raise InvalidCredentialsError()
    if not user.is_active:
        raise InactiveUserError()

    session, refresh_token = await session_service.create_session(
        db, str(user.id), ip_address=ip_address, user_agent=user_agent, device_name=device_name
    )
    return _token_pair_for(user, session, refresh_token)


async def refresh_tokens(
    db: AsyncSession, refresh_token: str, *, ip_address: str | None, user_agent: str | None
) -> AuthTokenPair:
    """
    Rotates the refresh token (see session_service for reuse-detection
    semantics) and mints a fresh access token. Raises whatever
    session_service raises (InvalidRefreshTokenError,
    RefreshTokenReuseDetectedError, SessionRevokedOrExpiredError) — the
    router maps each to the appropriate HTTP response.
    """
    session, new_refresh_token = await session_service.rotate_refresh_token(
        db, refresh_token, ip_address=ip_address, user_agent=user_agent
    )
    user = await get_user_by_id(db, str(session.user_id))
    if user is None:
        raise InvalidCredentialsError("User no longer exists")
    if not user.is_active:
        raise InactiveUserError()
    return _token_pair_for(user, session, new_refresh_token)


async def logout(db: AsyncSession, refresh_token: str) -> None:
    """Revokes only the session tied to this specific refresh token — i.e. "log out this device"."""
    session = await session_service.get_session_by_refresh_token(db, refresh_token)
    if session is not None and session.revoked_at is None:
        await session_service.revoke_session(db, session, SessionRevokedReason.LOGOUT)
