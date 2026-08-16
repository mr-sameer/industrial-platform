"""Unit tests for password hashing and access-token issuance/verification — no DB needed."""

import pytest

from app.core.security import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    decode_token,
    hash_password,
    needs_rehash,
    verify_password,
)


def test_hash_password_is_not_plaintext_and_verifies():
    hashed = hash_password("correct-horse-9")
    assert hashed != "correct-horse-9"
    assert verify_password("correct-horse-9", hashed) is True
    assert verify_password("wrong-password9", hashed) is False


def test_hash_password_uses_argon2_by_default():
    """See docs/adr/0018 — Argon2id is the preferred scheme as of Module 2.5."""
    hashed = hash_password("correct-horse-9")
    assert hashed.startswith("$argon2")


def test_needs_rehash_flags_legacy_bcrypt_hashes():
    # A hash produced by bcrypt directly (simulating a pre-Module-2.5 user row)
    # should be flagged for upgrade on next successful login.
    from passlib.hash import bcrypt

    legacy_hash = bcrypt.hash("correct-horse-9")
    assert needs_rehash(legacy_hash) is True
    assert needs_rehash(hash_password("correct-horse-9")) is False


def test_access_token_round_trips():
    token = create_access_token("user-123")
    payload = decode_token(token, TokenType.ACCESS)
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"


def test_decode_token_rejects_garbage():
    with pytest.raises(InvalidTokenError):
        decode_token("not-a-real-token", TokenType.ACCESS)


def test_decode_token_defaults_to_access_type():
    token = create_access_token("user-123")
    payload = decode_token(token)  # no explicit expected_type
    assert payload["sub"] == "user-123"


def test_production_rejects_wildcard_cors_origin(monkeypatch: pytest.MonkeyPatch):
    from app.core.config import Settings

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "a-real-secret-value-not-the-default")
    monkeypatch.setenv("API_CORS_ORIGINS", "*")
    with pytest.raises(ValueError, match="must not contain"):
        Settings()


def test_production_accepts_explicit_cors_origin(monkeypatch: pytest.MonkeyPatch):
    from app.core.config import Settings

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "a-real-secret-value-not-the-default")
    monkeypatch.setenv("API_CORS_ORIGINS", "https://app.example.com")
    settings = Settings()
    assert settings.cors_origins_list == ["https://app.example.com"]
