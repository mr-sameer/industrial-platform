"""
FastAPI dependencies for authentication and authorization. Any route that
needs a logged-in user depends on `get_current_user`; any route that
needs a specific role depends on `require_role(Role.ADMIN)` etc.
"""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import InvalidTokenError, TokenType, decode_token
from app.db.session import get_db
from app.models.user import Role, User
from app.services.auth_service import get_user_by_id

_bearer_scheme = HTTPBearer(auto_error=False, description="Access token issued by /auth/login")


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized

    try:
        payload = decode_token(credentials.credentials, TokenType.ACCESS)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = await get_user_by_id(db, payload["sub"])
    if user is None or not user.is_active:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_verified_email(current_user: CurrentUser) -> User:
    """
    Usage: `user: User = Depends(require_verified_email)` on any future
    route that should be blocked until the user has confirmed their
    email — e.g. creating a company/organization (see Module 2.5's
    Phase 4). Used by Module 3A's `POST /companies` — see
    app.api.v1.companies.create_company.
    """
    if not current_user.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "EMAIL_NOT_VERIFIED",
                "message": "Please verify your email address before continuing.",
            },
        )
    return current_user


VerifiedUser = Annotated[User, Depends(require_verified_email)]


def require_role(
    *allowed_roles: Role,
) -> Callable[[User], Coroutine[Any, Any, User]]:
    """Usage: `user: CurrentUser = Depends(require_role(Role.ADMIN))` on a route."""

    async def _check(current_user: CurrentUser) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(r.value for r in allowed_roles)}",
            )
        return current_user

    return _check
