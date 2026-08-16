"""
EntityResolutionCandidate — Module 5D. The review-queue foundation:
one row per candidate-generation attempt for a raw observation,
recording which signals matched (or didn't), the resulting
resolution_state, and — once a human acts — their decision. This is
the one new table this module introduces; everything else (Company,
SourceRegistry, RawObservation, ProvenanceRecord, DataConflict,
AcquisitionJob) is reused completely unchanged from Modules 3A/5A/5B.

Deliberately does NOT duplicate DataConflict (Module 5A, frozen) —
that model remains the one place *field-level* disagreement between
sources is tracked (Phase 6 of this module's own instructions: "Use
the existing Module 5A conflict infrastructure"). This model tracks a
different, higher-level question: *which* Company (if any) a new
observation should be considered the same real-world entity as — a
prerequisite decision that happens before any field-level
ProvenanceRecord referencing an existing Company can even be created.

`resolution_state` and `decision` are deliberately separate columns:
resolution_state is the SYSTEM's own assessment (computed once, at
candidate-generation time); decision is a HUMAN's later, independent
action. A candidate never modifies canonical Company data by itself —
only a recorded decision does (see app.services.entity_resolution_service).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.enum_utils import str_enum_values
from app.db.session import Base


class ResolutionState(str, enum.Enum):
    """
    The system's own computed assessment — see
    app.entity_resolution.matching for the deterministic rules that
    produce this. Never an automatic action by itself (Phase 9's
    safety principle: "It is NOT acceptable to silently merge two
    different companies" — restated as this whole model's governing
    constraint, not just a comment).
    """

    NEW = "new"
    AUTO_MATCH = "auto_match"
    REVIEW_REQUIRED = "review_required"
    NO_MATCH = "no_match"


class ResolutionDecision(str, enum.Enum):
    """A human reviewer's independent action — always required before
    any canonical Company data is touched, regardless of
    resolution_state (including AUTO_MATCH — see this module's own
    completion report for why even the system's highest-confidence
    state still requires an explicit decision in this phase)."""

    CONFIRM_MATCH = "confirm_match"
    REJECT_MATCH = "reject_match"
    CREATE_NEW = "create_new"


class EntityResolutionCandidate(Base):
    __tablename__ = "entity_resolution_candidates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_observation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("raw_observations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Null when resolution_state is NEW or NO_MATCH (no existing
    # Company is being proposed as a match).
    candidate_company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    resolution_state: Mapped[ResolutionState] = mapped_column(
        Enum(
            ResolutionState,
            name="resolution_state",
            native_enum=True,
            values_callable=str_enum_values,
        ),
        nullable=False,
    )
    # A list of individually-evaluated signals (never a single blended
    # numeric score — see app.entity_resolution.matching's own
    # docstring for why), e.g.
    # [{"signal": "cin", "matched": true, "strength": "strong"}, ...].
    match_signals: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)

    decision: Mapped[ResolutionDecision | None] = mapped_column(
        Enum(
            ResolutionDecision,
            name="resolution_decision",
            native_enum=True,
            values_callable=str_enum_values,
        ),
        nullable=True,
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
