"""
ProductSpecification — Phase 4B. A named, typed attribute definition
scoped to a ProductCategory (e.g. "Power" for Motors, "Flow Rate" for
Pumps). This is the "SpecificationDefinition" entity from Phase 4A
Section 5 — the dynamic specification system: adding a new spec for a
category means inserting one row here, never a schema migration. The
actual per-Product values live on ProductAttribute (a separate table,
deliberately — see that file's docstring).
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.enum_utils import str_enum_values
from app.db.session import Base

if TYPE_CHECKING:
    from app.models.product_attribute import ProductAttribute
    from app.models.product_category import ProductCategory


class SpecificationDataType(str, enum.Enum):
    NUMBER = "number"
    TEXT = "text"
    ENUM = "enum"
    BOOLEAN = "boolean"
    RANGE = "range"


class RiskTier(str, enum.Enum):
    """
    Module 5E addition (docs/product/phase-5e-data-quality-verification-architecture.md
    Section 12): category-level risk tagging, so every value entered
    against a specification inherits its risk tier automatically
    rather than each individual ProductAttribute value needing its own
    classification. Defaults to LOW — a specification is only HIGH-risk
    when a category author deliberately marks it so (e.g. a pressure
    rating, a safety tolerance), matching the architecture's own
    "high-risk by default only for specifications with real-world
    safety/compliance implications" framing, not a blanket default.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ProductSpecification(Base):
    __tablename__ = "product_specifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    datatype: Mapped[SpecificationDataType] = mapped_column(
        Enum(
            SpecificationDataType,
            name="specification_datatype",
            native_enum=True,
            values_callable=str_enum_values,
        ),
        nullable=False,
    )
    # Only meaningful when datatype == ENUM — the fixed set of valid
    # values (e.g. IP Rating's "IP54", "IP65", ...). Stored as JSONB
    # rather than a separate table: this is a small, category-author-
    # defined list, not data that needs its own relational identity.
    enum_options: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Module 5E addition — see RiskTier's own docstring above.
    risk_tier: Mapped[RiskTier] = mapped_column(
        Enum(RiskTier, name="risk_tier", native_enum=True, values_callable=str_enum_values),
        nullable=False,
        default=RiskTier.LOW,
        server_default=RiskTier.LOW.value,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    category: Mapped["ProductCategory"] = relationship(back_populates="specifications")
    attribute_values: Mapped[list["ProductAttribute"]] = relationship(
        back_populates="specification"
    )
