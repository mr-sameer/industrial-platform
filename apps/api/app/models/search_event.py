"""
Search telemetry — Module 7B (Search Telemetry). Two tables:
search_events, search_result_candidates.

This module records FACTS ONLY about what
app.services.requirement_matching_service.compute_matches actually
computed and what app.api.v1.requirements actually returned for a
given execution — it never recomputes, re-scores, or re-derives
anything, and it never modifies that service. See
app.services.search_telemetry_service for the single write path.

HISTORICAL INDEPENDENCE (the reason both snapshot columns exist):
a SearchEvent/SearchResultCandidate row must keep telling the truth
about what ForgeX returned at search time even after the live
Requirement, Offering, Company, or Product rows it referenced are
later edited or removed. `requirement_snapshot` and `result_snapshot`
are therefore the durable source of truth; `requirement_id` and
`offering_id` are live-reference conveniences only, both nullable via
ON DELETE SET NULL (never CASCADE) so a later deletion of what they
point to can never take the historical row down with it. Confirmed
against the current repository: no delete endpoint exists for
Requirement or Offering today, and User deletion (the one real
privacy/retention lever that does cascade, via
Requirement.created_by/SearchEvent.created_by -> users.id CASCADE) is
unaffected by this choice either way.

Append-only: neither table has an `updated_at` column, and nothing in
this codebase should ever UPDATE a row here after creation.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.offering import Offering
    from app.models.requirement import Requirement
    from app.models.user import User


class SearchEvent(Base):
    """
    One row per real execution of
    requirement_matching_service.compute_matches (today, exclusively
    triggered by GET /requirements/{id}/matches). Merges what the
    approved design called SearchEvent + SearchResultSet into a single
    table — the two were always 1:1, written together, with no
    independent lifecycle, so splitting them added a join for no
    benefit.
    """

    __tablename__ = "search_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # SET NULL, not CASCADE — see module docstring. Nullable because a
    # historical search fact must be able to outlive the Requirement
    # row it was executed against.
    requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("requirements.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # CASCADE (unchanged from every other created_by column in this
    # codebase, e.g. Requirement.created_by) — this is the real
    # privacy/retention lever: deleting a User's account removes their
    # search telemetry along with everything else of theirs.
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Promoted column (mirrors RawObservation's own promoted-field-
    # alongside-JSONB-blob precedent) — Requirement.raw_query already
    # exists and is non-nullable, so this is real captured data, never
    # invented.
    raw_query_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Immutable copy of the Requirement's structured state at search
    # time: raw_query, product_category_id, industry, country, state,
    # city, certifications, quantity, budget, timeline,
    # extraction_confidence, criteria (list of specification_id/
    # operator/value). Built once at write time from the already-loaded
    # Requirement object handed to the service — never re-read later.
    requirement_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # "computed" | "category_required" — plain string, matching
    # requirement_matching_service.MatchesResult.status's own
    # deliberately-untyped status field. Not upgraded to a Postgres
    # enum here; that would be a semantic decision 7A-2 itself didn't
    # make, and this module must not change 7A-2 semantics.
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    total_candidates_considered: Mapped[int] = mapped_column(Integer, nullable=False)
    more_candidates_may_exist: Mapped[bool] = mapped_column(Boolean, nullable=False)
    excluded_for_hard_criteria: Mapped[int] = mapped_column(Integer, nullable=False)
    returned_count: Mapped[int] = mapped_column(Integer, nullable=False)

    searched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    requirement: Mapped["Requirement | None"] = relationship()
    creator: Mapped["User"] = relationship()
    candidates: Mapped[list["SearchResultCandidate"]] = relationship(
        back_populates="search_event", cascade="all, delete-orphan"
    )


class SearchResultCandidate(Base):
    """
    One row per candidate actually present in a given search's
    `matches` list (surviving/returned candidates only — an excluded
    candidate is reflected solely in SearchEvent.excluded_for_hard_criteria,
    the same "counted, not detailed" boundary
    requirement_matching_service itself draws; per-excluded-candidate
    detail is explicitly future Data Gap Engine work, not this
    module's).
    """

    __tablename__ = "search_result_candidates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    search_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("search_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # SET NULL — see module docstring; a candidate row must survive
    # the later deletion of the Offering it was scored against (no
    # such delete path exists today, but the row's own
    # `result_snapshot` is the source of truth regardless).
    offering_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("offerings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    # The exact RequirementMatchCandidate payload already built by
    # app.api.v1.requirements._to_match_dto for this candidate
    # (company/product summary, all four signals, score_breakdown) —
    # stored verbatim, never re-derived from live Company/Offering/
    # Product/ProductAttribute state on read.
    result_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    search_event: Mapped["SearchEvent"] = relationship(back_populates="candidates")
    offering: Mapped["Offering | None"] = relationship()
