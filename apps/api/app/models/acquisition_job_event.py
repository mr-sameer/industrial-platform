"""
AcquisitionJobEvent — Module 5B. One row per item a collector run
produced, recording its outcome (created / skipped as a duplicate /
failed). This is also where the job<->RawObservation link lives —
deliberately not added as a column on Module 5A's RawObservation
(frozen, not modified): `raw_observation_id` here is a new outbound FK
from this new table, answering "what acquisition job produced this
observation" without touching Module 5A's schema at all.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.enum_utils import str_enum_values
from app.db.session import Base


class AcquisitionEventOutcome(str, enum.Enum):
    CREATED = "created"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    FAILED = "failed"


class AcquisitionJobEvent(Base):
    __tablename__ = "acquisition_job_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("acquisition_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    outcome: Mapped[AcquisitionEventOutcome] = mapped_column(
        Enum(
            AcquisitionEventOutcome,
            name="acquisition_event_outcome",
            native_enum=True,
            values_callable=str_enum_values,
        ),
        nullable=False,
    )
    external_identifier: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # Set only when outcome == CREATED — a new outbound FK to Module
    # 5A's raw_observations, not a modification of that table.
    raw_observation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("raw_observations.id", ondelete="SET NULL"), nullable=True
    )
    # Always redacted before being written — see app.collectors.secrets.
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
