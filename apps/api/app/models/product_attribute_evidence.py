"""
ProductAttributeEvidence — extends the Module 5A/5F evidence pattern to
ProductAttribute (the EAV specification-value table, Phase 4B). A
structurally separate table, following the exact precedent
app.models.graph_relationship.GraphRelationship already established:
ProvenanceRecord (Module 5A, frozen — not modified by this table) has a
real CHECK constraint requiring exactly one of company_id/product_id,
and its `field_name` is free text matched against real Company/Product
columns — neither fits ProductAttribute, which is a child EAV row
identified by (product_id, specification_id), not a column. Reuses
ProvenanceStatus and ExtractionMethod directly (imported from
app.models.provenance_record, not redefined), so an attribute claim's
trust state uses the identical OBSERVED/EXTRACTED/CLAIMED/UNDER_REVIEW/
VERIFIED/REJECTED/EXPIRED vocabulary, enforced by the identical rule:
VERIFIED is only ever set by an explicit, human, attributed action —
see app.services.product_attribute_evidence_service.verify_product_attribute_evidence.

Append-only, like RawObservation/ProvenanceRecord: multiple rows may
exist for the same (product_id, specification_id) — one per source —
so multi-source corroboration and conflict are both representable, and
no row is ever deleted or overwritten by a later, disagreeing claim.
ProductAttribute itself remains the single canonical value slot; this
table is the evidence ledger behind it, linked only via
ProductAttribute.latest_evidence_id — a cache pointer set exclusively
by apply_reviewed_attribute_to_product, never the source of truth for
what evidence exists.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.enum_utils import str_enum_values
from app.db.session import Base
from app.models.provenance_record import ExtractionMethod, ProvenanceStatus


class ProductAttributeEvidence(Base):
    __tablename__ = "product_attribute_evidence"
    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "specification_id",
            "raw_observation_id",
            name="uq_product_attribute_evidence_source",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    specification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_specifications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    raw_observation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("raw_observations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # What the source actually said for this attribute — never mutated
    # after creation, exactly like ProvenanceRecord.value_observed.
    value_observed: Mapped[str] = mapped_column(Text, nullable=False)

    extraction_method: Mapped[ExtractionMethod] = mapped_column(
        Enum(
            ExtractionMethod,
            name="extraction_method",
            native_enum=True,
            values_callable=str_enum_values,
        ),
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    status: Mapped[ProvenanceStatus] = mapped_column(
        Enum(
            ProvenanceStatus,
            name="provenance_status",
            native_enum=True,
            values_callable=str_enum_values,
        ),
        nullable=False,
        default=ProvenanceStatus.OBSERVED,
        server_default=ProvenanceStatus.OBSERVED.value,
    )
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Reuses DataConflict (Module 5A) exactly as
    # app.services.graph_service.flag_relationship_conflict already
    # does for relationship-level conflicts — no DataConflict schema
    # change, addressed via the same field_name string convention
    # ("attribute:{specification_id}"), see the service layer.
    conflict_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_conflicts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("verification_documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Free-form, schema-flexible (mirrors RawObservation.raw_content's
    # own JSONB rationale): where in the source this value was found —
    # e.g. {"page": 4, "section": "Performance Curve"}. Populated today
    # by manual entry at the submitter's discretion; the field a future
    # AI extractor would use to record the source location it read the
    # value from (see this table's own module docstring).
    extraction_context: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
