"""
Factory — Module 5F. Confirmed during architecture (Section 1 of
docs/product/phase-5f-industrial-knowledge-graph-architecture.md) that
no Factory entity existed anywhere in this codebase before this
module — Phase 4A only ever discussed the concept. This is the first
real implementation, kept deliberately minimal per this module's own
"do not overbuild Factory management" instruction.

A Factory represents a physical industrial location/asset context —
explicitly distinct from a Company's own registered address
(`Company.country`/`state`/`city`, Module 3A, self-reported/registry-
sourced) and from an Offering's service-coverage location
(`Offering.country`, Module 4B). A Company's registered office and its
factory are frequently different real-world places; this model exists
specifically to stop conflating them, per the architecture's own
Section 9 rule.

Deliberately does NOT include equipment/capacity/machine data in this
first pass — Machine Asset is explicitly deferred (architecture
Section 24); a Factory today is just a located, company-owned/operated
place, nothing more.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Factory(Base):
    __tablename__ = "factories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Required, per this module's own instruction: "Factory must have a
    # clear relationship to Company." No orphaned factories.
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Deliberately the same three-part shape as Company's own
    # country/state/city (Module 3A) — not a shared Location table
    # (architecture Section 9's own conclusion: a new Location entity
    # would add complexity without adding real capability the existing
    # field shape doesn't already provide, for this MVP's actual query
    # needs). A Factory's own country/state/city is independently set
    # here — never inherited from or synced with Company's, since a
    # factory's physical location is exactly the fact this model exists
    # to represent as distinct from the registered office.
    country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
