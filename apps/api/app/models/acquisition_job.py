"""
AcquisitionJob — Module 5B. The controlled job lifecycle for one
collector run against one source. Deliberately does not duplicate or
modify anything from Module 5A (SourceRegistry, RawObservation,
ProvenanceRecord, DataConflict, frozen as approved) — `source_id` is a
new outbound FK to `source_registry`, nothing was added to that table.

Job execution in this phase is synchronous within the request that
creates it (see app.services.acquisition_service) — there is no
background task queue yet, matching this phase's explicit "not
web-scale scheduling" scope. started_at/completed_at are still real,
independently-recorded timestamps (not always equal to created_at),
since validate_config can fail before started_at is ever set.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.enum_utils import str_enum_values
from app.db.session import Base


class AcquisitionJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AcquisitionJob(Base):
    __tablename__ = "acquisition_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_registry.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Matches app.collectors.registry's key space (e.g. "mock") — not a
    # DB enum, deliberately: adding a new collector type is a code
    # change (a new adapter class + registry entry), not a migration,
    # matching this module's own extensibility goal.
    collector_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[AcquisitionJobStatus] = mapped_column(
        Enum(
            AcquisitionJobStatus,
            name="acquisition_job_status",
            native_enum=True,
            values_callable=str_enum_values,
        ),
        nullable=False,
        default=AcquisitionJobStatus.PENDING,
        server_default=AcquisitionJobStatus.PENDING.value,
    )
    # Adapter-specific run configuration — validated by the adapter's
    # own validate_config before use. Never stored raw if it contains
    # anything credential-shaped — see app.collectors.secrets.redact_config,
    # applied by acquisition_service before this column is written.
    requested_scope: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    result_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    skipped_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    failed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Always redacted before being written here — see
    # app.collectors.secrets.redact_config and
    # acquisition_service._safe_error_message.
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
