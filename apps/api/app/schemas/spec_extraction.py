"""Pydantic schemas — deterministic specification extraction milestone."""

import uuid

from pydantic import BaseModel


class ExtractionRunRequest(BaseModel):
    raw_observation_id: uuid.UUID


class RejectedCandidatePublic(BaseModel):
    page: int
    label: str
    reason: str


class AmbiguousConfigurationPublic(BaseModel):
    label: str
    specification_ids: list[uuid.UUID]


class ExtractionRunPublic(BaseModel):
    created: list[uuid.UUID]
    existing: list[uuid.UUID]
    rejected: list[RejectedCandidatePublic]
    ambiguous_configuration: list[AmbiguousConfigurationPublic]
