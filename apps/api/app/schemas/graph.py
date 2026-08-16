"""Pydantic schemas — Module 5F (Industrial Knowledge Graph)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.graph_relationship import GraphEntityType, RelationshipType
from app.models.provenance_record import ProvenanceStatus


class FactoryCreate(BaseModel):
    company_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)
    country: str | None = None
    state: str | None = None
    city: str | None = None


class FactoryPublic(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    country: str | None
    state: str | None
    city: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CapabilityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class CapabilityPublic(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class GraphRelationshipCreate(BaseModel):
    company_subject_id: uuid.UUID
    relationship_type: RelationshipType
    object_type: GraphEntityType
    factory_object_id: uuid.UUID | None = None
    capability_object_id: uuid.UUID | None = None
    status: ProvenanceStatus = ProvenanceStatus.OBSERVED
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    raw_observation_id: uuid.UUID | None = None

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


class GraphRelationshipPublic(BaseModel):
    id: uuid.UUID
    subject_type: GraphEntityType
    company_subject_id: uuid.UUID | None
    relationship_type: RelationshipType
    object_type: GraphEntityType
    factory_object_id: uuid.UUID | None
    capability_object_id: uuid.UUID | None
    status: ProvenanceStatus
    confidence: float
    raw_observation_id: uuid.UUID | None
    verified_by: uuid.UUID | None
    verified_at: datetime | None
    review_note: str | None
    conflict_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RelationshipRejectRequest(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


class OfferingEdgePublic(BaseModel):
    """The Offering-derived edges (manufactures/supplies/distributes/
    exports/provides_service_for) — read-only, reusing Offering
    (Module 4B, unmodified) directly rather than duplicating it into
    graph_relationships. See architecture Section 3/17."""

    offering_id: uuid.UUID
    company_id: uuid.UUID
    product_id: uuid.UUID
    relationship_type: str  # derived from Offering.role, e.g. "manufactures"
    moq: str | None
    lead_time: str | None
    capacity: str | None
    country: str | None
    status: str


class CompanyGraphView(BaseModel):
    """The unified traversal view — Offering-derived edges plus
    graph_relationships edges, presented consistently regardless of
    which underlying table they came from."""

    company_id: uuid.UUID
    offering_edges: list[OfferingEdgePublic]
    relationship_edges: list[GraphRelationshipPublic]
