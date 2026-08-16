"""
Offering — Phase 4B. The bridge between a Company and a Product, per
this module's ABSOLUTE RULE: "one Product can have 100,000 Companies
without duplicating Product data. Offerings are the bridge." Everything
company-specific — role, MOQ, lead time, capacity, country,
verification status — lives here, never on Product.

`role` is per Offering, not per Company (explicit instruction) — this
is a deliberate refinement of Company.business_type (Module 3A), which
is company-wide. A company can be a MANUFACTURER for one Product and a
DISTRIBUTOR for another; that distinction is only expressible at the
Offering level.

`verification_status` here is NOT the same thing as Company's real,
live-computed Module 3B verification score — it's a simple, honest
status flag with no scoring logic behind it (no admin-review workflow
sets it to VERIFIED today, same deliberate-placeholder pattern as
VerificationDocument.verified_by/verified_at). Never conflate the two
in application code or documentation — see this module's completion
report for the explicit distinction.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.enum_utils import str_enum_values
from app.db.session import Base

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.product import Product


class OfferingRole(str, enum.Enum):
    MANUFACTURER = "manufacturer"
    SUPPLIER = "supplier"
    DISTRIBUTOR = "distributor"
    EXPORTER = "exporter"
    SERVICE_PROVIDER = "service_provider"


class OfferingVerificationStatus(str, enum.Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"


class OfferingStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class Offering(Base):
    __tablename__ = "offerings"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "product_id", "role", name="uq_offering_company_product_role"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[OfferingRole] = mapped_column(
        Enum(OfferingRole, name="offering_role", native_enum=True, values_callable=str_enum_values),
        nullable=False,
    )
    # Free text throughout (moq/lead_time/capacity) — matching the
    # rest of this codebase's existing pattern for real-world values
    # that carry units and don't need numeric queryability yet (e.g.
    # Company.company_size). Phase 4A Section 8 explicitly designed
    # these as *filters*, not ranking weights, for a future
    # requirement-matching consumer — string storage doesn't block
    # that, since simple presence/absence and substring checks work
    # fine as filters too.
    moq: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lead_time: Mapped[str | None] = mapped_column(String(120), nullable=True)
    capacity: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Per-Offering, not copied from Company.country — a company could
    # export from a different country than its registered headquarters
    # (Phase 4A Section 2's Offering design).
    country: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    verification_status: Mapped[OfferingVerificationStatus] = mapped_column(
        Enum(
            OfferingVerificationStatus,
            name="offering_verification_status",
            native_enum=True,
            values_callable=str_enum_values,
        ),
        nullable=False,
        default=OfferingVerificationStatus.UNVERIFIED,
        server_default=OfferingVerificationStatus.UNVERIFIED.value,
    )
    status: Mapped[OfferingStatus] = mapped_column(
        Enum(
            OfferingStatus,
            name="offering_status",
            native_enum=True,
            values_callable=str_enum_values,
        ),
        nullable=False,
        default=OfferingStatus.ACTIVE,
        server_default=OfferingStatus.ACTIVE.value,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    company: Mapped["Company"] = relationship(back_populates="offerings")
    product: Mapped["Product"] = relationship(back_populates="offerings")
