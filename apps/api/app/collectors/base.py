"""
Source adapter / collector abstraction — Module 5B. The contract every
future collector (website, API, public dataset, government source,
company submission, file/document) implements, so the acquisition
service (app.services.acquisition_service) never needs to know which
kind of source it's talking to.

Deliberately NOT built around websites specifically — `collect()`
returns a plain list of `CollectedItem`, agnostic to how those items
were actually obtained. A future website adapter, API adapter, etc.
all implement the same three methods below.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CollectedItem:
    """
    One candidate raw observation a collector run produced. Deliberately
    mirrors app.schemas.provenance.RawObservationCreate's shape closely
    (minus source_id, which the acquisition service already knows) —
    this is what gets handed to provenance_service.create_raw_observation
    unchanged, once idempotency has been checked.

    `external_identifier` is the adapter's own stable reference for this
    specific item (a URL, a registry record ID, a document ID) — the
    primary idempotency key (see acquisition_service's docstring on
    strategy). May be None for a source with no natural stable
    identifier, in which case content_hash alone is the fallback key.
    """

    raw_content: dict[str, Any]
    content_hash: str
    external_identifier: str | None = None


class RetryableCollectorError(Exception):
    """
    Raised by an adapter for a transient failure worth retrying —
    a timeout, a temporary rate-limit response, a momentary
    connectivity failure. The acquisition service retries up to a
    bounded limit (see that module's own docstring) before giving up.
    """


class NonRetryableCollectorError(Exception):
    """
    Raised by an adapter for a failure retrying cannot fix — invalid
    credentials, malformed source configuration, a permanently-gone
    resource. The acquisition service fails the job immediately on
    this exception, with zero retry attempts — retrying something that
    cannot succeed only delays an honest failure state and risks
    looking like the system is "trying," which is worse than a prompt,
    clear failure.
    """


class SourceAdapter(abc.ABC):
    """
    Every collector subclasses this. `adapter_type` is the string key
    the acquisition job's `collector_type` field references — see
    app.collectors.registry for the type->class mapping.
    """

    adapter_type: str

    @abc.abstractmethod
    def validate_config(self, config: dict[str, Any]) -> None:
        """
        Raises NonRetryableCollectorError if `config` is structurally
        invalid for this adapter (missing required keys, wrong types)
        — checked before collect() ever runs, so an invalid
        configuration fails fast with a clear message rather than
        failing confusingly partway through collection.
        """

    @abc.abstractmethod
    def collect(self, config: dict[str, Any]) -> list[CollectedItem]:
        """
        Performs one collection run and returns everything found.
        Raises RetryableCollectorError or NonRetryableCollectorError on
        failure — never returns a partial/empty list to silently
        signal failure, since an adapter genuinely finding zero items
        (a real, valid outcome) must remain distinguishable from an
        adapter that failed to collect at all.
        """

    @abc.abstractmethod
    def source_metadata(self) -> dict[str, Any]:
        """A small, redaction-safe description of this adapter instance
        — never includes credentials or secrets (see
        app.collectors.secrets.redact_config, which callers should
        apply to the *input* config before ever logging or persisting
        it; this method describes the adapter itself, not its config)."""
