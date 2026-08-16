"""
Upload validation — Module 3B. Every file upload endpoint
(logo/cover/document) runs its bytes through this module before storage.
Validates by inspecting actual file content (magic bytes / Pillow's
ability to decode the image), never by trusting the client-declared
Content-Type or filename extension alone — both are trivially spoofable.
"""

import io

from PIL import Image, UnidentifiedImageError

ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_DOCUMENT_CONTENT_TYPES = ALLOWED_IMAGE_CONTENT_TYPES | {"application/pdf"}

_PDF_MAGIC = b"%PDF-"


class FileValidationError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def validate_image(data: bytes, *, max_size_bytes: int) -> str:
    """
    Validates image bytes are actually a decodable image of an allowed
    format and within the size limit. Returns the detected content type
    (e.g. "image/png") — the caller should use this, not whatever the
    client sent, when storing/serving the file.
    """
    if len(data) > max_size_bytes:
        raise FileValidationError(
            "FILE_TOO_LARGE", f"Image exceeds the {max_size_bytes // (1024 * 1024)} MB limit."
        )
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()  # raises if the file isn't a genuine, well-formed image
            detected_format = (img.format or "").upper()
    except (UnidentifiedImageError, OSError) as exc:
        raise FileValidationError(
            "INVALID_IMAGE", "This file isn't a valid image (or is corrupted)."
        ) from exc

    content_type = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}.get(
        detected_format
    )
    if content_type is None or content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise FileValidationError(
            "UNSUPPORTED_IMAGE_TYPE", "Only JPEG, PNG, and WEBP images are supported."
        )
    return content_type


def validate_document(data: bytes, *, max_size_bytes: int) -> str:
    """
    Validates document bytes are either a genuine PDF (checked via magic
    bytes, not extension) or a valid image. Returns the detected content
    type.
    """
    if len(data) > max_size_bytes:
        raise FileValidationError(
            "FILE_TOO_LARGE", f"File exceeds the {max_size_bytes // (1024 * 1024)} MB limit."
        )
    if data.startswith(_PDF_MAGIC):
        return "application/pdf"
    # Not a PDF — try as an image (documents may be photographed/scanned as JPEG/PNG).
    return validate_image(data, max_size_bytes=max_size_bytes)


def scan_for_viruses(data: bytes) -> None:  # noqa: ARG001 — placeholder signature, see docstring
    """
    Virus-scan placeholder, per this module's brief. No real scanning
    engine (ClamAV, a cloud AV API, etc.) is integrated — this function
    exists as the single call site every upload path already routes
    through, so wiring up a real scanner later is a one-function change,
    not a hunt across every upload endpoint. Always "clean" today.
    """
    return None
