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


def make_object_key(*, company_id: uuid.UUID, category: str, original_filename: str) -> str:
    """
    Builds a storage key like `companies/<company_id>/<category>/<uuid>-<safe-filename>`.
    Never trusts the original filename directly (path traversal, unsafe
    characters) — only its extension and a sanitized stem are kept.
    """
    suffix = Path(original_filename).suffix.lower()
    stem = _UNSAFE_CHARS.sub("-", Path(original_filename).stem)[:60] or "file"
    unique = uuid.uuid4().hex[:12]
    return f"companies/{company_id}/{category}/{unique}-{stem}{suffix}"


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


_backend: StorageBackend = LocalStorageBackend()


def get_storage_backend() -> StorageBackend:
    return _backend
