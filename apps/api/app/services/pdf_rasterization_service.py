"""
PDF page rasterization — turns raw PDF bytes + a page number into a
raster image via pypdfium2 (approved technology-selection experiment:
Apache-2.0/BSD-3-Clause licensed, no copyleft exposure, measured faster
than PyMuPDF across the full 20-page CRI 2024 catalogue at 300 DPI —
see that experiment's own report). Local/offline only: pypdfium2 never
makes a network call.

Deliberately narrow: bytes + page number + DPI in, one PIL Image out.
No RawObservation, no database, no OCR — see app.services.ocr_pipeline_service
for how this composes with app.services.tesseract_ocr_service and the
existing app.services.ocr_result_service into the full pipeline.

Renders are cached on local disk (never in the database — no row is
ever created for a rendered image), keyed by a hash of EVERY input
that affects the output: content_hash, page_number, dpi, and the
renderer's own name/version. content_hash is always the first, always-
required component of that key, which is what makes it structurally
impossible for one document's cached rendering to ever be served back
for a different document — see _cache_key. The cache is a pure
performance optimization; a cache miss re-renders deterministically
from the same PDF bytes, so nothing here is a source of truth and nothing
here needs to survive a restart (a cleared temp dir just means the next
call re-renders).
"""

import hashlib
import json
import tempfile
from dataclasses import dataclass
from importlib.metadata import version as _pkg_version
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

RENDERER_NAME = "pypdfium2"
RENDERER_VERSION = _pkg_version("pypdfium2")
DEFAULT_DPI = 300

_CACHE_DIR = Path(tempfile.gettempdir()) / "forgex_render_cache"

__all__ = [
    "DEFAULT_DPI",
    "RENDERER_NAME",
    "RENDERER_VERSION",
    "PageOutOfRangeError",
    "PdfRasterizationError",
    "RenderedPage",
    "get_page_count",
    "rasterize_page",
]


class PdfRasterizationError(Exception):
    """Raised when the PDF cannot be opened/parsed at all — a corrupt
    or non-PDF byte stream. Never raised merely for a valid PDF with an
    out-of-range page number (see PageOutOfRangeError)."""


class PageOutOfRangeError(Exception):
    """Raised when the requested page_number is outside [1, page_count]
    for this PDF. page_number is always 1-indexed, matching how pages
    are referenced everywhere else in this codebase (e.g.
    app.collectors.document_extraction_adapter's own raw_content.pages)."""


@dataclass(frozen=True)
class RenderedPage:
    image: Image.Image
    width: int
    height: int
    render_dpi: int
    render_params: dict[str, object]
    cache_key: str
    from_cache: bool


def _cache_key(*, content_hash: str, page_number: int, dpi: int) -> str:
    """Every input that affects the rendered bytes goes into this key.
    RENDERER_NAME/RENDERER_VERSION are process-wide constants rather
    than parameters, but are still folded in so a renderer upgrade
    can never silently serve a stale, pre-upgrade cache entry."""
    payload = {
        "content_hash": content_hash,
        "page_number": page_number,
        "dpi": dpi,
        "renderer_name": RENDERER_NAME,
        "renderer_version": RENDERER_VERSION,
    }
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_page_count(pdf_bytes: bytes) -> int:
    try:
        pdf = pdfium.PdfDocument(pdf_bytes)
    except pdfium.PdfiumError as exc:
        raise PdfRasterizationError(f"Could not open PDF: {exc}") from exc
    try:
        return len(pdf)
    finally:
        pdf.close()


def rasterize_page(
    pdf_bytes: bytes,
    *,
    content_hash: str,
    page_number: int,
    dpi: int = DEFAULT_DPI,
) -> RenderedPage:
    """
    Renders one page (1-indexed) of pdf_bytes at `dpi`. Deterministic:
    the same (content_hash, page_number, dpi) always yields pixel-
    identical output — pypdfium2's rendering has no non-deterministic
    inputs (no font substitution roulette, no clock, no randomness) —
    which is what makes caching by these inputs alone safe.

    content_hash is the CALLER's RawObservation.content_hash — NOT
    recomputed from pdf_bytes here, since RawObservation.content_hash
    is a hash of the full raw_content structure (see
    app.collectors.document_extraction_adapter), not merely the PDF's
    own bytes. app.services.ocr_pipeline_service is the one place that
    legitimately knows which RawObservation these bytes came from, so
    it is trusted to supply the right value here — this function has no
    way to verify it independently, by design (it never touches the
    database).
    """
    key = _cache_key(content_hash=content_hash, page_number=page_number, dpi=dpi)
    cache_path = _CACHE_DIR / f"{key}.png"
    render_params: dict[str, object] = {
        "renderer": RENDERER_NAME,
        "renderer_version": RENDERER_VERSION,
        "color_mode": "rgb",
    }

    if cache_path.exists():
        image = Image.open(cache_path)
        image.load()  # type: ignore[no-untyped-call]  # Pillow ships no stub for this method
        return RenderedPage(
            image=image,
            width=image.width,
            height=image.height,
            render_dpi=dpi,
            render_params=render_params,
            cache_key=key,
            from_cache=True,
        )

    try:
        pdf = pdfium.PdfDocument(pdf_bytes)
    except pdfium.PdfiumError as exc:
        raise PdfRasterizationError(f"Could not open PDF: {exc}") from exc

    try:
        page_count = len(pdf)
        if page_number < 1 or page_number > page_count:
            raise PageOutOfRangeError(
                f"page_number {page_number} is outside the valid range "
                f"[1, {page_count}] for this document."
            )
        try:
            page = pdf[page_number - 1]
            bitmap = page.render(scale=dpi / 72)
            image = bitmap.to_pil()
        except pdfium.PdfiumError as exc:
            raise PdfRasterizationError(f"Could not rasterize page {page_number}: {exc}") from exc
    finally:
        pdf.close()

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    image.save(cache_path)

    return RenderedPage(
        image=image,
        width=image.width,
        height=image.height,
        render_dpi=dpi,
        render_params=render_params,
        cache_key=key,
        from_cache=False,
    )
