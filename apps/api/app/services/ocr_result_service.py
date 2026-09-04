"""
OCRResult service — V1 persistence/service foundation only (approved OCR
Architecture Design Proposal). No OCR engine is invoked here: callers
(a future rasterize-and-OCR pipeline, or tests using fake/mock OCR
output) supply already-produced text/confidence; this module's job is
only to persist that output correctly and idempotently, never to
produce it.

get_or_create_ocr_result is the intended entry point for a future
extraction pipeline: it treats (raw_observation_id, page_number,
engine_name, engine_version, render_dpi) as the identity of one OCR
*run*, and reuses an existing run's result rather than creating a
duplicate — unless the caller explicitly asks to force a fresh run
(e.g. re-processing after a known engine bugfix at the same version).
This is an application-level idempotency check, not a DB uniqueness
constraint (see this module's own docstring rationale in the OCR
Architecture Design Proposal: a hard DB constraint on this tuple would
be too rigid for that exact "same params, deliberately forced re-run"
case).

Every created row is immutable thereafter — there is no update
function in this module, matching RawObservation/ProductAttributeEvidence's
own append-only convention, and letting a later, better-engine run
coexist as a NEW row rather than overwriting the old one (see
app.models.ocr_result.OCRResult's own docstring).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ocr_result import OCRResult
from app.models.raw_observation import RawObservation

__all__ = [
    "RawObservationNotFoundForOcrResultError",
    "create_ocr_result",
    "get_or_create_ocr_result",
    "get_ocr_result",
]


class RawObservationNotFoundForOcrResultError(Exception):
    pass


async def get_ocr_result(db: AsyncSession, ocr_result_id: uuid.UUID) -> OCRResult | None:
    result = await db.execute(select(OCRResult).where(OCRResult.id == ocr_result_id))
    return result.scalar_one_or_none()


async def create_ocr_result(
    db: AsyncSession,
    *,
    raw_observation_id: uuid.UUID,
    page_number: int,
    text: str,
    confidence: float,
    engine_name: str,
    engine_version: str,
    render_dpi: int,
    confidence_detail: dict[str, object] | None = None,
    render_params: dict[str, object] | None = None,
) -> OCRResult:
    """Unconditionally creates a new OCRResult row. Prefer
    get_or_create_ocr_result for normal pipeline use — this is the
    primitive it (and a caller that has already decided to force a
    fresh run) builds on."""
    observation_result = await db.execute(
        select(RawObservation).where(RawObservation.id == raw_observation_id)
    )
    if observation_result.scalar_one_or_none() is None:
        raise RawObservationNotFoundForOcrResultError(str(raw_observation_id))

    ocr_result = OCRResult(
        raw_observation_id=raw_observation_id,
        page_number=page_number,
        text=text,
        confidence=confidence,
        confidence_detail=confidence_detail,
        engine_name=engine_name,
        engine_version=engine_version,
        render_dpi=render_dpi,
        render_params=render_params,
    )
    db.add(ocr_result)
    await db.commit()
    await db.refresh(ocr_result)
    return ocr_result


async def get_or_create_ocr_result(
    db: AsyncSession,
    *,
    raw_observation_id: uuid.UUID,
    page_number: int,
    text: str,
    confidence: float,
    engine_name: str,
    engine_version: str,
    render_dpi: int,
    confidence_detail: dict[str, object] | None = None,
    render_params: dict[str, object] | None = None,
    force_reprocess: bool = False,
) -> OCRResult:
    """Reuses an existing OCRResult for the same (raw_observation_id,
    page_number, engine_name, engine_version, render_dpi) tuple unless
    force_reprocess is True — see this module's own docstring. text/
    confidence/confidence_detail/render_params passed here are only
    used if a new row actually gets created; they are NOT used to
    "update" a reused row (OCRResult rows are never mutated)."""
    if not force_reprocess:
        existing_result = await db.execute(
            select(OCRResult).where(
                OCRResult.raw_observation_id == raw_observation_id,
                OCRResult.page_number == page_number,
                OCRResult.engine_name == engine_name,
                OCRResult.engine_version == engine_version,
                OCRResult.render_dpi == render_dpi,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            return existing

    return await create_ocr_result(
        db,
        raw_observation_id=raw_observation_id,
        page_number=page_number,
        text=text,
        confidence=confidence,
        engine_name=engine_name,
        engine_version=engine_version,
        render_dpi=render_dpi,
        confidence_detail=confidence_detail,
        render_params=render_params,
    )
