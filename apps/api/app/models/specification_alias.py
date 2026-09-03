"""
SpecificationAlias — deterministic synonym configuration for
ProductSpecification, added for the deterministic PDF specification-
extraction milestone. A label like "Discharge" or "Flow Rate" printed
on a real datasheet must resolve to an existing ProductSpecification
(e.g. "Flow") without hardcoding any category-specific vocabulary into
the extractor (app.extraction.label_matching) — this table is that
configuration, scoped to one specification (and, through it, one
category) at a time.

Deliberately NOT a JSONB column on ProductSpecification, despite that
table's own `enum_options` precedent — the design review for this
milestone considered and rejected that shape. `enum_options` is
authored once, atomically, by whoever defines the specification;
aliases are added incrementally, often by someone other than the
spec's original author, specifically because a *new* document used
unfamiliar wording. That is exactly the shape of fact this codebase
always gives its own row with `created_at` (RawObservation,
ProvenanceRecord, ProductAttributeEvidence) rather than folding into a
bare JSON list with no independent identity of its own.

`alias` is stored exactly as authored (original casing/whitespace) —
normalization (lowercase, trim, collapse whitespace, strip a trailing
colon) happens only at match time, in app.extraction.label_matching,
identically to how `ProductSpecification.name` itself is normalized
for comparison. Never store a pre-normalized value here: normalizing
once at write time would silently diverge the moment the match-time
normalization function changes.

No `created_by` in V1 — deliberate, not an oversight. The existing
specification-authoring endpoints (POST /product-categories,
POST /product-categories/{id}/specifications,
app.api.v1.products.create_category_specification) require only an
authenticated user, not Role.ADMIN. This milestone's extraction
trigger (app.api.v1.spec_extraction) does not wire alias authoring
through that under-protected surface — see that module's own
docstring — so there is no admin-authorized actor to attribute alias
rows to yet. Rows are seeded directly (service/script/fixture) until
that authorization gap is resolved as its own, separate decision.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SpecificationAlias(Base):
    __tablename__ = "specification_aliases"
    __table_args__ = (UniqueConstraint("specification_id", "alias", name="uq_specification_alias"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    specification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_specifications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Matches ProductSpecification.name's own String(120) width — an
    # alias is a synonym for a name, so the same bound applies.
    alias: Mapped[str] = mapped_column(String(120), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


__all__ = ["SpecificationAlias"]
