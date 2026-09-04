"""
OCRResult — V1 OCR foundation (design: OCR Architecture Design Proposal,
approved refinements A/B). A dedicated entity (Option B), subordinate to
and always linked back to the RawObservation holding the original
document — never a peer/replacement source. Represents one OCR *run*
(a specific engine/version/render-DPI combination) against one page of
one RawObservation; deliberately page-scoped, not document-scoped,
since Test 3 established that machine-readability can vary by page
within a single PDF.

Append-only, like RawObservation itself: no update endpoint, no
`updated_at` — a re-run with a better engine or higher DPI is always a
NEW row (see app.services.ocr_result_service.get_or_create_ocr_result),
never a mutation of an old one. This is what lets an auditor later see
the exact OCR text a human verification decision was made against,
even after a better engine ships.

`confidence` is a single required page-level/native-engine score in
V1. `confidence_detail` is a reserved, nullable, currently-unused seam
for a future span/region-level confidence breakdown (e.g.
{"spans": [...]});  populating it later is an application-level change
against an already-existing column, not a new migration — deliberately
NOT populated or read anywhere in V1 (table/region OCR is out of
scope for this milestone).

Rendered page images are NOT represented here or anywhere in the
database — they're a regenerable cache artifact keyed by
(RawObservation.content_hash, page_number, render_dpi, renderer
name/version), per the approved design. Only `render_dpi` (the
parameter that actually affects OCR input quality) and free-form
`render_params` (renderer name/version, color mode, etc.) are recorded
here, for reproducibility/audit — not the image itself.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class OCRResult(Base):
    __tablename__ = "ocr_results"
    __table_args__ = (
        Index("ix_ocr_results_raw_observation_page", "raw_observation_id", "page_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Always the ORIGINAL document's RawObservation — an OCRResult is a
    # derived transformation of it, never a new source in its own
    # right. RESTRICT mirrors every other FK into raw_observations
    # (ProductAttributeEvidence.raw_observation_id, ProvenanceRecord's).
    raw_observation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("raw_observations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Full-page OCR text only — no per-region/table structure in V1
    # (see this module's own docstring and confidence_detail below).
    text: Mapped[str] = mapped_column(Text, nullable=False)

    # Native/aggregate engine confidence for this page, 0.0-1.0.
    # Combined with deterministic-extraction confidence as a CEILING
    # (see app.extraction.ocr_confidence) before it ever reaches
    # ProductAttributeEvidence.confidence — never read directly at
    # verify time.
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    # Reserved for future span/region-level confidence. Unused in V1 —
    # always NULL. See module docstring.
    confidence_detail: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    engine_name: Mapped[str] = mapped_column(String(120), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(60), nullable=False)

    render_dpi: Mapped[int] = mapped_column(Integer, nullable=False)
    # Free-form: renderer name/version, color mode, etc. — kept
    # flexible instead of growing more columns for incidental
    # rendering metadata (mirrors RawObservation.raw_content's own
    # JSONB rationale).
    render_params: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
