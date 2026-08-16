"""
Document management service — Module 3B. Handles upload/replace/delete/
list for VerificationDocument, all routed through the storage
abstraction (app.core.storage) and file validation
(app.core.file_validation) — never touching the filesystem or trusting
client-declared content types directly.
"""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.file_validation import scan_for_viruses, validate_document
from app.core.storage import StorageBackend, make_object_key
from app.models.verification_document import DocumentStatus, DocumentType, VerificationDocument

settings_max_size_default = 15 * 1024 * 1024


class DocumentNotFoundError(Exception):
    pass


async def upload_document(
    db: AsyncSession,
    storage: StorageBackend,
    *,
    company_id: uuid.UUID,
    uploaded_by: uuid.UUID,
    document_type: DocumentType,
    filename: str,
    data: bytes,
    max_size_bytes: int,
    expiry_date: date | None = None,
) -> VerificationDocument:
    """
    Raises FileValidationError (mapped to 422 by the router) if the file
    fails validation. Never raises on a clean upload — status is always
    PENDING (see DocumentStatus's docstring: nothing in this module sets
    VERIFIED/REJECTED).
    """
    content_type = validate_document(data, max_size_bytes=max_size_bytes)
    scan_for_viruses(data)  # placeholder — see app.core.file_validation

    file_type = "pdf" if content_type == "application/pdf" else "image"
    key = make_object_key(company_id=company_id, category="documents", original_filename=filename)
    url = await storage.save(key, data, content_type)

    document = VerificationDocument(
        company_id=company_id,
        document_type=document_type,
        file_type=file_type,
        file_url=url,
        status=DocumentStatus.PENDING,
        uploaded_by=uploaded_by,
        expiry_date=expiry_date,
        version=1,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)
    return document


async def get_document_or_none(
    db: AsyncSession, company_id: uuid.UUID, document_id: uuid.UUID
) -> VerificationDocument | None:
    result = await db.execute(
        select(VerificationDocument).where(
            VerificationDocument.company_id == company_id,
            VerificationDocument.id == document_id,
            VerificationDocument.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def list_documents(db: AsyncSession, company_id: uuid.UUID) -> list[VerificationDocument]:
    result = await db.execute(
        select(VerificationDocument)
        .where(
            VerificationDocument.company_id == company_id,
            VerificationDocument.is_deleted.is_(False),
        )
        .order_by(VerificationDocument.uploaded_at.desc())
    )
    return list(result.scalars().all())


async def replace_document(
    db: AsyncSession,
    storage: StorageBackend,
    *,
    existing: VerificationDocument,
    uploaded_by: uuid.UUID,
    filename: str,
    data: bytes,
    max_size_bytes: int,
    expiry_date: date | None = None,
) -> VerificationDocument:
    """
    Creates a new document row (version = existing.version + 1, same
    document_type) and soft-deletes `existing`, linking it forward via
    `superseded_by_id` — preserves the full audit trail rather than
    mutating the old row's file_url in place.
    """
    content_type = validate_document(data, max_size_bytes=max_size_bytes)
    scan_for_viruses(data)

    file_type = "pdf" if content_type == "application/pdf" else "image"
    key = make_object_key(
        company_id=existing.company_id, category="documents", original_filename=filename
    )
    url = await storage.save(key, data, content_type)

    new_document = VerificationDocument(
        company_id=existing.company_id,
        document_type=existing.document_type,
        file_type=file_type,
        file_url=url,
        status=DocumentStatus.PENDING,
        uploaded_by=uploaded_by,
        expiry_date=expiry_date if expiry_date is not None else existing.expiry_date,
        version=existing.version + 1,
    )
    db.add(new_document)
    await db.flush()  # assigns new_document.id before we reference it below

    existing.is_deleted = True
    existing.deleted_at = datetime.now(UTC)
    existing.deleted_by = uploaded_by
    existing.superseded_by_id = new_document.id

    await db.commit()
    await db.refresh(new_document)
    return new_document


async def delete_document(
    db: AsyncSession,
    storage: StorageBackend,
    *,
    document: VerificationDocument,
    deleted_by: uuid.UUID,
) -> None:
    """
    Soft-delete: marks the row deleted and keeps both the row and its
    underlying stored file untouched, so a soft-deleted document remains
    recoverable (matches Module 3A's Company archive-not-delete
    precedent, and the module brief's "soft delete" + "audit trail"
    requirements — an audit trail that references a physically-deleted
    file would be a broken audit trail). The `storage` parameter is
    accepted for interface symmetry with upload_document/replace_document
    and to make a future "hard delete after N days" retention job an
    additive change here, not a signature change.
    """
    document.is_deleted = True
    document.deleted_at = datetime.now(UTC)
    document.deleted_by = deleted_by
    await db.commit()
