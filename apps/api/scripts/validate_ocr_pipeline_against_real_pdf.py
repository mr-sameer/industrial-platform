#!/usr/bin/env python3
"""
Manual, real-PDF validation for the rasterization + OCR pipeline
(app.services.pdf_rasterization_service, app.services.tesseract_ocr_service)
against an actual industrial catalogue — NOT part of the pytest suite,
deliberately: the normal test suite must never depend on downloading an
external file, so this is a separately-runnable script instead (per the
OCR Processing Foundation's own validation requirements).

Does not touch the database or RawObservation at all — this exercises
only the rasterization + OCR layers directly against a local PDF file,
which is exactly what's needed to confirm the real engine still behaves
as measured in the approved rasterization+OCR technology-selection
experiment (that experiment used the CRI 2024 catalogue; any real PDF
works here).

Usage:
    cd apps/api
    python scripts/validate_ocr_pipeline_against_real_pdf.py /path/to/some.pdf [page_number ...]

If no page numbers are given, renders/OCRs pages 1, 2, and the last
page. Requires the real `tesseract` binary to be installed locally
(see README.md's Prerequisites) — this script does not mock anything.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.pdf_rasterization_service import get_page_count, rasterize_page  # noqa: E402
from app.services.tesseract_ocr_service import get_engine_version, run_ocr  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    pdf_path = Path(sys.argv[1])
    if not pdf_path.is_file():
        print(f"No such file: {pdf_path}")
        sys.exit(1)

    pdf_bytes = pdf_path.read_bytes()
    page_count = get_page_count(pdf_bytes)
    print(f"{pdf_path.name}: {page_count} pages, tesseract {get_engine_version()}\n")

    if len(sys.argv) > 2:
        pages = [int(p) for p in sys.argv[2:]]
    else:
        pages = sorted({1, min(2, page_count), page_count})

    content_hash = f"manual-validation:{pdf_path.name}"
    for page_number in pages:
        t0 = time.perf_counter()
        rendered = rasterize_page(pdf_bytes, content_hash=content_hash, page_number=page_number)
        render_ms = (time.perf_counter() - t0) * 1000

        t1 = time.perf_counter()
        output = run_ocr(rendered.image)
        ocr_ms = (time.perf_counter() - t1) * 1000

        print(
            f"=== page {page_number} ({rendered.width}x{rendered.height}px @ {rendered.render_dpi}DPI) ==="
        )
        print(
            f"  render: {render_ms:.0f}ms, ocr: {ocr_ms:.0f}ms, confidence: {output.confidence:.3f}"
        )
        print(f"  words recognized: {output.word_count}")
        print("  --- first 300 chars of OCR text ---")
        print(output.text[:300])
        print()


if __name__ == "__main__":
    main()
