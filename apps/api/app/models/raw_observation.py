"""
RawObservation — Module 5A. Section 5 (Raw Data vs. Canonical Data):
an immutable, source-stamped capture. Append-only by convention — this
module provides no update endpoint for these rows; a re-observation is
always a new row, never a mutation of an old one, per Section 5's own
reasoning (auditability, re-processing, conflict resolution all depend
on the original capture never being overwritten).

Deliberately carries no entity link (no company_id/product_id) — per
Section 6's pipeline ordering, raw collection happens *before* entity
resolution. A RawObservation may exist with nothing in ForgeX's
canonical data resolved to it yet. ProvenanceRecord (see that model)
is what bridges a raw observation to a resolved entity+field, once
that resolution has happened — never this model directly.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.enum_utils import str_enum_values
from app.db.session import Base
from app.models.source_registry import CollectionMethod


class RawObservation(Base):
    __tablename__ = "raw_observations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_registry.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # The specific location/reference within the source — a URL, a
    # registry record ID, a document reference. Distinct from
    # source_registry.base_url, which is the source *instance* as a
    # whole (e.g. "acme-motors.com"), not this one specific capture
    # (e.g. "acme-motors.com/products/xj-450").
    external_reference: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # JSONB rather than plain text: raw captures are frequently
    # structured (an API response, a parsed registry record) even
    # before ForgeX's own extraction step runs — storing them as JSONB
    # keeps that structure queryable rather than flattening it
    # prematurely into a string.
    raw_content: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    # Idempotency key material (Section 2/23): source_id + content_hash
    # lets a retried collection job recognize "I already captured this
    # exact content" without re-parsing raw_content itself.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    collection_method_used: Mapped[CollectionMethod] = mapped_column(
        Enum(
            CollectionMethod,
            name="collection_method",
            native_enum=True,
            values_callable=str_enum_values,
        ),
        nullable=False,
    )
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
