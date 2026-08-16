"""
Data quality & verification operations routes — Module 5E. A new
file, mounted under /api/v1, separate from Module 5A's
app/api/v1/provenance.py (frozen, not modified). Role.ADMIN-gated
throughout — an internal operational surface, matching Module 5B/5C/
5D's own established pattern; per this module's own explicit
instruction, no public endpoint allows arbitrary verification.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.core.dependencies import CurrentUser, require_role
from app.core.responses import ApiSuccess, success_response
from app.data_quality.freshness import classify_freshness
from app.data_quality.risk_classification import classify_field
from app.db.session import DbSession
from app.models.provenance_record import ProvenanceRecord
from app.models.user import Role
from app.schemas.data_quality import (
    EntityQualityReport,
    FieldQualityEntry,
    LinkEvidenceRequest,
    MarkExpiredRequest,
    ProvenanceRecordWithQuality,
    QualityScore,
    RejectRequest,
    ReviewQueueItem,
    ReviewQueuePage,
)
from app.services import data_quality_service, provenance_service
from app.services.data_quality_service import (
    NoDocumentEvidenceError,
    RecordNotUnderReviewableStateError,
)

router = APIRouter(prefix="/data-quality", tags=["data-quality"])

RequireAdmin = Annotated[object, Depends(require_role(Role.ADMIN))]


@router.get("/{entity_type}/{entity_id}", response_model=ApiSuccess[EntityQualityReport])
async def get_entity_quality(
    entity_type: Annotated[str, Path(pattern="^(company|product)$")],
    entity_id: uuid.UUID,
    db: DbSession,
    _admin: RequireAdmin,
) -> ApiSuccess[EntityQualityReport]:
    """
    The field-level quality view, Sections 3/4/15 — the score and its
    breakdown are always returned together in this one response,
    enforced structurally (a single response model with both fields
    required), not by convention.
    """
    fields = await data_quality_service.get_field_quality(
        db, entity_type=entity_type, entity_id=entity_id
    )
    score = await data_quality_service.get_quality_score(
        db, entity_type=entity_type, entity_id=entity_id
    )
    return success_response(
        EntityQualityReport(
            entity_type=entity_type,
            entity_id=entity_id,
            fields=[FieldQualityEntry.model_validate(f) for f in fields],
            quality_score=QualityScore.model_validate(score),
        )
    )


@router.get("/review-queue", response_model=ApiSuccess[ReviewQueuePage])
async def get_review_queue(
    db: DbSession,
    _admin: RequireAdmin,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiSuccess[ReviewQueuePage]:
    records, total = await data_quality_service.list_review_queue(
        db, page=page, page_size=page_size
    )
    items = [
        ReviewQueueItem(
            id=r.id,
            entity_type=r.entity_type.value,
            company_id=r.company_id,
            product_id=r.product_id,
            field_name=r.field_name,
            value_observed=r.value_observed,
            status=r.status.value,
            risk_level=classify_field(r.entity_type.value, r.field_name).value,
            has_open_conflict=r.conflict_id is not None,
            created_at=r.created_at,
        )
        for r in records
    ]
    return success_response(
        ReviewQueuePage(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=max(1, -(-total // page_size)),
        )
    )


async def _get_record_or_404(db: DbSession, record_id: uuid.UUID) -> ProvenanceRecord:
    record = await provenance_service.get_provenance_record(db, record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "PROVENANCE_RECORD_NOT_FOUND",
                "message": "No provenance record with that ID exists.",
            },
        )
    return record


def _to_quality_response(record: ProvenanceRecord) -> ProvenanceRecordWithQuality:
    freshness = classify_freshness(record.field_name, record.last_observed_at)
    risk = classify_field(record.entity_type.value, record.field_name)
    return ProvenanceRecordWithQuality(
        id=record.id,
        field_name=record.field_name,
        value_observed=record.value_observed,
        status=record.status.value,
        confidence=record.confidence,
        risk_level=risk.value,
        freshness=freshness.value,
        review_note=record.review_note,
        expires_at=record.expires_at,
        verification_document_id=record.verification_document_id,
    )


@router.post("/records/{record_id}/review", response_model=ApiSuccess[ProvenanceRecordWithQuality])
async def mark_under_review(
    record_id: uuid.UUID, db: DbSession, current_user: CurrentUser, _admin: RequireAdmin
) -> ApiSuccess[ProvenanceRecordWithQuality]:
    record = await _get_record_or_404(db, record_id)
    try:
        updated = await data_quality_service.mark_under_review(
            db, record, reviewer_id=current_user.id
        )
    except RecordNotUnderReviewableStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "INVALID_TRANSITION", "message": str(exc)},
        ) from exc
    return success_response(_to_quality_response(updated))


@router.post("/records/{record_id}/reject", response_model=ApiSuccess[ProvenanceRecordWithQuality])
async def reject_record(
    record_id: uuid.UUID,
    payload: RejectRequest,
    db: DbSession,
    current_user: CurrentUser,
    _admin: RequireAdmin,
) -> ApiSuccess[ProvenanceRecordWithQuality]:
    record = await _get_record_or_404(db, record_id)
    try:
        updated = await data_quality_service.reject(
            db, record, reviewer_id=current_user.id, note=payload.note
        )
    except RecordNotUnderReviewableStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "INVALID_TRANSITION", "message": str(exc)},
        ) from exc
    return success_response(_to_quality_response(updated))


@router.post(
    "/records/{record_id}/mark-expired", response_model=ApiSuccess[ProvenanceRecordWithQuality]
)
async def mark_expired_record(
    record_id: uuid.UUID,
    payload: MarkExpiredRequest,
    db: DbSession,
    current_user: CurrentUser,
    _admin: RequireAdmin,
) -> ApiSuccess[ProvenanceRecordWithQuality]:
    record = await _get_record_or_404(db, record_id)
    try:
        updated = await data_quality_service.mark_expired(
            db, record, reviewer_id=current_user.id, note=payload.note
        )
    except RecordNotUnderReviewableStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "INVALID_TRANSITION", "message": str(exc)},
        ) from exc
    return success_response(_to_quality_response(updated))


@router.post(
    "/records/{record_id}/link-evidence", response_model=ApiSuccess[ProvenanceRecordWithQuality]
)
async def link_evidence_route(
    record_id: uuid.UUID,
    payload: LinkEvidenceRequest,
    db: DbSession,
    current_user: CurrentUser,
    _admin: RequireAdmin,
) -> ApiSuccess[ProvenanceRecordWithQuality]:
    """
    Attaches evidence only — per Section 9, this never verifies the
    claim by itself. A reviewer still calls the existing, unmodified
    POST /provenance/records/{id}/verify (Module 5A) as a distinct,
    deliberate second step.
    """
    record = await _get_record_or_404(db, record_id)
    try:
        updated = await data_quality_service.link_evidence(
            db, record, document_id=payload.verification_document_id, linked_by=current_user.id
        )
    except NoDocumentEvidenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "DOCUMENT_NOT_FOUND",
                "message": "No verification document with that ID exists.",
            },
        ) from exc
    return success_response(_to_quality_response(updated))
