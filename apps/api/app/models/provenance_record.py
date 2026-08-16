"""
ProvenanceRecord — Module 5A. Section 4 (Source Provenance) made
concrete: the record that answers, for one field on one entity, where
the value came from, when, by what method, with what confidence, and
whether it's been independently verified.

This is where the entity link lives — deliberately not on
RawObservation (see that model's docstring: raw collection precedes
entity resolution). A ProvenanceRecord is what a (future, not-this-
phase) entity-resolution step would create once a raw observation has
been matched to a real Company or Product.

THE CORE ENFORCEMENT POINT: `status` distinguishes OBSERVED / EXTRACTED
/ VERIFIED / CLAIMED — per the architecture doc's Section 11, these are
four genuinely different claims that must never be collapsed. Nothing
in this model or its service layer (app.services.provenance_service)
ever transitions a record to VERIFIED as a side effect of creation —
verification is always a distinct, explicit action
(`provenance_service.verify_provenance_record`), requiring a real
`verified_by` actor. See that service function's own docstring for the
enforcement mechanism.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.enum_utils import str_enum_values
from app.db.session import Base


class EntityType(str, enum.Enum):
    """
    A convenience/derived field, not the sole mechanism linking a
    ProvenanceRecord to its entity — see company_id/product_id below,
    which carry real foreign-key referential integrity. This column
    exists so a query can filter "all Company provenance" or "all
    Product provenance" without inspecting which FK column is set.
    """

    COMPANY = "company"
    PRODUCT = "product"


class ExtractionMethod(str, enum.Enum):
    MANUAL = "manual"
    RULE_BASED = "rule_based"
    AI_ASSISTED = "ai_assisted"


class ProvenanceStatus(str, enum.Enum):
    """
    The architecture doc's Section 11 distinction, exactly as
    specified: four genuinely different claims. OBSERVED and EXTRACTED
    are set at creation time; VERIFIED is only ever set by
    provenance_service.verify_provenance_record, never automatically.
    CLAIMED is for company self-submission (Section 12) — not built in
    this phase's scope, but a valid status value future work can use
    without a schema change.

    UNDER_REVIEW / REJECTED / EXPIRED — added in Module 5E
    (docs/product/phase-5e-data-quality-verification-architecture.md
    Section 8), the one explicitly-sanctioned exception to "do not
    modify Module 5A" (per that module's own approval ticket's "Most
    Important Architectural Decision" section). UNDER_REVIEW sits
    between OBSERVED/EXTRACTED/CLAIMED and VERIFIED — a reviewer has
    picked this up but not yet decided (app.services.data_quality_service
    is the only code that sets it). REJECTED is a terminal state a
    reviewer reaches instead of VERIFIED. EXPIRED is reachable only
    from VERIFIED, time- or event-triggered — a claim that was once
    confirmed but whose evidence has lapsed, distinct from both
    VERIFIED and REJECTED.
    """

    OBSERVED = "observed"
    EXTRACTED = "extracted"
    VERIFIED = "verified"
    CLAIMED = "claimed"
    UNDER_REVIEW = "under_review"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ProvenanceRecord(Base):
    __tablename__ = "provenance_records"
    __table_args__ = (
        CheckConstraint(
            "(company_id IS NOT NULL AND product_id IS NULL) OR "
            "(company_id IS NULL AND product_id IS NOT NULL)",
            name="ck_provenance_exactly_one_entity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    entity_type: Mapped[EntityType] = mapped_column(
        Enum(
            EntityType,
            name="provenance_entity_type",
            native_enum=True,
            values_callable=str_enum_values,
        ),
        nullable=False,
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Free text, not an enum — Company/Product each have many fields
    # (Section 1 of the architecture doc catalogued them) and hardcoding
    # an exhaustive field-name enum here would need a migration every
    # time either model gains a field. Matches Section 9's extensibility
    # principle: this is a per-value distinction, not a schema one.
    field_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    raw_observation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("raw_observations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # What the source actually said for this field — may differ from
    # whatever is currently stored on the canonical Company/Product row
    # (this module does not write to Company/Product at all — see this
    # module's own completion report for why that's a deliberate
    # Module 5A scope boundary, not an oversight).
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
    # 0.0-1.0 — Section 4/10's confidence score, reflecting extraction
    # method reliability combined with source reliability
    # (source_registry.reliability_weight) at creation time.
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

    # Distinct from raw_observations.collected_at (Section 4: "when was
    # it collected" vs. "when was it last observed"). At creation these
    # are equal; a future re-observation (Section 13, not this phase)
    # would update this field on the existing ProvenanceRecord while
    # raw_observations gains a new, separate immutable row.
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Set by provenance_service when a conflicting value is detected
    # for the same (entity, field) — see DataConflict. Null when this
    # record has no open conflict.
    conflict_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_conflicts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # --- Module 5E additions (docs/product/phase-5e-data-quality-verification-architecture.md) ---
    # Section 5: a proposed field for non-document claims with a
    # natural expiry — for a claim backed by a VerificationDocument,
    # this is expected to mirror that document's own expiry_date
    # (app.services.data_quality_service keeps them in sync); for a
    # claim with no document, this lets a reviewer set an expiry
    # directly (e.g. "re-check this in 90 days").
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Section 18: the WHY behind a review decision (approve/reject/
    # mark-stale) — never set at creation, only by
    # data_quality_service's review-decision functions.
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Section 9: the evidence link the architecture doc identified as
    # missing — "a document existing is never, by itself, proof," so
    # this column records *which* document a reviewer considered, not
    # that the claim is therefore true. One document per record in
    # this first pass — a real, documented scoping choice (see this
    # module's own completion report), not a claim that a claim can
    # never have multiple supporting documents.
    verification_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("verification_documents.id", ondelete="SET NULL"),
        nullable=True,
    )
