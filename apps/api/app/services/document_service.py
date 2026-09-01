"""
Document management service — Module 3B, extended in Phase 1 of the
admin document-verification review workflow. Handles upload/replace/
delete/list/review for VerificationDocument, all routed through the
storage abstraction (app.core.storage) and file validation
(app.core.file_validation) — never touching the filesystem or trusting
client-declared content types directly.
"""

import math
import uuid
from datetime import UTC, date, datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.file_validation import scan_for_viruses, validate_document
from app.core.storage import StorageBackend, make_object_key
from app.models.verification_document import DocumentStatus, DocumentType, VerificationDocument

settings_max_size_default = 15 * 1024 * 1024


class DocumentNotFoundError(Exception):
    pass


class DocumentNotPendingError(Exception):
    """
    Raised by review_document when the target document's status isn't
    PENDING — matches app.services.provenance_service.AlreadyVerifiedError's
    pattern: review is a one-time, attributable action from a single
    starting state, not an idempotent status update. Covers all three
    non-reviewable cases (already VERIFIED, already REJECTED, or
    EXPIRED) with one guard, since none of them should ever be
    reviewable again.
    """


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
    PENDING; only review_document (below) ever sets VERIFIED/REJECTED.
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


async def review_document(
    db: AsyncSession,
    *,
    document: VerificationDocument,
    reviewer_id: uuid.UUID,
    decision: Literal["approve", "reject"],
    note: str | None = None,
) -> VerificationDocument:
    """
    THE enforcement point for Phase 1 of the admin document-verification
    review workflow (docs/adr/0029 decision #3) — this is the *only*
    function anywhere in this codebase that sets status=VERIFIED or
    status=REJECTED on a VerificationDocument, mirroring
    app.services.provenance_service.verify_provenance_record's role for
    ProvenanceRecord. Requires a real, attributable reviewer_id (see
    app.core.dependencies.CurrentUser + require_role(Role.ADMIN) at the
    router layer, never CompanyRole) — there is no system-reviewed or
    anonymous path.

    Only a PENDING document may be reviewed; anything else (already
    VERIFIED, already REJECTED, or EXPIRED) raises
    DocumentNotPendingError rather than silently overwriting a prior
    review decision. On approve, review_note is cleared to None even if
    a stale value existed (e.g. from a hypothetical future re-review
    path) — an approved document should never carry a rejection reason.

    Deliberately does NOT touch verification_score_service — scoring
    still treats any non-REJECTED/EXPIRED document as sufficient (see
    that module's _has_document_of_type), unchanged in this phase.
    """
    if document.status != DocumentStatus.PENDING:
        raise DocumentNotPendingError(str(document.id))

    document.status = DocumentStatus.VERIFIED if decision == "approve" else DocumentStatus.REJECTED
    document.verified_by = reviewer_id
    document.verified_at = datetime.now(UTC)
    document.review_note = note if decision == "reject" else None

    await db.commit()
    await db.refresh(document)
    return document


async def list_documents_by_status(
    db: AsyncSession, *, status: DocumentStatus, page: int, page_size: int
) -> tuple[list[VerificationDocument], int]:
    """
    Phase 2A — the admin verification queue's data source. Unlike every
    other list/get function in this module, this one is deliberately
    NOT scoped to a single company_id: it's the one place documents are
    queried across every company at once, for a platform admin working
    a review queue rather than a company's own Documents page. Same
    count-then-page shape as provenance_service.list_conflicts /
    list_provenance_for_entity.

    `company` is eager-loaded (selectinload, one extra query, not N+1)
    since the router needs each row's company_name for
    PendingVerificationDocumentPublic — see that schema's docstring for
    why this can't be a plain `model_validate(document)`.

    Does not change list_documents (still company-scoped, unaffected)
    or anything in verification_score_service — out of scope for this
    phase.
    """
    query = select(VerificationDocument).where(
        VerificationDocument.status == status,
        VerificationDocument.is_deleted.is_(False),
    )

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = int(count_result.scalar_one())

    query = (
        query.options(selectinload(VerificationDocument.company))
        .order_by(VerificationDocument.uploaded_at.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    return list(result.scalars().all()), total


def total_pages(total: int, page_size: int) -> int:
    """Matches the identical helper already duplicated per paginating service
    module in this codebase (e.g. provenance_service.total_pages, company_service.total_pages)."""
    return max(1, math.ceil(total / page_size))
