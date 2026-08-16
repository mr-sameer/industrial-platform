"""
Config redaction — Module 5B. Source credentials must never appear in
plaintext logs, API responses, error messages, or raw observations
(per this module's own security requirement). This is the one shared
utility every logging/persistence path in acquisition_service routes
adapter config through before it's ever written anywhere.

Deliberately simple: a fixed key-name denylist, not a full secrets-
management platform — this phase's own instruction is "do not
introduce a complicated secrets platform unless the existing
architecture requires it." No real adapter with real credentials
exists yet (MockSourceAdapter has none) — this exists so the boundary
is established and tested now, before one is ever added.
"""

from typing import Any

_SENSITIVE_KEY_MARKERS = ("password", "secret", "token", "api_key", "apikey", "credential", "auth")

REDACTED_PLACEHOLDER = "***REDACTED***"


def redact_config(config: dict[str, Any]) -> dict[str, Any]:
    """
    Returns a copy of `config` with any key whose name suggests it
    holds a credential replaced by a fixed placeholder. Recurses into
    nested dicts (a real adapter's config may reasonably nest an "auth"
    block). Matching is on key *name*, not value shape — deliberately
    conservative (a false-positive redaction of a non-sensitive field
    named e.g. "token_expiry_seconds" is a harmless, acceptable cost;
    a false negative that lets a real secret through is not).
    """
    redacted: dict[str, Any] = {}
    for key, value in config.items():
        if isinstance(value, dict):
            redacted[key] = redact_config(value)
        elif any(marker in key.lower() for marker in _SENSITIVE_KEY_MARKERS):
            redacted[key] = REDACTED_PLACEHOLDER
        else:
            redacted[key] = value
    return redacted
