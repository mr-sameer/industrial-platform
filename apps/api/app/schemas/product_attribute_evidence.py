"""
Pydantic schemas — ProductAttribute evidence mechanism. Mirrors
app/schemas/provenance.py's conventions (from_attributes=True for
ORM-backed read models, a schema-level guard against creating evidence
already VERIFIED, matching ProvenanceRecordCreate/GraphRelationshipCreate
exactly).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.provenance_record import ExtractionMethod, ProvenanceStatus

# ---- ProductAttributeEvidence ----


class ProductAttributeEvidenceCreate(BaseModel):
    """
    Creates one source's evidence claim for one (product, specification)
    pair. Only OBSERVED/EXTRACTED/CLAIMED may be submitted at creation —
    VERIFIED is never accepted here (enforced below, and re-affirmed as
    a second, independent guard in
    app.services.product_attribute_evidence_service.create_attribute_evidence),
    regardless of extraction_method — an ai_assisted claim has no more
    authority at creation time than a manual one.
    """

    product_id: uuid.UUID
    specification_id: uuid.UUID
    raw_observation_id: uuid.UUID
    value_observed: str = Field(min_length=1)
    extraction_method: ExtractionMethod
    confidence: float = Field(ge=0.0, le=1.0)
    status: ProvenanceStatus = ProvenanceStatus.OBSERVED
    # Free-form source-location metadata (page/section/URL fragment) —
    # see the model's own docstring. Optional: manual entries commonly
    # omit it.
    extraction_context: dict[str, object] | None = None
    verification_document_id: uuid.UUID | None = None

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


class ProductAttributeEvidencePublic(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    specification_id: uuid.UUID
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
    verification_document_id: uuid.UUID | None
    extraction_context: dict[str, object] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProductAttributeEvidencePage(BaseModel):
    items: list[ProductAttributeEvidencePublic]
    total: int
    page: int
    page_size: int
    total_pages: int


class ProductAttributeEvidenceRejectRequest(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


class ApplyAttributeEvidenceResponse(BaseModel):
    product_id: uuid.UUID
    specification_id: uuid.UUID
    value: str
    evidence: ProductAttributeEvidencePublic
