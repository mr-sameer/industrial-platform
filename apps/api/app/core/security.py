"""
Password hashing and access-token issuance/verification.

Password hashing: passlib's CryptContext, preferring Argon2id (the
current OWASP-recommended default) with bcrypt kept only to verify any
pre-existing hashes — see docs/adr/0018-argon2id-password-hashing.md
(supersedes ADR-0011, which chose bcrypt at foundation stage).
`deprecated="auto"` means passlib transparently re-hashes with argon2 on
the next successful login for any user still on a bcrypt hash; no bulk
migration needed.

Tokens: only the **access token** is a JWT here — short-lived (default 15
min), sent as `Authorization: Bearer <token>`, verified stateless (no
DB/Redis lookup) for speed. The refresh token is no longer a JWT — see
app.core.opaque_tokens and app.services.session_service for the
database-backed, rotating, revocable design (docs/adr/0014).
"""

import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()

_pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


def needs_rehash(hashed_password: str) -> bool:
    """True if this hash was made with a deprecated scheme (e.g. legacy bcrypt) and should be upgraded."""
    return _pwd_context.needs_update(hashed_password)


class TokenType(StrEnum):
    ACCESS = "access"


class InvalidTokenError(Exception):
    """Raised for any expired/malformed/wrong-type access token. Callers map this to 401."""


def create_access_token(user_id: str) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": user_id,
        "type": TokenType.ACCESS.value,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: TokenType = TokenType.ACCESS) -> dict[str, Any]:
    """Decodes and validates an access token's signature, expiry, and type. Raises InvalidTokenError otherwise."""
    try:
        payload: dict[str, Any] = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    if payload.get("type") != expected_type.value:
        raise InvalidTokenError(f"Expected a {expected_type.value} token")

    return payload
