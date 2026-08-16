"""
DataConflict — Module 5A. Section 14 (Data Conflicts), scoped exactly
to "foundation" per this module's own instruction — detection and
flagging only. No automatic resolution logic exists anywhere in this
model or its service layer; resolving a conflict is always a distinct,
explicit human action (provenance_service.resolve_conflict), matching
the architecture doc's hard rule: "never silently overwrite conflicting
information."

A conflict is detected when two ProvenanceRecords for the same
(entity, field_name) carry different value_observed — see
provenance_service.create_provenance_record's conflict-detection step.
Both records' conflict_id are set to point here; this table itself
holds no direct pointer back to them (avoiding a circular FK), so
"which records are in conflict" is answered by querying
ProvenanceRecord.conflict_id, not by a field on this table.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.enum_utils import str_enum_values
from app.db.session import Base


class ConflictStatus(str, enum.Enum):
    OPEN = "open"
    RESOLVED = "resolved"


class DataConflict(Base):
    __tablename__ = "data_conflicts"
    __table_args__ = (
        CheckConstraint(
            "(company_id IS NOT NULL AND product_id IS NULL) OR "
            "(company_id IS NULL AND product_id IS NOT NULL)",
            name="ck_data_conflict_exactly_one_entity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=True, index=True
    )
    field_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    status: Mapped[ConflictStatus] = mapped_column(
        Enum(
            ConflictStatus,
            name="conflict_status",
            native_enum=True,
            values_callable=str_enum_values,
        ),
        nullable=False,
        default=ConflictStatus.OPEN,
        server_default=ConflictStatus.OPEN.value,
    )
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
