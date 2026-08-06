"""
Session + refresh-token lifecycle. See docs/adr/0014-refresh-token-and-session-model.md
for the full design rationale. Summary of the invariants this module
maintains:

- Exactly one `RefreshToken` row per `Session` has `used_at IS NULL` at
  any time — that is the currently valid token for that session.
- Refreshing **rotates**: the presented token is marked used, a new one
  is created, and the client receives the new one. The old token string
  is never valid again.
- **Reuse detection**: if a presented token's hash matches a row that is
  already `used_at IS NOT NULL`, someone is replaying a token that was
  already rotated away — the strongest available signal of theft. The
  entire session is revoked immediately (not just that token), forcing
  both the attacker and the legitimate user to re-authenticate.
"""

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
from app.core.user_agent import parse_browser, parse_platform
from app.models.refresh_token import RefreshToken
from app.models.session import Session, SessionRevokedReason

settings = get_settings()


class InvalidRefreshTokenError(Exception):
    pass


class RefreshTokenReuseDetectedError(Exception):
    """Raised when a previously-rotated-away token is presented again. The session has been revoked."""


class SessionRevokedOrExpiredError(Exception):
    pass


def _session_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days)


async def create_session(
    db: AsyncSession,
    user_id: str,
    *,
    ip_address: str | None,
    user_agent: str | None,
    device_name: str | None = None,
) -> tuple[Session, str]:
    """Creates a new session (i.e. a new login) and its first refresh token. Returns (session, refresh_token_string)."""
    session = Session(
        user_id=user_id,
        device_name=device_name,
        browser=parse_browser(user_agent),
        platform=parse_platform(user_agent),
        user_agent=user_agent[:512] if user_agent else None,
        ip_address=ip_address,
        expires_at=_session_expiry(),
    )
    db.add(session)
    await db.flush()  # assigns session.id without committing yet

    refresh_token_string = await _issue_new_token(db, session)
    await db.commit()
    await db.refresh(session)
    return session, refresh_token_string


async def _issue_new_token(db: AsyncSession, session: Session) -> str:
    secret = new_opaque_secret()
    token_row = RefreshToken(session_id=session.id, token_hash=hash_opaque_secret(secret))
    db.add(token_row)
    await db.flush()  # assigns token_row.id
    return encode_opaque_token(token_row.id, secret)


async def rotate_refresh_token(
    db: AsyncSession,
    refresh_token_string: str,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[Session, str]:
    """
    Validates and rotates a refresh token. Returns (session, new_refresh_token_string).
    Raises InvalidRefreshTokenError, RefreshTokenReuseDetectedError, or SessionRevokedOrExpiredError.
    """
    decoded = decode_opaque_token(refresh_token_string)
    if decoded is None:
        raise InvalidRefreshTokenError("Malformed refresh token")
    token_id, secret = decoded

    result = await db.execute(select(RefreshToken).where(RefreshToken.id == token_id))
    token_row = result.scalar_one_or_none()
    if token_row is None or token_row.token_hash != hash_opaque_secret(secret):
        raise InvalidRefreshTokenError("Unknown or malformed refresh token")

    session_result = await db.execute(select(Session).where(Session.id == token_row.session_id))
    session = session_result.scalar_one_or_none()
    if session is None:
        raise InvalidRefreshTokenError("Session no longer exists")

    if token_row.used_at is not None:
        # This exact token was already rotated away once. Someone is
        # replaying it — treat the whole session as compromised.
        await revoke_session(db, session, SessionRevokedReason.REUSE_DETECTED)
        raise RefreshTokenReuseDetectedError("Refresh token reuse detected; session revoked")

    if session.revoked_at is not None:
        raise SessionRevokedOrExpiredError("Session has been revoked")
    if session.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise SessionRevokedOrExpiredError("Session has expired")

    now = datetime.now(UTC)
    new_token_string = await _issue_new_token(db, session)

    # Mark the presented token used and link it to its replacement.
    new_decoded = decode_opaque_token(new_token_string)
    assert new_decoded is not None  # we just created it
    token_row.used_at = now
    token_row.replaced_by_id = new_decoded[0]

    session.last_active_at = now
    if ip_address:
        session.ip_address = ip_address
    session.expires_at = _session_expiry()  # sliding expiration on activity

    await db.commit()
    await db.refresh(session)
    return session, new_token_string


async def revoke_session(db: AsyncSession, session: Session, reason: SessionRevokedReason) -> None:
    session.revoked_at = datetime.now(UTC)
    session.revoked_reason = reason
    await db.commit()


async def get_session_by_refresh_token(
    db: AsyncSession, refresh_token_string: str
) -> Session | None:
    decoded = decode_opaque_token(refresh_token_string)
    if decoded is None:
        return None
    token_id, secret = decoded
    result = await db.execute(select(RefreshToken).where(RefreshToken.id == token_id))
    token_row = result.scalar_one_or_none()
    if token_row is None or token_row.token_hash != hash_opaque_secret(secret):
        return None
    session_result = await db.execute(select(Session).where(Session.id == token_row.session_id))
    return session_result.scalar_one_or_none()


async def revoke_session_for_user(
    db: AsyncSession, user_id: str, session_id: str, reason: SessionRevokedReason
) -> bool:
    """Revokes a session only if it belongs to user_id. Returns False if not found/not owned."""
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.user_id == user_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        return False
    await revoke_session(db, session, reason)
    return True


async def revoke_all_sessions_for_user(
    db: AsyncSession,
    user_id: str,
    reason: SessionRevokedReason,
    *,
    except_session_id: str | None = None,
) -> int:
    result = await db.execute(
        select(Session).where(Session.user_id == user_id, Session.revoked_at.is_(None))
    )
    sessions = result.scalars().all()
    now = datetime.now(UTC)
    count = 0
    for session in sessions:
        if except_session_id is not None and str(session.id) == str(except_session_id):
            continue
        session.revoked_at = now
        session.revoked_reason = reason
        count += 1
    await db.commit()
    return count


async def list_active_sessions_for_user(db: AsyncSession, user_id: str) -> list[Session]:
    result = await db.execute(
        select(Session)
        .where(Session.user_id == user_id, Session.revoked_at.is_(None))
        .order_by(Session.last_active_at.desc())
    )
    return list(result.scalars().all())


async def cleanup_expired_sessions(
    db: AsyncSession, *, grace_period: timedelta = timedelta(days=1)
) -> int:
    """
    Deletes sessions (and, via ON DELETE CASCADE, their refresh tokens)
    that expired more than `grace_period` ago. Intended to be run
    periodically (see scripts/cleanup_expired_tokens.py) — Module 2.5
    ships this as a standalone script rather than a scheduled task, since
    no task scheduler (Celery/APScheduler/etc.) exists in this codebase
    yet; wiring one up is future infrastructure work, not an auth concern.
    """
    cutoff = datetime.now(UTC) - grace_period
    result = await db.execute(select(Session).where(Session.expires_at < cutoff))
    sessions = result.scalars().all()
    count = len(sessions)
    for session in sessions:
        await db.delete(session)
    await db.commit()
    return count
