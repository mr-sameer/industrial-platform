"""
PDF page rasterization tests — app.services.pdf_rasterization_service.
Uses tests.test_document_extraction's hand-built, real, valid PDF bytes
(no binary fixture file, no new PDF-authoring dependency) so pypdfium2
is exercised against a genuine PDF, not a mock.
"""

import uuid

import pytest

from app.services.pdf_rasterization_service import (
    DEFAULT_DPI,
    PageOutOfRangeError,
    PdfRasterizationError,
    get_page_count,
    rasterize_page,
)
from tests.test_document_extraction import _build_test_pdf, _valid_test_pdf_bytes

# --------------------------------------------------------------------------
# A. PDF page rasterization
# --------------------------------------------------------------------------


def test_rasterize_page_produces_expected_image():
    data = _valid_test_pdf_bytes()
    rendered = rasterize_page(data, content_hash="hash-a", page_number=1, dpi=DEFAULT_DPI)
    assert rendered.width > 0
    assert rendered.height > 0
    assert rendered.render_dpi == DEFAULT_DPI
    assert rendered.image.size == (rendered.width, rendered.height)


def test_rasterize_page_is_deterministic_pixel_identical():
    data = _valid_test_pdf_bytes()
    first = rasterize_page(data, content_hash="hash-det", page_number=1, dpi=DEFAULT_DPI)
    second = rasterize_page(data, content_hash="hash-det", page_number=1, dpi=DEFAULT_DPI)
    assert list(first.image.getdata()) == list(second.image.getdata())


def test_rasterize_page_respects_configurable_dpi():
    data = _valid_test_pdf_bytes()
    low = rasterize_page(data, content_hash="hash-dpi", page_number=1, dpi=72)
    high = rasterize_page(data, content_hash="hash-dpi", page_number=1, dpi=300)
    assert high.width > low.width
    assert high.height > low.height


def test_get_page_count():
    data = _build_test_pdf(["Page One", "Page Two", "Page Three"])
    assert get_page_count(data) == 3


def test_rasterize_page_no_network_calls_required(monkeypatch):
    """Sanity check that rasterization needs no network access at all —
    breaks socket creation and confirms rendering still succeeds."""
    import socket

    def _blocked(*args, **kwargs):
        raise AssertionError("rasterize_page must never open a network socket")

    monkeypatch.setattr(socket, "socket", _blocked)
    data = _valid_test_pdf_bytes()
    rendered = rasterize_page(data, content_hash="hash-offline", page_number=1, dpi=DEFAULT_DPI)
    assert rendered.width > 0


# --------------------------------------------------------------------------
# B. Deterministic render/cache key
# --------------------------------------------------------------------------


def test_cache_key_includes_content_hash_page_and_dpi():
    data = _valid_test_pdf_bytes()
    a = rasterize_page(data, content_hash="hash-x", page_number=1, dpi=150)
    b = rasterize_page(data, content_hash="hash-y", page_number=1, dpi=150)  # different hash
    c = rasterize_page(data, content_hash="hash-x", page_number=1, dpi=200)  # different dpi
    assert a.cache_key != b.cache_key
    assert a.cache_key != c.cache_key


def test_rendering_from_one_document_never_reused_for_another():
    """Two DIFFERENT documents, same page number/dpi — the cache key
    must differ, so a rendering can never be served across documents."""
    doc_a = _build_test_pdf(["Document A content"])
    doc_b = _build_test_pdf(["Document B content, completely different"])

    rendered_a = rasterize_page(doc_a, content_hash="doc-a-hash", page_number=1, dpi=150)
    rendered_b = rasterize_page(doc_b, content_hash="doc-b-hash", page_number=1, dpi=150)

    assert rendered_a.cache_key != rendered_b.cache_key
    assert list(rendered_a.image.getdata()) != list(rendered_b.image.getdata())


def test_cache_hit_on_second_call_with_identical_inputs():
    """The render cache lives in the real OS temp dir and is shared
    across process invocations by design (see the module's own
    docstring) — a fixed content_hash could collide with a file left
    over from an earlier test run/process. A fresh, random hash
    guarantees this specific cache key has never been rendered before,
    so `first` is provably a genuine miss."""
    content_hash = f"hash-cache-{uuid.uuid4().hex}"
    data = _valid_test_pdf_bytes()
    first = rasterize_page(data, content_hash=content_hash, page_number=1, dpi=DEFAULT_DPI)
    second = rasterize_page(data, content_hash=content_hash, page_number=1, dpi=DEFAULT_DPI)
    assert first.from_cache is False
    assert second.from_cache is True
    assert first.cache_key == second.cache_key


# --------------------------------------------------------------------------
# C. Page selection / range validation
# --------------------------------------------------------------------------


def test_page_out_of_range_rejected():
    data = _build_test_pdf(["Only page"])
    with pytest.raises(PageOutOfRangeError):
        rasterize_page(data, content_hash="hash-range", page_number=2, dpi=DEFAULT_DPI)


def test_page_zero_rejected():
    data = _valid_test_pdf_bytes()
    with pytest.raises(PageOutOfRangeError):
        rasterize_page(data, content_hash="hash-zero", page_number=0, dpi=DEFAULT_DPI)


def test_negative_page_rejected():
    data = _valid_test_pdf_bytes()
    with pytest.raises(PageOutOfRangeError):
        rasterize_page(data, content_hash="hash-neg", page_number=-1, dpi=DEFAULT_DPI)


def test_corrupt_pdf_rejected():
    with pytest.raises(PdfRasterizationError):
        rasterize_page(b"not a pdf at all", content_hash="hash-corrupt", page_number=1, dpi=300)


def test_get_page_count_rejects_corrupt_pdf():
    with pytest.raises(PdfRasterizationError):
        get_page_count(b"garbage bytes")
