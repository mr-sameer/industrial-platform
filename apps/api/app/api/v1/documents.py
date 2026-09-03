"""
Generic document upload — Checkpoint 1 of the approved Document ->
Structured Product Data design review. Deliberately company-agnostic
and product-agnostic (unlike VerificationDocument, Module 3B) — this
is raw source material for the acquisition pipeline (Module 5B), not
one company's own verification evidence. Role.ADMIN-gated: parsing
untrusted uploaded file content downstream is exactly the "executes
code on the server" case app.api.v1.acquisition's own docstring
already reserves for Role.ADMIN, and per the approved design review
this is a hard prerequisite for this feature specifically, not a
follow-up.

Reuses app.core.file_validation.validate_document (magic-byte check —
never the client-declared Content-Type or filename extension) and
app.core.storage's existing StorageBackend/make_source_document_key
exactly as app.services.document_service.upload_document already does
for VerificationDocument uploads — no parallel storage abstraction.
Reuses the same settings.upload_max_document_size_bytes limit that
route already enforces.

Stores nothing in the database — this endpoint is pure file handling.
The returned storage_key/sha256/filename are passed by the caller into
a separate, explicit POST /acquisition/jobs request
(collector_type="document_extraction", Module 5B, unmodified); see
app.collectors.document_extraction_adapter for what happens next. The
storage URL is deliberately never returned here — this file is
internal source material for an admin-gated pipeline, not a
publicly-servable asset like a company logo.
"""

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.config import get_settings
from app.core.dependencies import require_role
from app.core.file_validation import FileValidationError, scan_for_viruses, validate_document
from app.core.responses import ApiSuccess, success_response
from app.core.storage import StorageBackend, get_storage_backend, make_source_document_key
from app.models.user import Role
from app.schemas.document_upload import DocumentUploadPublic

router = APIRouter(prefix="/documents", tags=["documents"])

settings = get_settings()

RequireAdmin = Annotated[object, Depends(require_role(Role.ADMIN))]


def _get_storage() -> StorageBackend:
    return get_storage_backend()


StorageDep = Annotated[StorageBackend, Depends(_get_storage)]


@router.post(
    "", response_model=ApiSuccess[DocumentUploadPublic], status_code=status.HTTP_201_CREATED
)
async def upload_document(
    _admin: RequireAdmin,
    storage: StorageDep,
    file: Annotated[UploadFile, File(...)],
) -> ApiSuccess[DocumentUploadPublic]:
    """
    PDF-only in this checkpoint (§4 of the approved design) — any other
    genuinely-detected type is rejected, even though
    file_validation.validate_document also accepts images (a
    scanned-document allowance VerificationDocument uses; out of scope
    here, since OCR is explicitly not built yet).
    """
    data = await file.read()
    try:
        content_type = validate_document(
            data, max_size_bytes=settings.upload_max_document_size_bytes
        )
    except FileValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    if content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "UNSUPPORTED_DOCUMENT_TYPE",
                "message": "Only PDF documents are supported in this checkpoint.",
            },
        )

    scan_for_viruses(data)  # placeholder — see app.core.file_validation's own docstring;
    # no real scanning engine is integrated, unchanged by this checkpoint.

    sha256 = hashlib.sha256(data).hexdigest()
    filename = file.filename or "document.pdf"
    key = make_source_document_key(category="uploads", original_filename=filename)
    await storage.save(key, data, content_type)

    return success_response(
        DocumentUploadPublic(
            storage_key=key,
            sha256=sha256,
            filename=filename,
            size_bytes=len(data),
            content_type=content_type,
        )
    )
