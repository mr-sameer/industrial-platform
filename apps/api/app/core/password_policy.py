"""
Password strength validation and a small common-password blacklist.
Kept intentionally simple (length/composition + blacklist membership) —
entropy-estimation libraries (e.g. zxcvbn) are a reasonable future
upgrade, not required for this hardening pass.
"""

_MIN_LENGTH = 10
_MAX_LENGTH = 128

# A deliberately small, illustrative sample of the most common leaked
# passwords (e.g. from "have i been pwned" / SecLists top-N lists).
# Swap this for a real, larger list (or a k-anonymity HIBP API check) in
# a follow-up — the point here is that the check exists and is easy to
# extend, not that this exact list is exhaustive.
COMMON_PASSWORDS: frozenset[str] = frozenset(
    {
        "password",
        "password1",
        "password123",
        "123456",
        "123456789",
        "12345678",
        "qwerty",
        "qwerty123",
        "letmein",
        "welcome",
        "welcome1",
        "admin123",
        "iloveyou",
        "monkey123",
        "dragon123",
        "football1",
        "baseball1",
        "sunshine1",
        "princess1",
        "trustno1",
        "abc12345",
        "1234567890",
        "changeme1",
        "passw0rd",
        "p@ssw0rd",
    }
)


class WeakPasswordError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def validate_password_strength(password: str) -> None:
    """Raises WeakPasswordError with a human-readable reason, or returns None if acceptable."""
    if len(password) < _MIN_LENGTH:
        raise WeakPasswordError(f"Password must be at least {_MIN_LENGTH} characters.")
    if len(password) > _MAX_LENGTH:
        raise WeakPasswordError(f"Password must be at most {_MAX_LENGTH} characters.")
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        raise WeakPasswordError("Password must contain at least one letter and one digit.")
    if password.lower() in COMMON_PASSWORDS:
        raise WeakPasswordError("This password is too common. Please choose a different one.")
