"""
Deterministic PDF text-layer extraction — Checkpoint 1 of the approved
Document -> Structured Product Data design review. Pure text-layer
reading via `pypdf` only: no OCR (no image-to-text), no LLM, no
embedded-JavaScript execution, no fetching of external resources a PDF
might reference — pypdf is a passive reader of the PDF's own text
objects, never a renderer, which is exactly why it was chosen (see the
approved design's Section 17).

Wrapped in a hard timeout (`_PARSE_TIMEOUT_SECONDS`) since this runs
synchronously, inline, with no background queue — matching
app.services.acquisition_service's own documented, accepted
synchronous-by-design limitation. A malformed or adversarially complex
PDF must fail cleanly within a bounded time, never hang the request
indefinitely. Note the real limit of this mitigation: Python threads
cannot be forcibly killed, so a genuinely hung native parse still ties
up one background thread until it eventually returns — this bounds the
*caller's* wait time to a clean failure, it does not guarantee the
worker thread itself terminates early. A true kill-switch would need a
subprocess, which is out of scope for this checkpoint's synchronous,
no-queue architecture.
"""

import concurrent.futures
import io

import pypdf

_PARSE_TIMEOUT_SECONDS = 20


class PdfParsingError(Exception):
    """Raised for any malformed/unparseable/encrypted PDF, or one that
    exceeds the hard timeout below. Always translated to
    NonRetryableCollectorError by the calling adapter — a malformed
    file will not become parseable on a second attempt."""


def _extract_pages_blocking(data: bytes) -> list[str]:
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise PdfParsingError("PDF is encrypted/password-protected — cannot extract text.")
        return [(page.extract_text() or "") for page in reader.pages]
    except PdfParsingError:
        raise
    except Exception as exc:  # noqa: BLE001 — any pypdf/parsing failure must become this module's own typed error, never an unhandled exception reaching the adapter's caller
        raise PdfParsingError(f"Failed to parse PDF: {exc}") from exc


def extract_pdf_pages(data: bytes) -> list[str]:
    """
    Returns one string per page, in page order (index 0 == page 1).
    Deterministic: the same bytes always produce the same output — no
    randomness, no external calls, no model inference.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_extract_pages_blocking, data)
        try:
            return future.result(timeout=_PARSE_TIMEOUT_SECONDS)
        except concurrent.futures.TimeoutError as exc:
            raise PdfParsingError(
                f"PDF parsing exceeded the {_PARSE_TIMEOUT_SECONDS}s limit — "
                "possibly malformed or adversarially complex."
            ) from exc


__all__ = ["PdfParsingError", "extract_pdf_pages"]
