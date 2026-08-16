"""
Product — Phase 4B. Canonical, shared representation of an industrial
good. Per Phase 4A's governing principle (and this module's own
ABSOLUTE RULE): a Product never belongs to one company — many
Companies reference the same Product via `Offering` (see
app.models.offering). Nothing on this table is company-specific;
company-specific facts (MOQ, lead time, capacity, role) live on
Offering, exactly per Phase 4A Section 2's "Offering is the pivotal
design decision" and this module's own explicit instruction.

`status` starts at DRAFT for every new Product (Phase 4A Section 6) —
there is no admin-review workflow to move it to PUBLISHED yet (the
same deliberately-deferred pattern as VerificationDocument's
verified_by/verified_at, Module 3B, docs/adr/0029). See this module's
completion report for the resulting, explicitly-flagged limitation:
any authenticated user can currently publish a Product directly: no
per-product ownership or moderation model exists yet.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.enum_utils import str_enum_values
from app.db.session import Base

if TYPE_CHECKING:
    from app.models.offering import Offering
    from app.models.product_attribute import ProductAttribute
    from app.models.product_category import ProductCategory


class ProductStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # A simple free-text grouping label (e.g. "XJ-series motors") — NOT
    # the Brand entity Phase 4A Section 2 describes (out of this
    # phase's explicit "Only these" entity list). Deliberately just a
    # string, not a new table, to stay within scope.
    product_family: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Free text, matching Company.industry's existing pattern (Module
    # 3A) — see this file's module docstring for why Industry isn't a
    # linked entity in this phase.
    industry: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    status: Mapped[ProductStatus] = mapped_column(
        Enum(
            ProductStatus, name="product_status", native_enum=True, values_callable=str_enum_values
        ),
        nullable=False,
        default=ProductStatus.DRAFT,
        server_default=ProductStatus.DRAFT.value,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    category: Mapped["ProductCategory"] = relationship(back_populates="products")
    attributes: Mapped[list["ProductAttribute"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    offerings: Mapped[list["Offering"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
