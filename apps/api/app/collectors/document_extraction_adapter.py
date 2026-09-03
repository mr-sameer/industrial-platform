"""
DocumentExtractionAdapter — Checkpoint 1 of the approved Document ->
Structured Product Data design review. Turns a previously-uploaded
document (see app.api.v1.documents.upload_document, which stores the
file via app.core.storage and returns a storage_key + sha256) into
exactly one RawObservation, via the same SourceAdapter contract every
other collector (Module 5B/6D) already implements — no parallel
ingestion path, matching this codebase's own established extension
point (app.collectors.manual_entry_adapter's identical reasoning: "for
zero new persistence, zero new API route, and zero schema change"
beyond the adapter itself).

CHECKPOINT SCOPE, restated explicitly: this adapter produces NO
Product, NO ProductAttributeEvidence, and performs NO specification/
value extraction of any kind — it stops at "the document's text is now
a durable, page-numbered, provenance-tracked RawObservation." Turning
that text into structured product data is a separate, later,
explicitly-scoped checkpoint (not built here).

WHY THIS ADAPTER RE-VERIFIES sha256 rather than trusting the caller's
config: `requested_scope` is a client-supplied JSON body (Module 5B's
existing AcquisitionJobCreate) — nothing prevents a caller from citing
a stale or fabricated hash. Re-hashing the bytes actually read from
storage and comparing against the claimed hash is the only way to
guarantee the RawObservation this adapter produces genuinely reflects
the file at that storage key, not merely an unverified claim about it.
"""

import hashlib
import json
from typing import Any

from app.collectors.base import CollectedItem, NonRetryableCollectorError, SourceAdapter
from app.collectors.pdf_text_extraction import PdfParsingError, extract_pdf_pages
from app.core.storage import get_storage_backend

_REQUIRED_FIELDS = ("storage_key", "sha256", "filename")


def _content_hash(raw_content: dict[str, Any]) -> str:
    canonical = json.dumps(raw_content, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class DocumentExtractionAdapter(SourceAdapter):
    """
    config keys (== what POST /acquisition/jobs's requested_scope must
    carry for this collector_type):
      storage_key (required) — the key returned by POST /documents.
      sha256 (required)      — the hash computed at upload time; re-verified
                                against the bytes actually read here, never
                                trusted as-is.
      filename (required)    — the original filename, preserved for
                                traceability only — never trusted for
                                content-type decisions (see
                                app.core.file_validation's own docstring:
                                content is validated by magic bytes at
                                upload time, not here, and not by this
                                filename).
    """

    adapter_type = "document_extraction"

    def validate_config(self, config: dict[str, Any]) -> None:
        missing = [f for f in _REQUIRED_FIELDS if not config.get(f)]
        if missing:
            raise NonRetryableCollectorError(
                f"Missing required config key(s): {', '.join(missing)}"
            )

    def collect(self, config: dict[str, Any]) -> list[CollectedItem]:
        storage_key = str(config["storage_key"])
        expected_sha256 = str(config["sha256"])
        filename = str(config["filename"])

        storage = get_storage_backend()
        try:
            data = storage.read_bytes(storage_key)
        except FileNotFoundError as exc:
            raise NonRetryableCollectorError(
                f"No stored file found at key {storage_key!r}."
            ) from exc

        actual_sha256 = hashlib.sha256(data).hexdigest()
        if actual_sha256 != expected_sha256:
            raise NonRetryableCollectorError(
                "SHA-256 mismatch — the stored file's content does not match the hash "
                "recorded at upload time. Refusing to process a document that cannot be "
                "verified against its own claimed hash."
            )

        try:
            pages = extract_pdf_pages(data)
        except PdfParsingError as exc:
            raise NonRetryableCollectorError(str(exc)) from exc

        raw_content: dict[str, Any] = {
            "filename": filename,
            "sha256": actual_sha256,
            "storage_key": storage_key,
            "page_count": len(pages),
            "pages": [{"page": index + 1, "text": text} for index, text in enumerate(pages)],
        }
        return [
            CollectedItem(
                raw_content=raw_content,
                content_hash=_content_hash(raw_content),
                external_identifier=actual_sha256,
            )
        ]

    def source_metadata(self) -> dict[str, Any]:
        return {
            "adapter_type": self.adapter_type,
            "provider": "ForgeX platform (uploaded source documents)",
            "dataset": "PDF text-layer extraction — no OCR, no AI, no embedded-content execution",
            "data_shape_note": (
                "One RawObservation per document; raw_content carries page-numbered "
                "text only, never structured product data (a separate, later checkpoint)."
            ),
        }


__all__ = ["DocumentExtractionAdapter"]
