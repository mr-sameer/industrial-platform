"""
Auth routes. Thin per docs/standards/coding-standards.md — all real logic
lives in app.services.*; this module translates between HTTP/Pydantic and
those services, applies rate limiting/lockout (Redis, request-scoped
concerns that don't belong in a business-logic service), writes audit log
entries, and maps domain exceptions to the standard error envelope.
"""

import uuid

from fastapi import APIRouter, HTTPException, Request, status

from app.core.config import get_settings
from app.core.dependencies import CurrentUser
from app.core.password_policy import WeakPasswordError, validate_password_strength
from app.core.rate_limit import (
    check_rate_limit,
    clear_failed_logins,
    is_account_locked,
    register_failed_login,
)
from app.core.responses import ApiSuccess, success_response
from app.core.security import verify_password
from app.db.redis_client import RedisClient
from app.db.session import DbSession
from app.models.session import SessionRevokedReason
from app.schemas.auth import (
    AuthTokenPair,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SessionPublic,
    UserPublic,
    VerifyEmailRequest,
)
from app.services import auth_service, password_service, session_service, verification_service
from app.services.audit_service import log_event
from app.services.password_reset_service import (
    InvalidResetTokenError,
    request_password_reset,
    reset_password,
)
from app.services.session_service import (
    InvalidRefreshTokenError,
    RefreshTokenReuseDetectedError,
    SessionRevokedOrExpiredError,
)
from app.services.verification_service import AlreadyVerifiedError, InvalidVerificationTokenError

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _client_ip(request: Request) -> str | None:
    # Trusts X-Forwarded-For only because this service is expected to sit
    # behind a reverse proxy in every real deployment; if that stops being
    # true, this must be revisited (a client could otherwise spoof its
    # apparent IP for rate-limiting/audit purposes).
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


@router.post(
    "/register", response_model=ApiSuccess[AuthTokenPair], status_code=status.HTTP_201_CREATED
)
async def register(
    payload: RegisterRequest,
    request: Request,
    db: DbSession,
    redis_client: RedisClient,
) -> ApiSuccess[AuthTokenPair]:
    ip = _client_ip(request)
    await check_rate_limit(
        redis_client,
        f"ratelimit:register:{ip}",
        settings.rate_limit_register_per_ip,
        settings.rate_limit_register_per_ip_window_seconds,
    )
    try:
        tokens = await auth_service.register_user(
            db,
            payload,
            ip_address=ip,
            user_agent=_user_agent(request),
            device_name=payload.device_name,
        )
    except auth_service.EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "EMAIL_ALREADY_REGISTERED",
                "message": "An account with this email already exists.",
            },
        ) from exc
    except WeakPasswordError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "VALIDATION_ERROR", "message": str(exc), "field": "password"},
        ) from exc
    await log_event(
        db,
        "user_registered",
        user_id=str(tokens.user.id),
        ip_address=ip,
        user_agent=_user_agent(request),
    )
    return success_response(tokens)


@router.post("/login", response_model=ApiSuccess[AuthTokenPair])
async def login(
    payload: LoginRequest,
    request: Request,
    db: DbSession,
    redis_client: RedisClient,
) -> ApiSuccess[AuthTokenPair]:
    ip = _client_ip(request)
    ua = _user_agent(request)
    await check_rate_limit(
        redis_client,
        f"ratelimit:login:ip:{ip}",
        settings.rate_limit_login_per_ip,
        settings.rate_limit_login_per_ip_window_seconds,
    )

    locked_seconds = await is_account_locked(redis_client, payload.email)
    if locked_seconds > 0:
        await log_event(
            db,
            "login_blocked_lockout",
            ip_address=ip,
            user_agent=ua,
            metadata={"email": payload.email},
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "ACCOUNT_LOCKED",
                "message": f"Too many failed login attempts. Try again in {locked_seconds} seconds.",
            },
            headers={"Retry-After": str(locked_seconds)},
        )

    try:
        tokens = await auth_service.authenticate_user(
            db,
            payload.email,
            payload.password,
            ip_address=ip,
            user_agent=ua,
            device_name=payload.device_name,
        )
    except auth_service.InvalidCredentialsError as exc:
        await register_failed_login(redis_client, payload.email)
        await log_event(
            db, "login_failed", ip_address=ip, user_agent=ua, metadata={"email": payload.email}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": "Incorrect email or password."},
        ) from exc
    except auth_service.InactiveUserError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "ACCOUNT_INACTIVE", "message": "This account has been deactivated."},
        ) from exc

    await clear_failed_logins(redis_client, payload.email)
    await log_event(
        db, "login_succeeded", user_id=str(tokens.user.id), ip_address=ip, user_agent=ua
    )
    return success_response(tokens)


@router.post("/refresh", response_model=ApiSuccess[AuthTokenPair])
async def refresh(
    payload: RefreshRequest,
    request: Request,
    db: DbSession,
    redis_client: RedisClient,
) -> ApiSuccess[AuthTokenPair]:
    ip = _client_ip(request)
    await check_rate_limit(
        redis_client,
        f"ratelimit:refresh:{ip}",
        settings.rate_limit_refresh_per_ip,
        settings.rate_limit_refresh_per_ip_window_seconds,
    )
    try:
        tokens = await auth_service.refresh_tokens(
            db, payload.refresh_token, ip_address=ip, user_agent=_user_agent(request)
        )
    except RefreshTokenReuseDetectedError as exc:
        await log_event(
            db, "refresh_token_reuse_detected", ip_address=ip, user_agent=_user_agent(request)
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "REFRESH_TOKEN_REUSE_DETECTED",
                "message": "This session has been revoked for your security. Please log in again.",
            },
        ) from exc
    except (
        InvalidRefreshTokenError,
        SessionRevokedOrExpiredError,
        auth_service.InvalidCredentialsError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "INVALID_REFRESH_TOKEN",
                "message": f"Invalid or expired refresh token: {exc}",
            },
        ) from exc
    except auth_service.InactiveUserError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "ACCOUNT_INACTIVE", "message": "This account has been deactivated."},
        ) from exc
    return success_response(tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: LogoutRequest, db: DbSession) -> None:
    """
    Logs out *this device only* — revokes the session tied to the
    presented refresh token. As of Module 2.5 this is a real server-side
    revocation (see docs/adr/0014), unlike Module 2's client-side no-op.
    """
    await auth_service.logout(db, payload.refresh_token)
    return None


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(current_user: CurrentUser, db: DbSession) -> None:
    """Revokes every session for the current user — "log out everywhere"."""
    await session_service.revoke_all_sessions_for_user(
        db, str(current_user.id), SessionRevokedReason.LOGOUT_ALL
    )
    await log_event(db, "logout_all_devices", user_id=str(current_user.id))
    return None


@router.get("/sessions", response_model=ApiSuccess[list[SessionPublic]])
async def list_sessions(
    current_user: CurrentUser, request: Request, db: DbSession
) -> ApiSuccess[list[SessionPublic]]:
    sessions = await session_service.list_active_sessions_for_user(db, str(current_user.id))
    current_ip = _client_ip(request)
    current_ua = _user_agent(request)
    result = []
    for s in sessions:
        public = SessionPublic.model_validate(s)
        public.is_current = s.ip_address == current_ip and s.user_agent == current_ua
        result.append(public)
    return success_response(result)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(session_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    revoked = await session_service.revoke_session_for_user(
        db, str(current_user.id), str(session_id), SessionRevokedReason.ADMIN_REVOKED
    )
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "SESSION_NOT_FOUND",
                "message": "No active session with that ID for this account.",
            },
        )
    await log_event(
        db,
        "session_revoked",
        user_id=str(current_user.id),
        metadata={"session_id": str(session_id)},
    )
    return None


@router.get("/me", response_model=ApiSuccess[UserPublic])
async def me(current_user: CurrentUser) -> ApiSuccess[UserPublic]:
    return success_response(UserPublic.model_validate(current_user))


@router.post("/verify-email", response_model=ApiSuccess[UserPublic])
async def verify_email(
    payload: VerifyEmailRequest,
    request: Request,
    db: DbSession,
    redis_client: RedisClient,
) -> ApiSuccess[UserPublic]:
    ip = _client_ip(request)
    await check_rate_limit(
        redis_client,
        f"ratelimit:verify_email:{ip}",
        settings.rate_limit_verify_email_per_ip,
        settings.rate_limit_verify_email_per_ip_window_seconds,
    )
    try:
        user = await verification_service.verify_email(db, payload.token)
    except InvalidVerificationTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_VERIFICATION_TOKEN", "message": str(exc)},
        ) from exc
    await log_event(db, "email_verified", user_id=str(user.id), ip_address=ip)
    return success_response(UserPublic.model_validate(user))


@router.post("/resend-verification", status_code=status.HTTP_204_NO_CONTENT)
async def resend_verification(current_user: CurrentUser, db: DbSession) -> None:
    try:
        await verification_service.resend_verification(db, current_user)
    except AlreadyVerifiedError:
        # Idempotent from the caller's point of view — already verified is not an error.
        return None
    await log_event(db, "verification_email_resent", user_id=str(current_user.id))
    return None


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: DbSession,
    redis_client: RedisClient,
) -> None:
    """
    Always returns 204 regardless of whether the email is registered —
    the response must not reveal account existence (see
    docs/adr/0019 and the login endpoint's identical-error precedent).
    """
    ip = _client_ip(request)
    await check_rate_limit(
        redis_client,
        f"ratelimit:forgot_password:{ip}",
        settings.rate_limit_forgot_password_per_ip,
        settings.rate_limit_forgot_password_per_ip_window_seconds,
    )
    user = await auth_service.get_user_by_email(db, payload.email)
    await request_password_reset(db, user)
    await log_event(
        db, "password_reset_requested", ip_address=ip, metadata={"email": payload.email}
    )
    return None


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password_endpoint(
    payload: ResetPasswordRequest, request: Request, db: DbSession
) -> None:
    try:
        user = await reset_password(db, payload.token, payload.new_password)
    except InvalidResetTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_RESET_TOKEN", "message": str(exc)},
        ) from exc
    except WeakPasswordError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "VALIDATION_ERROR", "message": str(exc), "field": "new_password"},
        ) from exc
    except password_service.PasswordReusedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "PASSWORD_REUSED", "message": str(exc)},
        ) from exc
    await log_event(
        db, "password_reset_completed", user_id=str(user.id), ip_address=_client_ip(request)
    )
    return None


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: CurrentUser,
    request: Request,
    db: DbSession,
) -> None:
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": "Current password is incorrect."},
        )
    try:
        validate_password_strength(payload.new_password)
        await password_service.assert_not_reused(db, str(current_user.id), payload.new_password)
    except WeakPasswordError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "VALIDATION_ERROR", "message": str(exc), "field": "new_password"},
        ) from exc
    except password_service.PasswordReusedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "PASSWORD_REUSED", "message": str(exc)},
        ) from exc

    await password_service.set_password(db, current_user, payload.new_password)
    await session_service.revoke_all_sessions_for_user(
        db, str(current_user.id), SessionRevokedReason.PASSWORD_RESET
    )
    await db.commit()
    await log_event(
        db, "password_changed", user_id=str(current_user.id), ip_address=_client_ip(request)
    )
    return None
