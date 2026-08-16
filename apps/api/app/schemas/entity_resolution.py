"""Pydantic schemas — Module 5D (Data Normalization & Entity Resolution)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.entity_resolution_candidate import ResolutionDecision, ResolutionState


class CandidateGenerateRequest(BaseModel):
    raw_observation_id: uuid.UUID


class MatchSignalPublic(BaseModel):
    signal: str
    matched: bool
    strength: str
    detail: str


class EntityResolutionCandidatePublic(BaseModel):
    id: uuid.UUID
    raw_observation_id: uuid.UUID
    candidate_company_id: uuid.UUID | None
    resolution_state: ResolutionState
    match_signals: list[MatchSignalPublic]
    explanation: str
    decision: ResolutionDecision | None
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class EntityResolutionCandidatePage(BaseModel):
    items: list[EntityResolutionCandidatePublic]
    total: int
    page: int
    page_size: int
    total_pages: int


class DecisionRequest(BaseModel):
    decision: ResolutionDecision
    note: str | None = Field(default=None, max_length=2000)
