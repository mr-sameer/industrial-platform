import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.user import Role

_PASSWORD_MIN_LENGTH = 10


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=_PASSWORD_MIN_LENGTH, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    device_name: str | None = Field(default=None, max_length=255)

    @field_validator("password")
    @classmethod
    def password_has_letter_and_digit(cls, v: str) -> str:
        if not any(c.isalpha() for c in v) or not any(c.isdigit() for c in v):
            raise ValueError("password must contain at least one letter and one digit")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    device_name: str | None = Field(default=None, max_length=255)


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=_PASSWORD_MIN_LENGTH, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_has_letter_and_digit(cls, v: str) -> str:
        if not any(c.isalpha() for c in v) or not any(c.isdigit() for c in v):
            raise ValueError("password must contain at least one letter and one digit")
        return v


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=_PASSWORD_MIN_LENGTH, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_has_letter_and_digit(cls, v: str) -> str:
        if not any(c.isalpha() for c in v) or not any(c.isdigit() for c in v):
            raise ValueError("password must contain at least one letter and one digit")
        return v


class VerifyEmailRequest(BaseModel):
    token: str


class SessionPublic(BaseModel):
    id: uuid.UUID
    device_name: str | None
    browser: str | None
    platform: str | None
    ip_address: str | None
    created_at: datetime
    last_active_at: datetime
    is_current: bool = False

    model_config = {"from_attributes": True}


class UserPublic(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: Role
    is_active: bool
    is_email_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AuthTokenPair(BaseModel):
    """
    The FastAPI service always returns *both* tokens in the JSON body — it
    has no concept of a browser cookie jar and stays transport-agnostic.
    What each client does with the refresh token differs:

      - Mobile calls these endpoints directly and stores both tokens in
        platform secure storage (Keychain/Keystore) — see
        apps/mobile/lib/core/storage/secure_token_storage.dart.
      - Web never calls these endpoints from the browser. A Next.js Route
        Handler (the "BFF") calls them server-side, returns only
        `access_token` to the browser for in-memory storage, and sets
        `refresh_token` as an httpOnly, Secure cookie on the web app's own
        domain — see apps/web/src/app/api/auth/*/route.ts and
        docs/adr/0012-web-session-strategy.md.

    As of Module 2.5, `refresh_token` is an opaque, database-backed,
    rotating token — not a JWT. See docs/adr/0014.
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: UserPublic
