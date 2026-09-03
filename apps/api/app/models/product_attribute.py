"""
ProductAttribute — Phase 4B. The actual specification VALUE for one
Product (e.g. Product X's "Power" = "5.5 kW"). Deliberately a separate
table from ProductSpecification (the definition): this is Phase 4A
Section 5's Entity-Attribute-Value pattern. `value` is always stored as
a string regardless of the specification's declared `datatype` —
type enforcement (number parsing, enum-membership checking) is an
application-layer concern (see app.services.product_service), not a
database-column-type concern. This is the EAV trade-off Phase 4A
Section 12 names explicitly: schema flexibility over database-level
type safety.

`latest_evidence_id` (additive) is a convenience/cache pointer only —
"which ProductAttributeEvidence row is currently backing this value,"
set exclusively by
app.services.product_attribute_evidence_service.apply_reviewed_attribute_to_product.
It is never the source of truth for what evidence exists for this
attribute (the full, append-only ledger lives entirely in
product_attribute_evidence — see that model's own docstring); a NULL
value here means only "no evidence trail was applied," never "no
evidence exists."
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.product_specification import ProductSpecification


class ProductAttribute(Base):
    __tablename__ = "product_attributes"
    __table_args__ = (
        UniqueConstraint("product_id", "specification_id", name="uq_product_attribute"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    specification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_specifications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    value: Mapped[str] = mapped_column(String(500), nullable=False)
    latest_evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_attribute_evidence.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    product: Mapped["Product"] = relationship(back_populates="attributes")
    specification: Mapped["ProductSpecification"] = relationship(back_populates="attribute_values")
