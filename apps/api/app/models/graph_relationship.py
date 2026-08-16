"""
GraphRelationship — Module 5F. Relationship-level evidence, extending
the SAME conceptual system Module 5A's ProvenanceRecord already
established for fields — reusing ProvenanceStatus (imported directly
from app.models.provenance_record, not redefined) so a relationship's
trust state uses the identical OBSERVED/EXTRACTED/CLAIMED/UNDER_REVIEW/
VERIFIED/REJECTED/EXPIRED vocabulary, enforced by the identical rule
(VERIFIED is only ever set by an explicit, human, attributed action —
see app.services.graph_service.verify_relationship).

A DELIBERATE, DOCUMENTED ARCHITECTURAL CHOICE (see this module's own
completion report for the full reasoning): this is a NEW, structurally
separate table — `provenance_records` (Module 5A) is NOT modified, its
schema and CHECK constraint are completely untouched. Given
ProvenanceRecord is depended on by 17 files across every Module
5A-5E component (confirmed by direct inspection before writing this
model), altering its schema to also carry (subject, relationship_type,
object) triples was judged the higher-risk path; a new table sharing
the same enum type and the same verification semantics achieves "the
same conceptual system, not a second competing one" without touching
the foundation every prior Module 5 phase relies on.

Reuses Offering (Module 4B) directly for manufactures/supplies/
distributes/exports/provides_service_for — see architecture Section 3/
17's own conclusion that Offering already IS the graph edge for those
relationship types. This table only covers relationship types nothing
else already represents: owns/operates (Company->Factory) and
has_capability (Company->Capability).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, Float, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.enum_utils import str_enum_values
from app.db.session import Base
from app.models.provenance_record import ProvenanceStatus


class GraphEntityType(str, enum.Enum):
    """Subject/object entity kinds this table's edges can reference.
    Company/Product/Offering (the existing canonical identities, per
    architecture Section 16) intentionally are NOT duplicated here as
    a parallel identity concept — this enum only labels *which* table
    an id column points into, for edges this table actually stores."""

    COMPANY = "company"
    FACTORY = "factory"
    CAPABILITY = "capability"


class RelationshipType(str, enum.Enum):
    """The approved MVP relationship vocabulary NOT already represented
    by Offering.role (Module 4B) — a controlled, closed vocabulary, per
    the architecture's own "no arbitrary relationship creation" rule
    (Section 17). Adding a new relationship type is a deliberate,
    reviewed code change, not a free-text value."""

    OWNS = "owns"
    OPERATES = "operates"
    HAS_CAPABILITY = "has_capability"


class GraphRelationship(Base):
    __tablename__ = "graph_relationships"
    __table_args__ = (
        CheckConstraint(
            "(subject_type = 'company' AND company_subject_id IS NOT NULL)",
            name="ck_graph_relationship_subject_is_company",
        ),
        CheckConstraint(
            "(object_type = 'factory' AND factory_object_id IS NOT NULL AND capability_object_id IS NULL) OR "
            "(object_type = 'capability' AND capability_object_id IS NOT NULL AND factory_object_id IS NULL)",
            name="ck_graph_relationship_exactly_one_object",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    subject_type: Mapped[GraphEntityType] = mapped_column(
        Enum(
            GraphEntityType,
            name="graph_entity_type",
            native_enum=True,
            values_callable=str_enum_values,
        ),
        nullable=False,
    )
    # Every relationship type in this table's current, approved MVP
    # vocabulary (owns/operates/has_capability) originates from
    # Company — confirmed against architecture Section 17's table.
    # A single, non-polymorphic FK column (rather than a generic
    # subject_id with no referential integrity) keeps this genuinely
    # type-safe; extending to a non-Company subject type in a future
    # phase would add a new nullable column the same way, not weaken
    # this one.
    company_subject_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    relationship_type: Mapped[RelationshipType] = mapped_column(
        Enum(
            RelationshipType,
            name="relationship_type",
            native_enum=True,
            values_callable=str_enum_values,
        ),
        nullable=False,
    )

    object_type: Mapped[GraphEntityType] = mapped_column(
        Enum(
            GraphEntityType,
            name="graph_entity_type",
            native_enum=True,
            values_callable=str_enum_values,
        ),
        nullable=False,
    )
    factory_object_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("factories.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    capability_object_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("capabilities.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Reuses provenance_status (Module 5A's real Postgres enum type)
    # directly — see this file's own module docstring for why this is
    # "the same conceptual system," not a redefinition.
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
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.5, server_default="0.5"
    )
    # Mirrors ProvenanceRecord.raw_observation_id exactly — a
    # relationship claim traces back to the same real, unmodified
    # Module 5A RawObservation model an individual field claim would.
    raw_observation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("raw_observations.id", ondelete="SET NULL"), nullable=True
    )
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Mirrors DataConflict (Module 5A, reused unchanged) — a
    # relationship-level conflict is recorded the same way a
    # field-level one is, in the SAME table, not a parallel conflict
    # model.
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
