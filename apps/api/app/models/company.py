"""
Company ORM model — Module 3A ("Company Core"). See
docs/domain/03-core-entities.md for the full business definition and
docs/adr/0022-company-role-naming.md for why `CompanyMember.role` uses a
separate `CompanyRole` enum rather than reusing `app.models.user.Role`.

Deliberate Module 3A simplifications (documented, not accidental — see
docs/adr/0023-module-3a-scope-simplifications.md):
- `industry` is a plain string, not a foreign key into a controlled
  Industry/Category taxonomy (docs/domain/03's `Industry`/`Category`
  entities) — that taxonomy is deferred to the module that actually
  builds Products/Search, since nothing in Module 3A needs it to be
  queryable/controlled yet.
- `verification_status` is a placeholder enum (always `unverified` today)
  standing in for the full `Verification` aggregate
  (docs/domain/03/05) — that's its own future module, not built here.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.enum_utils import str_enum_values
from app.db.session import Base

if TYPE_CHECKING:
    from app.models.company_member import CompanyMember


class CompanyStatus(str, enum.Enum):
    """Mirrors docs/domain/03-core-entities.md's Company lifecycle (Draft → Active → Suspended/Archived)."""

    DRAFT = "draft"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class CompanySize(str, enum.Enum):
    """A small, closed set of employee-count bands — sufficient for Stage 1 filtering/display."""

    MICRO = "1-10"
    SMALL = "11-50"
    MEDIUM = "51-200"
    LARGE = "201-1000"
    ENTERPRISE = "1000+"


class VerificationStatus(str, enum.Enum):
    """
    Placeholder for the full Verification aggregate (docs/domain/03/05,
    a future module). Module 3A only needs a display value — every
    Company starts and stays UNVERIFIED until the real Verification
    module exists to change it.
    """

    UNVERIFIED = "unverified"
    VERIFIED = "verified"


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        Index("ix_companies_name", "name"),
        Index("ix_companies_industry", "industry"),
        Index("ix_companies_city", "city"),
        Index("ix_companies_country", "country"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Deliberately a plain string in Module 3A — see module docstring.
    industry: Mapped[str | None] = mapped_column(String(120), nullable=True)

    website: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    year_established: Mapped[int | None] = mapped_column(Integer, nullable=True)
    company_size: Mapped[CompanySize | None] = mapped_column(
        Enum(CompanySize, name="company_size", native_enum=True, values_callable=str_enum_values),
        nullable=True,
    )
    gst_number: Mapped[str | None] = mapped_column(String(32), nullable=True)

    country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)

    status: Mapped[CompanyStatus] = mapped_column(
        Enum(
            CompanyStatus, name="company_status", native_enum=True, values_callable=str_enum_values
        ),
        default=CompanyStatus.ACTIVE,
        nullable=False,
    )
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(
            VerificationStatus,
            name="company_verification_status",
            native_enum=True,
            values_callable=str_enum_values,
        ),
        default=VerificationStatus.UNVERIFIED,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    members: Mapped[list["CompanyMember"]] = relationship(
        "CompanyMember", back_populates="company", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover — debug convenience only
        return f"<Company id={self.id} slug={self.slug} status={self.status}>"
