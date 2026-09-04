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

OCR foundation (approved OCR Architecture Design Proposal, refinement
B): `ocr_result_id` is nullable and NULL for every evidence row created
before this milestone and every non-OCR row created after it —
`raw_observation_id` alone continues to mean exactly what it always
has for those rows. When set, it links this row to the specific
app.models.ocr_result.OCRResult *run* it was extracted from; the
service layer (see
app.services.product_attribute_evidence_service.create_ocr_derived_attribute_evidence)
guarantees `raw_observation_id == ocr_result.raw_observation_id` by
construction — an OCRResult is always a transformation of the same
original document this row's raw_observation_id already points at,
never a different one.

The original 3-column uniqueness (product_id, specification_id,
raw_observation_id) is preserved EXACTLY for non-OCR rows via a partial
index scoped to ocr_result_id IS NULL — the existing idempotent-create
guarantee for manual/rule_based/ai_assisted evidence is unchanged bit
for bit. A second, separate partial index (scoped to ocr_result_id IS
NOT NULL) additionally keys on ocr_result_id, because a second OCR run
against the very same raw_observation_id (same original PDF, better
engine or higher DPI) must be able to produce its OWN evidence row
without colliding with the first run's — while a repeated extraction
pass against the SAME OCRResult remains idempotent, exactly mirroring
the non-OCR guarantee one dimension over.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.enum_utils import str_enum_values
from app.db.session import Base
from app.models.provenance_record import ExtractionMethod, ProvenanceStatus

if TYPE_CHECKING:
    from app.models.ocr_result import OCRResult


class ProductAttributeEvidence(Base):
    __tablename__ = "product_attribute_evidence"
    __table_args__ = (
        # Replaces the original single UniqueConstraint(product_id,
        # specification_id, raw_observation_id) — see this class's own
        # docstring ("OCR foundation") for why a plain 3-column
        # constraint can no longer serve both non-OCR and OCR evidence.
        # ocr_result_id IS NULL / IS NOT NULL are plain-NULL predicates,
        # not enum literals, so these are safe to declare here directly
        # (unlike company_members' partial index — see that model's own
        # comment for the asyncpg/enum-literal quirk this avoids).
        Index(
            "uq_pae_source_manual",
            "product_id",
            "specification_id",
            "raw_observation_id",
            unique=True,
            postgresql_where=text("ocr_result_id IS NULL"),
        ),
        Index(
            "uq_pae_source_ocr",
            "product_id",
            "specification_id",
            "raw_observation_id",
            "ocr_result_id",
            unique=True,
            postgresql_where=text("ocr_result_id IS NOT NULL"),
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
    # NULL for every non-OCR row (manual/rule_based/ai_assisted against
    # a native text layer) — set only when this row's value_observed
    # was extracted from an app.models.ocr_result.OCRResult run. See
    # this class's own "OCR foundation" docstring for the uniqueness
    # implications and the raw_observation_id-consistency invariant.
    ocr_result_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ocr_results.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    # One-directional (no back_populates): OCRResult has no reciprocal
    # collection attribute — nothing in this milestone needs to walk
    # "all evidence derived from this OCR run" via the ORM.
    ocr_result: Mapped["OCRResult | None"] = relationship()
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
