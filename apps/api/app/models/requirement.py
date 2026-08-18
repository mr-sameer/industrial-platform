"""
Requirement / RequirementSpecificationCriterion — Module 7A-1
(Requirement Intelligence foundation). Persists what
apps/web/src/lib/requirement.ts already computes client-side (the
`RequirementObject` shape) so a requirement can survive a page refresh
and be referenced by a future matching engine — this phase adds NO
matching/ranking logic itself (see app.services.requirement_service's
own docstring for the boundary this maintains).

Deliberately reuses the existing Industrial Taxonomy
(ProductCategory/ProductSpecification, Phase 4B) rather than inventing
a parallel one — `product_category_id`/`specification_id` below are
plain FKs into that real, existing vocabulary, never a new enum or
lookup table. RequirementSpecificationCriterion points at
ProductSpecification (the category-scoped *definition*), not
ProductAttribute (one Product's stored *value* against a definition) —
a criterion is a desired-value predicate over the definition, the same
role ProductAttribute plays for an actual value, never a reference to
one specific product's row.

`certifications` is stored as a free-text JSONB array, NOT a FK/enum
into VerificationDocument.DocumentType — that enum is real but
confirmed India-biased (GST_CERTIFICATE/MSME/BIS alongside more-global
ISO/CE) during this module's own architecture review, and redesigning
it is explicitly out of scope here. Storing free strings keeps
Requirement decoupled from that future redesign rather than binding to
a type that will need to change.

`value` on RequirementSpecificationCriterion is JSONB, not a plain
string: a scalar for `eq`/`gte`/`lte`, a 2-element array for `range`,
an N-element array for `in`. A comma-delimited string was considered
and rejected during this module's own design review — ProductAttribute
(the pattern this was meant to mirror) only ever stores ONE scalar, so
a delimited-string convention for multi-value operators would have
been a new, unprecedented, unindexable micro-format, not a reuse of
anything that exists. JSONB matches the same small-structured-value
choice ProductSpecification.enum_options already makes, stays
app-layer-typed (consistent with ProductAttribute's own explicit EAV
trade-off, Phase 4A Section 12), and remains genuinely queryable
(GIN-indexable) later if a matching engine ever needs it.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.enum_utils import str_enum_values
from app.db.session import Base

if TYPE_CHECKING:
    from app.models.product_category import ProductCategory
    from app.models.product_specification import ProductSpecification
    from app.models.user import User


class RequirementStatus(str, enum.Enum):
    """
    `submitted` is the only status this phase's service layer ever
    sets (POST /requirements IS the act of submission — there is no
    draft-editing flow in 7A-1). `draft` and `archived` are real,
    intentionally-reserved values for later phases (e.g. a future
    Consult flow that saves partial state before the user finishes
    answering clarifying questions) — present in the enum now so no
    migration is needed to introduce them, never set by anything today.
    """

    DRAFT = "draft"
    SUBMITTED = "submitted"
    ARCHIVED = "archived"


class CriterionOperator(str, enum.Enum):
    EQ = "eq"
    GTE = "gte"
    LTE = "lte"
    RANGE = "range"
    IN = "in"


class Requirement(Base):
    __tablename__ = "requirements"
    __table_args__ = (
        # A pure, seam-preserving addition for the future
        # requirement_matching_service (Phase 7A-2) — "find submitted
        # requirements in category X" is that service's first real
        # query. Zero API/contract impact today; added now so no
        # index-only migration is needed later.
        Index("ix_requirements_category_status", "product_category_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    raw_query: Mapped[str] = mapped_column(Text, nullable=False)

    product_category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    industry: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Free-text list — see module docstring for why this is not an FK
    # into VerificationDocument.DocumentType.
    certifications: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    # Captured for a future matching phase, never filtered/matched on
    # in 7A-1 (mirrors the frontend's own current behavior — these
    # fields are already extracted client-side today and already
    # unused for filtering, per this module's own architecture
    # inspection of apps/web/src/lib/requirement.ts).
    quantity: Mapped[str | None] = mapped_column(String(120), nullable=True)
    budget: Mapped[str | None] = mapped_column(String(120), nullable=True)
    timeline: Mapped[str | None] = mapped_column(String(120), nullable=True)

    status: Mapped[RequirementStatus] = mapped_column(
        Enum(
            RequirementStatus,
            name="requirement_status",
            native_enum=True,
            values_callable=str_enum_values,
        ),
        nullable=False,
        default=RequirementStatus.SUBMITTED,
        server_default=RequirementStatus.SUBMITTED.value,
    )
    # 0.0-1.0 — the requirement's OWN epistemic status (how confident
    # the client-side extraction was), passed through as-received.
    # Deliberately NOT a ProvenanceRecord: a Requirement is a user's
    # stated need, not a claim about a Company/Product entity, and
    # ProvenanceRecord's real CHECK constraint requires exactly one of
    # company_id/product_id — confirmed, during this module's own
    # architecture review, to be the same wall Module 6D hit for
    # Census/USITC aggregate data. Not routed through that model for
    # exactly the reason documented there.
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    creator: Mapped["User"] = relationship()
    category: Mapped["ProductCategory | None"] = relationship()
    criteria: Mapped[list["RequirementSpecificationCriterion"]] = relationship(
        back_populates="requirement", cascade="all, delete-orphan"
    )


class RequirementSpecificationCriterion(Base):
    __tablename__ = "requirement_specification_criteria"
    __table_args__ = (
        UniqueConstraint(
            "requirement_id", "specification_id", name="uq_requirement_criterion_specification"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # RESTRICT, not CASCADE — a ProductSpecification being deleted must
    # never silently delete a user's requirement criteria (matching
    # RawObservation's own FK-to-source_registry precedent, Module 5A).
    specification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_specifications.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    operator: Mapped[CriterionOperator] = mapped_column(
        Enum(
            CriterionOperator,
            name="criterion_operator",
            native_enum=True,
            values_callable=str_enum_values,
        ),
        nullable=False,
    )
    # A scalar for eq/gte/lte, a 2-element array for range, an
    # N-element array for in — see module docstring for why this is
    # JSONB rather than a delimited string. Typed Any (not a precise
    # union) since this column holds genuinely dynamic JSON; real shape
    # validation happens at the Pydantic layer
    # (app.schemas.requirement.CriterionValue /
    # RequirementSpecificationCriterionInput's own validator), matching
    # ProductAttribute.value's own precedent of no DB/ORM-level value
    # typing.
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    requirement: Mapped["Requirement"] = relationship(back_populates="criteria")
    specification: Mapped["ProductSpecification"] = relationship()
