"""
File storage abstraction — Module 3B. Everything that uploads a file
(logo, cover image, verification documents) goes through this interface,
never through raw filesystem calls, so a future S3 (or GCS/Azure Blob)
backend is a drop-in swap — see docs/adr/0029-module-3b-verification-and-identity.md.

Design principle: callers work with **keys** (opaque, storage-backend-
chosen string identifiers), never filesystem paths — this is what makes
the interface S3-compatible from day one, since S3 has no concept of a
"path" the way a local disk does, only object keys within a bucket.
"""

import re
import uuid
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings

settings = get_settings()

_UNSAFE_CHARS = re.compile(r"[^a-zA-Z0-9._-]")


def _build_key(*, prefix: str, original_filename: str) -> str:
    """
    Shared sanitization/uniqueness logic behind every key-builder below.
    Never trusts the original filename directly (path traversal, unsafe
    characters) — only its extension and a sanitized stem are kept.
    """
    suffix = Path(original_filename).suffix.lower()
    stem = _UNSAFE_CHARS.sub("-", Path(original_filename).stem)[:60] or "file"
    unique = uuid.uuid4().hex[:12]
    return f"{prefix}/{unique}-{stem}{suffix}"


def make_object_key(*, company_id: uuid.UUID, category: str, original_filename: str) -> str:
    """Builds a storage key like `companies/<company_id>/<category>/<uuid>-<safe-filename>`."""
    return _build_key(
        prefix=f"companies/{company_id}/{category}", original_filename=original_filename
    )


def make_source_document_key(*, category: str, original_filename: str) -> str:
    """
    Company-agnostic variant of make_object_key — for acquisition-
    pipeline source material (e.g. an uploaded manufacturer catalogue
    PDF, Checkpoint 1 of the Document -> Structured Product Data
    design) that belongs to no single Company's own verification
    evidence (VerificationDocument, Module 3B uses make_object_key
    directly, unchanged). Shares the identical sanitization/uniqueness
    logic as make_object_key via _build_key — never a duplicated or
    divergent implementation.
    """
    return _build_key(prefix=f"source-documents/{category}", original_filename=original_filename)


class StorageBackend(Protocol):
    """
    Every method is key-based (never a raw filesystem path) so any
    implementation — local disk today, S3/GCS/Azure Blob tomorrow — can
    satisfy this interface without callers changing at all.
    """

    async def save(self, key: str, data: bytes, content_type: str) -> str:
        """Stores `data` under `key`. Returns a URL the file can be fetched from."""
        ...

    async def delete(self, key: str) -> None:
        """Deletes the object at `key`. Safe to call on a key that doesn't exist."""
        ...

    def get_url(self, key: str) -> str:
        """Returns the fetchable URL for `key`, without touching storage."""
        ...

    def read_bytes(self, key: str) -> bytes:
        """
        Synchronous read of a previously-saved object's raw bytes.
        Deliberately NOT async, unlike save()/delete() — this exists
        specifically for app.collectors.base.SourceAdapter.collect()
        implementations (e.g. DocumentExtractionAdapter, Checkpoint 1 of
        the Document -> Structured Product Data design), which are
        synchronous by contract (that module's own docstring: every
        adapter's collect() runs inline inside
        acquisition_service.create_and_run_job, an already-running
        coroutine, with no way to await anything from within a plain
        `def collect()`) and therefore cannot use save()/delete()'s
        async interface. Raises FileNotFoundError if no object exists
        at `key` — callers (adapters) must translate this to
        NonRetryableCollectorError, never retry it.
        """
        ...


class LocalStorageBackend:
    """
    Development/self-hosted implementation — writes to a local directory
    (see `settings.upload_storage_path`), served back out via a static
    file route (`app.api.v1.uploads`, mounted at `/uploads/*`). This is
    explicitly NOT the intended production backend for a real multi-
    instance deployment (local disk isn't shared across replicas) — see
    ADR-0029's consequences for when/why to introduce an S3Backend
    implementing the same Protocol.
    """

    def __init__(self, base_path: str | None = None, base_url: str | None = None):
        self._base_path = Path(base_path or settings.upload_storage_path)
        self._base_url = (base_url or settings.upload_public_base_url).rstrip("/")

    async def save(self, key: str, data: bytes, content_type: str) -> str:
        target = self._base_path / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return self.get_url(key)

    async def delete(self, key: str) -> None:
        target = self._base_path / key
        target.unlink(missing_ok=True)

    def get_url(self, key: str) -> str:
        return f"{self._base_url}/{key}"

    def read_bytes(self, key: str) -> bytes:
        target = self._base_path / key
        return target.read_bytes()  # raises FileNotFoundError naturally if missing


_backend: StorageBackend = LocalStorageBackend()


def get_storage_backend() -> StorageBackend:
    return _backend
