"""
Opaque (non-JWT) bearer tokens used for refresh tokens, email verification
tokens, and password reset tokens. Unlike access tokens, these are never
decoded/verified by signature alone — they're looked up in the database,
so only a hash of the secret half is ever stored (never the token itself).

Format: "<row-id>.<url-safe-secret>". The id half lets a single indexed
lookup find the candidate row; the secret half is compared by hash.
"""

import hashlib
import secrets
import uuid

_SECRET_BYTES = 32  # 256 bits of entropy


def new_opaque_secret() -> str:
    return secrets.token_urlsafe(_SECRET_BYTES)


def hash_opaque_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def encode_opaque_token(row_id: uuid.UUID, secret: str) -> str:
    return f"{row_id}.{secret}"


def decode_opaque_token(token: str) -> tuple[uuid.UUID, str] | None:
    try:
        id_part, secret_part = token.split(".", 1)
        return uuid.UUID(id_part), secret_part
    except (ValueError, AttributeError):
        return None
