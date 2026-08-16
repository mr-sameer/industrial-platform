"""
ProductCategory — Phase 4B. A single-parent tree node in the Industrial
Taxonomy, scoped exactly to what Phase 4A's architecture document
(docs/product/phase-4a-industrial-product-graph-architecture.md,
Section 4) calls for: variable depth, one parent per category. Industry
is deliberately NOT a field here — Phase 4A Section 3 explains why
Industry is modeled as a separate, many-to-many cross-cutting dimension
rather than folded into this tree; for this phase, `industry` lives as
a free-text field directly on `Product` (matching `Company.industry`'s
existing pattern, Module 3A) rather than introducing a full Industry
entity, which Phase 4B's own scope ("Only these" entities) doesn't
include.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.product_specification import ProductSpecification


class ProductCategory(Base):
    __tablename__ = "product_categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    parent: Mapped["ProductCategory | None"] = relationship(remote_side=[id])
    products: Mapped[list["Product"]] = relationship(back_populates="category")
    specifications: Mapped[list["ProductSpecification"]] = relationship(back_populates="category")
