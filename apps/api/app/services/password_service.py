"""
Shared password-change mechanics used by both the authenticated
change-password endpoint and the (unauthenticated, token-based) password
reset flow — see docs/adr/0018 and docs/adr/0019.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.password_history import PasswordHistory
from app.models.user import User

_HISTORY_SIZE = 5


class PasswordReusedError(Exception):
    pass


async def assert_not_reused(db: AsyncSession, user_id: str, new_password: str) -> None:
    """Raises PasswordReusedError if new_password matches the current password or any of the last N."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is not None and verify_password(new_password, user.hashed_password):
        raise PasswordReusedError("New password must be different from your current password.")

    history_result = await db.execute(
        select(PasswordHistory)
        .where(PasswordHistory.user_id == user_id)
        .order_by(PasswordHistory.created_at.desc())
        .limit(_HISTORY_SIZE)
    )
    for entry in history_result.scalars().all():
        if verify_password(new_password, entry.hashed_password):
            raise PasswordReusedError(
                f"You've used this password before. Choose one you haven't used in your last {_HISTORY_SIZE} passwords."
            )


async def set_password(db: AsyncSession, user: User, new_password: str) -> None:
    """
    Updates user.hashed_password and archives the *previous* hash into
    password_history, trimming to the last _HISTORY_SIZE entries. Does
    NOT commit — callers control the transaction boundary (they typically
    also revoke sessions / write an audit log in the same unit of work).
    """
    db.add(PasswordHistory(user_id=user.id, hashed_password=user.hashed_password))
    user.hashed_password = hash_password(new_password)

    # Trim history to the most recent _HISTORY_SIZE rows for this user.
    result = await db.execute(
        select(PasswordHistory)
        .where(PasswordHistory.user_id == user.id)
        .order_by(PasswordHistory.created_at.desc())
    )
    entries = list(result.scalars().all())
    for stale_entry in entries[_HISTORY_SIZE:]:
        await db.delete(stale_entry)
