"""
Tesseract OCR execution — runs Tesseract (via pytesseract's safe,
argument-list subprocess API; approved technology-selection experiment)
against an already-rasterized page image and computes a single page-
level confidence score from Tesseract's own word-level output.

Deliberately narrow: a PIL Image in, text + confidence out. No
RawObservation, no database, no rasterization — see
app.services.ocr_pipeline_service for how this composes with
app.services.pdf_rasterization_service and the existing
app.services.ocr_result_service into the full pipeline.

Two Tesseract calls, deliberately, not one: `image_to_string` for the
full page text (Tesseract's own line/paragraph reading-order
reconstruction — reproducing that correctly from raw word-level data
would be real, error-prone complexity for zero benefit) and
`image_to_data` for word-level confidence. This exact two-call shape is
what the approved rasterization+OCR technology-selection experiment
actually measured against the real CRI 2024 catalogue — using a
different reconstruction here would mean shipping something whose
behavior was never validated. The measured cost (~2x a single call) was
judged acceptable: this pipeline is a background/batch operation, not a
request-latency-sensitive path (no API is added in this milestone).

CONFIDENCE CALCULATION, precisely: pytesseract.image_to_data returns
one TSV row per detected region at every level (page/block/paragraph/
line/word). Tesseract marks every row that is NOT an actual recognized
word — the page/block/paragraph/line container rows — with conf == -1;
those rows have no real recognition confidence of their own and are
never meaningful text. This module keeps only rows with conf >= 0
(genuine word-level recognitions, including legitimately low-confidence
ones like conf == 0 — a real, low-but-valid recognition, not a
sentinel) and averages them, then rescales Tesseract's native 0-100
scale to the 0.0-1.0 scale app.models.ocr_result.OCRResult.confidence
is documented to use. A page with zero such rows (nothing Tesseract
considered a word at all — e.g. a blank page) yields EMPTY_PAGE_CONFIDENCE
(0.0), never None and never a crash.

get_word_boxes (Table Intelligence V1 foundation): a second, additive
entry point returning each recognized word's own bounding box, not
just an aggregate page confidence — the input app.extraction.table_geometry's
deterministic pitch/origin fitting and position-based cell assignment
require. Applies the identical conf >= 0 filter as run_ocr's own
confidence calculation, for the same reason (page/block/paragraph/line
container rows carry no real per-word position or confidence of their
own). Does not change run_ocr's behavior or signature in any way.
"""

from dataclasses import dataclass

import pytesseract
from PIL import Image

from app.extraction.table_geometry import WordBox

ENGINE_NAME = "tesseract"
EMPTY_PAGE_CONFIDENCE = 0.0

__all__ = [
    "EMPTY_PAGE_CONFIDENCE",
    "ENGINE_NAME",
    "TesseractExecutionError",
    "TesseractOcrOutput",
    "get_engine_version",
    "get_word_boxes",
    "run_ocr",
]


class TesseractExecutionError(Exception):
    """Raised when Tesseract itself fails to run — binary missing
    (pytesseract.TesseractNotFoundError) or an internal engine failure
    (pytesseract.TesseractError) — never silently swallowed into a
    fake/empty result. See app.services.ocr_pipeline_service's own
    fail-closed handling of this: no OCRResult row is ever created when
    this is raised."""


@dataclass(frozen=True)
class TesseractOcrOutput:
    text: str
    confidence: float  # 0.0-1.0, see this module's own docstring
    word_count: int  # words with conf >= 0 — internal diagnostic only, not persisted structurally


def get_engine_version() -> str:
    """The real Tesseract binary's version (e.g. "5.5.3") — distinct
    from pytesseract's own package version, which is not recorded on
    OCRResult (see that model's own docstring: engine_name/engine_version
    identify the OCR ENGINE, not the Python wrapper around it)."""
    try:
        return str(pytesseract.get_tesseract_version())
    except pytesseract.TesseractNotFoundError as exc:
        raise TesseractExecutionError(f"Tesseract is not available: {exc}") from exc


def run_ocr(image: Image.Image) -> TesseractOcrOutput:
    try:
        text = pytesseract.image_to_string(image)
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    except (pytesseract.TesseractNotFoundError, pytesseract.TesseractError) as exc:
        raise TesseractExecutionError(f"Tesseract OCR execution failed: {exc}") from exc

    word_confidences = [int(c) for c in data["conf"] if int(c) >= 0]
    if word_confidences:
        confidence = (sum(word_confidences) / len(word_confidences)) / 100.0
    else:
        confidence = EMPTY_PAGE_CONFIDENCE

    return TesseractOcrOutput(text=text, confidence=confidence, word_count=len(word_confidences))


def get_word_boxes(image: Image.Image) -> list[WordBox]:
    try:
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    except (pytesseract.TesseractNotFoundError, pytesseract.TesseractError) as exc:
        raise TesseractExecutionError(f"Tesseract OCR execution failed: {exc}") from exc

    boxes: list[WordBox] = []
    for i in range(len(data["text"])):
        text = data["text"][i].strip()
        conf = int(data["conf"][i])
        if not text or conf < 0:
            continue
        boxes.append(
            WordBox(
                text=text,
                x=float(data["left"][i]),
                y=float(data["top"][i]),
                width=float(data["width"][i]),
                height=float(data["height"][i]),
                confidence=conf,
            )
        )
    return boxes
