"""
In-memory shapes exchanged between app.services.spec_extraction_service
and the pure app.extraction modules — never persisted, never an ORM
model. See app.extraction.validation.ParsedReading for the one
per-occurrence shape that *does* carry parsed values; these are the
document-level results the extraction run reports back to its caller.
"""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class RejectedCandidate:
    """A candidate that failed app.extraction.validation and therefore
    never became a ProductAttributeEvidence row of any status."""

    page: int
    label: str
    reason: str


@dataclass(frozen=True)
class AmbiguousConfigurationEntry:
    """A label that matched more than one specification's name/alias
    set within the target product's own category — a category
    authoring conflict, reported for a human to fix, never resolved by
    guessing which specification was meant."""

    label: str
    specification_ids: list[uuid.UUID]


@dataclass(frozen=True)
class ExtractionRunResult:
    created: list[uuid.UUID]
    existing: list[uuid.UUID]
    rejected: list[RejectedCandidate]
    ambiguous_configuration: list[AmbiguousConfigurationEntry]


__all__ = ["AmbiguousConfigurationEntry", "ExtractionRunResult", "RejectedCandidate"]
