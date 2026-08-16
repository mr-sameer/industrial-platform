"""Pydantic schemas — Module 5E (Data Quality & Verification Operations)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class FieldQualityEntry(BaseModel):
    field_name: str
    value_observed: str
    status: str
    confidence: float
    risk_level: str
    freshness: str
    has_open_conflict: bool
    provenance_record_id: uuid.UUID
    last_observed_at: datetime
    expires_at: datetime | None


class QualityScore(BaseModel):
    score: float | None
    meaning: str


class EntityQualityReport(BaseModel):
    """Always returns the score bundled with its field-level
    breakdown — never one without the other, per the architecture
    doc's Section 15 rule that a composite score must always ship
    paired with what it summarizes."""

    entity_type: str
    entity_id: uuid.UUID
    fields: list[FieldQualityEntry]
    quality_score: QualityScore


class ReviewQueueItem(BaseModel):
    id: uuid.UUID
    entity_type: str
    company_id: uuid.UUID | None
    product_id: uuid.UUID | None
    field_name: str
    value_observed: str
    status: str
    risk_level: str
    has_open_conflict: bool
    created_at: datetime


class ReviewQueuePage(BaseModel):
    items: list[ReviewQueueItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class RejectRequest(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


class MarkExpiredRequest(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


class LinkEvidenceRequest(BaseModel):
    verification_document_id: uuid.UUID


class ProvenanceRecordWithQuality(BaseModel):
    id: uuid.UUID
    field_name: str
    value_observed: str
    status: str
    confidence: float
    risk_level: str
    freshness: str
    review_note: str | None
    expires_at: datetime | None
    verification_document_id: uuid.UUID | None

    model_config = {"from_attributes": True}
