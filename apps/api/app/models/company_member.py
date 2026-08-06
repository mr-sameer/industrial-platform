"""
CompanyMember ORM model — the join entity between User and Company,
carrying the company-scoped role. See
docs/domain/03-core-entities.md ("Company Member") and
docs/domain/08-business-rules.md ("a company must have exactly one
Owner") for the business rules this model's constraints enforce.

Naming: `CompanyRole` is deliberately a distinct enum from
`app.models.user.Role` (the platform-level role from Module 2/2.5) — see
docs/adr/0022-company-role-naming.md. A user's platform Role and their
CompanyRole within any given company are independent and both apply.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.enum_utils import str_enum_values
from app.db.session import Base

if TYPE_CHECKING:
    from app.models.company import Company


class CompanyRole(str, enum.Enum):
    """Company-scoped permission level — see docs/domain/09-permission-matrix.md."""

    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class CompanyMemberStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"


class CompanyMember(Base):
    __tablename__ = "company_members"
    __table_args__ = (
        # A user can only hold one membership row per company — re-inviting
        # an existing member should update that row, never create a second.
        UniqueConstraint("company_id", "user_id", name="uq_company_members_company_user"),
        # NOTE: the partial unique index enforcing "exactly one Owner per
        # company" (docs/domain/08-business-rules.md) is deliberately NOT
        # declared here. It's created explicitly by migration 0003
        # (op.create_index with postgresql_where) for real deployments,
        # and by tests/conftest.py's schema-setup fixture for tests — not
        # via this declarative __table_args__ / Base.metadata.create_all.
        # Reason: asyncpg has a client-side type-cache quirk where a
        # partial index predicate referencing an enum literal
        # ("WHERE role = 'owner'") fails with "invalid input value for
        # enum company_role: 'owner'" when the enum type was created
        # moments earlier in the same session/connection — reproducible
        # every time via Base.metadata.create_all over the async engine,
        # never via Alembic (which uses the sync psycopg driver, no such
        # cache). Declaring it here would make every test run hit that
        # failure; creating it out-of-band after a fresh connection (see
        # conftest.py) avoids it while keeping the real migration correct
        # and unchanged.
        Index("ix_company_members_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[CompanyRole] = mapped_column(
        Enum(CompanyRole, name="company_role", native_enum=True, values_callable=str_enum_values),
        nullable=False,
    )
    status: Mapped[CompanyMemberStatus] = mapped_column(
        Enum(
            CompanyMemberStatus,
            name="company_member_status",
            native_enum=True,
            values_callable=str_enum_values,
        ),
        default=CompanyMemberStatus.PENDING,
        nullable=False,
    )
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    company: Mapped["Company"] = relationship("Company", back_populates="members")

    def __repr__(self) -> str:  # pragma: no cover — debug convenience only
        return (
            f"<CompanyMember company_id={self.company_id} user_id={self.user_id} role={self.role}>"
        )
