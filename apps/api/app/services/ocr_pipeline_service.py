"""
OCR pipeline orchestration — RawObservation -> PDF page rasterization
(app.services.pdf_rasterization_service) -> Tesseract OCR
(app.services.tesseract_ocr_service) -> persisted OCRResult (the
existing, unmodified app.services.ocr_result_service). This module is
the ONLY place these three pieces are wired together — deliberately
thin, no logic of its own beyond orchestration and fail-closed error
translation. No API route calls this in this milestone (see the OCR
Processing Foundation's own explicit non-goals).

Reads the original PDF bytes via the SAME storage_key contract
app.collectors.document_extraction_adapter already established for
document-derived RawObservations (raw_content["storage_key"]) — no new
storage mechanism, no redesign of RawObservation. A RawObservation
without that key (e.g. a manual/API-collected observation that was
never a document) is rejected explicitly, never guessed at.

Fails closed at every step, in this order, deliberately (cheapest/
fastest checks first): Tesseract availability, RawObservation
existence, storage_key presence, file presence, rasterization, OCR
execution. The ONLY way an OCRResult row is ever created is the single
call to ocr_result_service.get_or_create_ocr_result at the very end,
after every prior step has already succeeded — there is no code path
that creates a partial or fake OCRResult on failure.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import get_storage_backend
from app.models.ocr_result import OCRResult
from app.models.raw_observation import RawObservation
from app.services import ocr_result_service, provenance_service
from app.services.pdf_rasterization_service import DEFAULT_DPI, rasterize_page
from app.services.tesseract_ocr_service import ENGINE_NAME, get_engine_version, run_ocr

__all__ = [
    "InvalidRawObservationForOcrError",
    "RawObservationNotFoundError",
    "process_raw_observation_page",
]


class RawObservationNotFoundError(Exception):
    pass


class InvalidRawObservationForOcrError(Exception):
    """Raised when raw_observation.raw_content has no usable
    storage_key — this RawObservation was never a document (e.g. a
    manual/API observation) and cannot be rasterized/OCR'd, or its
    stored file is missing."""


def _get_storage_key(observation: RawObservation) -> str:
    storage_key = observation.raw_content.get("storage_key")
    if not storage_key or not isinstance(storage_key, str):
        raise InvalidRawObservationForOcrError(
            f"RawObservation {observation.id} has no usable storage_key in "
            f"raw_content — it was not collected via DocumentExtractionAdapter "
            f"and cannot be rasterized."
        )
    return storage_key


async def process_raw_observation_page(
    db: AsyncSession,
    *,
    raw_observation_id: uuid.UUID,
    page_number: int,
    dpi: int = DEFAULT_DPI,
    force_reprocess: bool = False,
) -> OCRResult:
    engine_version = get_engine_version()

    observation = await provenance_service.get_raw_observation(db, raw_observation_id)
    if observation is None:
        raise RawObservationNotFoundError(str(raw_observation_id))

    storage_key = _get_storage_key(observation)
    storage = get_storage_backend()
    try:
        pdf_bytes = storage.read_bytes(storage_key)
    except FileNotFoundError as exc:
        raise InvalidRawObservationForOcrError(
            f"No stored file found at key {storage_key!r} for RawObservation " f"{observation.id}."
        ) from exc

    rendered = rasterize_page(
        pdf_bytes,
        content_hash=observation.content_hash,
        page_number=page_number,
        dpi=dpi,
    )
    ocr_output = run_ocr(rendered.image)

    return await ocr_result_service.get_or_create_ocr_result(
        db,
        raw_observation_id=observation.id,
        page_number=page_number,
        text=ocr_output.text,
        confidence=ocr_output.confidence,
        engine_name=ENGINE_NAME,
        engine_version=engine_version,
        render_dpi=dpi,
        render_params=rendered.render_params,
        force_reprocess=force_reprocess,
    )
