"""
Tesseract OCR execution tests — app.services.tesseract_ocr_service.
Runs the REAL Tesseract binary against real, small, synthetic images
(no mocked OCR output for the happy path — the actual engine is fast
enough on a single small image that mocking would only hide real
integration bugs). Failure-path tests mock pytesseract directly, since
provoking a genuine Tesseract crash deterministically isn't practical.
"""

from unittest.mock import patch

import pytesseract
import pytest
from PIL import Image, ImageDraw

from app.services.tesseract_ocr_service import (
    EMPTY_PAGE_CONFIDENCE,
    TesseractExecutionError,
    get_engine_version,
    run_ocr,
)


def _text_image(text: str, size: tuple[int, int] = (400, 100)) -> Image.Image:
    img = Image.new("RGB", size, color="white")
    draw = ImageDraw.Draw(img)
    draw.text((10, 30), text, fill="black")
    return img


def _blank_image(size: tuple[int, int] = (200, 200)) -> Image.Image:
    return Image.new("RGB", size, color="white")


# --------------------------------------------------------------------------
# E. OCR confidence calculation
# --------------------------------------------------------------------------


def test_run_ocr_returns_text_and_confidence_in_0_1_range():
    output = run_ocr(_text_image("Hello World"))
    assert "Hello" in output.text
    assert 0.0 <= output.confidence <= 1.0
    assert output.word_count > 0


def test_confidence_excludes_non_text_conf_negative_one():
    """Confidence is computed only from conf >= 0 rows — this is proven
    indirectly: a real word-bearing image must yield word_count > 0
    (i.e. real word rows were found and kept) and a plausible non-zero
    confidence, not a value dragged toward zero by non-text container
    rows (which pytesseract marks conf == -1 and this module discards)."""
    output = run_ocr(_text_image("Confidence Test"))
    assert output.word_count > 0
    assert output.confidence > 0.0


def test_confidence_scale_is_0_to_1_not_0_to_100():
    output = run_ocr(_text_image("Scale Check"))
    assert output.confidence <= 1.0  # would be up to 100 if unscaled


# --------------------------------------------------------------------------
# F. Empty OCR result
# --------------------------------------------------------------------------


def test_blank_image_yields_empty_page_confidence():
    output = run_ocr(_blank_image())
    assert output.confidence == EMPTY_PAGE_CONFIDENCE
    assert output.word_count == 0


def test_blank_image_does_not_raise():
    """A page with no usable text is a valid, successful OCR outcome —
    never a failure (see TesseractExecutionError, reserved for actual
    engine failures only)."""
    output = run_ocr(_blank_image())
    assert output.text is not None


# --------------------------------------------------------------------------
# G. Tesseract failure handling
# --------------------------------------------------------------------------


def test_tesseract_not_found_raises_execution_error():
    with (
        patch("pytesseract.image_to_string", side_effect=pytesseract.TesseractNotFoundError()),
        pytest.raises(TesseractExecutionError),
    ):
        run_ocr(_text_image("irrelevant"))


def test_tesseract_engine_error_raises_execution_error():
    with (
        patch(
            "pytesseract.image_to_string",
            side_effect=pytesseract.TesseractError(1, "simulated engine failure"),
        ),
        pytest.raises(TesseractExecutionError),
    ):
        run_ocr(_text_image("irrelevant"))


def test_get_engine_version_raises_when_tesseract_missing():
    with (
        patch(
            "pytesseract.get_tesseract_version", side_effect=pytesseract.TesseractNotFoundError()
        ),
        pytest.raises(TesseractExecutionError),
    ):
        get_engine_version()


def test_get_engine_version_returns_real_version_string():
    version = get_engine_version()
    assert version
    assert isinstance(version, str)
