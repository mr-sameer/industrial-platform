"""
Capability — Module 5F, architecture Section 7. A small, fixed,
extensible controlled vocabulary — not a giant taxonomy built ahead
of evidence, matching this codebase's established "configuration, not
code, and only what's actually needed" discipline (Phase 5's general
architecture document, Section 9).

A Company's `has_capability` edge to a Capability node carries its own
verification state (app.models.graph_relationship.GraphRelationship) —
this table only defines *what a capability is called*, never whether
any given company actually has it. A company claiming a capability is
never conflated with ForgeX having verified it, per the architecture's
own Section 7 rule.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Capability(Base):
    __tablename__ = "capabilities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
