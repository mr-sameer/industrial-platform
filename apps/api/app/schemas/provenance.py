"""
Pydantic schemas — Module 5A (Provenance & Source Registry
Foundation). Mirrors app/schemas/product.py's conventions
(from_attributes=True for ORM-backed read models).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.data_conflict import ConflictStatus
from app.models.provenance_record import EntityType, ExtractionMethod, ProvenanceStatus
from app.models.source_registry import CollectionMethod, CollectionPolicyStatus, SourceClass

# ---- SourceRegistry ----


class SourceRegistryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    source_class: SourceClass
    description: str | None = None
    base_url: str | None = Field(default=None, max_length=2048)
    reliability_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    collection_method: CollectionMethod
    geographic_scope: str | None = Field(default=None, max_length=32)


class SourceRegistryUpdate(BaseModel):
    description: str | None = None
    reliability_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    collection_policy_status: CollectionPolicyStatus | None = None
    is_active: bool | None = None


class SourceRegistryPublic(BaseModel):
    id: uuid.UUID
    name: str
    source_class: SourceClass
    description: str | None
    base_url: str | None
    reliability_weight: float
    collection_method: CollectionMethod
    collection_policy_status: CollectionPolicyStatus
    geographic_scope: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---- RawObservation ----


class RawObservationCreate(BaseModel):
    source_id: uuid.UUID
    external_reference: str | None = Field(default=None, max_length=2048)
    raw_content: dict[str, object] = Field(min_length=1)
    content_hash: str = Field(min_length=1, max_length=64)
    collection_method_used: CollectionMethod
    collected_at: datetime


class RawObservationPublic(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    external_reference: str | None
    raw_content: dict[str, object]
    content_hash: str
    collection_method_used: CollectionMethod
    collected_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


# ---- ProvenanceRecord ----


class ProvenanceRecordCreate(BaseModel):
    """
    Creates a provenance record with status OBSERVED or EXTRACTED only
    — VERIFIED is never accepted here, enforced at the schema level as
    the first of several enforcement layers (service layer is the
    second, see provenance_service.create_provenance_record).
    """

    entity_type: EntityType
    company_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    field_name: str = Field(min_length=1, max_length=120)
    raw_observation_id: uuid.UUID
    value_observed: str = Field(min_length=1)
    extraction_method: ExtractionMethod
    confidence: float = Field(ge=0.0, le=1.0)
    status: ProvenanceStatus = ProvenanceStatus.OBSERVED

    def model_post_init(self, __context: object) -> None:
        if self.status not in (
            ProvenanceStatus.OBSERVED,
            ProvenanceStatus.EXTRACTED,
            ProvenanceStatus.CLAIMED,
        ):
            raise ValueError(
                "status must be 'observed', 'extracted', or 'claimed' at creation — "
                "'verified' can only be set via the dedicated verify action"
            )


class ProvenanceRecordPublic(BaseModel):
    id: uuid.UUID
    entity_type: EntityType
    company_id: uuid.UUID | None
    product_id: uuid.UUID | None
    field_name: str
    raw_observation_id: uuid.UUID
    value_observed: str
    extraction_method: ExtractionMethod
    confidence: float
    status: ProvenanceStatus
    verified_by: uuid.UUID | None
    verified_at: datetime | None
    last_observed_at: datetime
    conflict_id: uuid.UUID | None
    review_note: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProvenanceRecordPage(BaseModel):
    items: list[ProvenanceRecordPublic]
    total: int
    page: int
    page_size: int
    total_pages: int


# ---- DataConflict ----


class DataConflictResolve(BaseModel):
    resolution_note: str = Field(min_length=1)


class DataConflictPublic(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID | None
    product_id: uuid.UUID | None
    field_name: str
    status: ConflictStatus
    resolved_by: uuid.UUID | None
    resolved_at: datetime | None
    resolution_note: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DataConflictPage(BaseModel):
    items: list[DataConflictPublic]
    total: int
    page: int
    page_size: int
    total_pages: int


# ---- Apply reviewed evidence to Company (Module 8B) ----


class ApplyToCompanyRequest(BaseModel):
    company_id: uuid.UUID
    overwrite: bool = False


class ApplyToCompanyResponse(BaseModel):
    company_id: uuid.UUID
    field_name: str
    provenance_record: ProvenanceRecordPublic
