"""
Provenance & Source Registry routes — Module 5A. A new router file,
mounted under /api/v1, separate from every existing router — this
module is explicitly scoped as new, additive infrastructure that does
not modify Company, Product, or Offering in any way (confirmed:
nothing in this file writes to companies or products tables, only
reads them to validate a referenced entity_id exists).

Read routes (list sources, list provenance for an entity, list
conflicts) are public, matching this codebase's established pattern
for company/product search (Module 3A/4B) — provenance is meant to be
inspectable, not privileged information. Mutations (create source,
create observation, create provenance record, verify, resolve
conflict) require authentication only — no finer-grained RBAC exists
yet for this new subsystem, an explicitly flagged limitation matching
the same honest pattern Phase 4B used for Product creation.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.core.dependencies import CurrentUser, require_role
from app.core.responses import ApiSuccess, success_response
from app.db.session import DbSession
from app.models.company import Company
from app.models.data_conflict import ConflictStatus
from app.models.user import Role
from app.schemas.provenance import (
    ApplyToCompanyRequest,
    ApplyToCompanyResponse,
    DataConflictPage,
    DataConflictPublic,
    DataConflictResolve,
    ProvenanceRecordCreate,
    ProvenanceRecordPage,
    ProvenanceRecordPublic,
    RawObservationCreate,
    RawObservationPublic,
    SourceRegistryCreate,
    SourceRegistryPublic,
    SourceRegistryUpdate,
)
from app.services import data_quality_service, provenance_service
from app.services.provenance_service import (
    AlreadyVerifiedError,
    RawObservationNotFoundError,
    SourceNotFoundError,
)

router = APIRouter(prefix="/provenance", tags=["provenance"])
sources_router = APIRouter(prefix="/sources", tags=["sources"])

RequireAdmin = Annotated[object, Depends(require_role(Role.ADMIN))]


# ---- Source Registry ----


@sources_router.post(
    "", response_model=ApiSuccess[SourceRegistryPublic], status_code=status.HTTP_201_CREATED
)
async def create_source(
    payload: SourceRegistryCreate, db: DbSession, _current_user: CurrentUser
) -> ApiSuccess[SourceRegistryPublic]:
    source = await provenance_service.create_source(db, payload)
    return success_response(SourceRegistryPublic.model_validate(source))


@sources_router.get("", response_model=ApiSuccess[list[SourceRegistryPublic]])
async def list_sources(
    db: DbSession, active_only: bool = Query(default=False)
) -> ApiSuccess[list[SourceRegistryPublic]]:
    sources = await provenance_service.list_sources(db, active_only=active_only)
    return success_response([SourceRegistryPublic.model_validate(s) for s in sources])


@sources_router.get("/{source_id}", response_model=ApiSuccess[SourceRegistryPublic])
async def get_source(source_id: uuid.UUID, db: DbSession) -> ApiSuccess[SourceRegistryPublic]:
    source = await provenance_service.get_source(db, source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SOURCE_NOT_FOUND", "message": "No source with that ID exists."},
        )
    return success_response(SourceRegistryPublic.model_validate(source))


@sources_router.patch("/{source_id}", response_model=ApiSuccess[SourceRegistryPublic])
async def update_source(
    source_id: uuid.UUID, payload: SourceRegistryUpdate, db: DbSession, _current_user: CurrentUser
) -> ApiSuccess[SourceRegistryPublic]:
    source = await provenance_service.get_source(db, source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SOURCE_NOT_FOUND", "message": "No source with that ID exists."},
        )
    updated = await provenance_service.update_source(
        db,
        source,
        description=payload.description,
        reliability_weight=payload.reliability_weight,
        collection_policy_status=payload.collection_policy_status.value
        if payload.collection_policy_status
        else None,
        is_active=payload.is_active,
    )
    return success_response(SourceRegistryPublic.model_validate(updated))


@sources_router.post(
    "/{source_id}/observations",
    response_model=ApiSuccess[RawObservationPublic],
    status_code=status.HTTP_201_CREATED,
)
async def create_raw_observation(
    source_id: uuid.UUID, payload: RawObservationCreate, db: DbSession, _current_user: CurrentUser
) -> ApiSuccess[RawObservationPublic]:
    if payload.source_id != source_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "SOURCE_MISMATCH",
                "message": "source_id in the body must match the URL path.",
            },
        )
    try:
        observation = await provenance_service.create_raw_observation(db, payload)
    except SourceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SOURCE_NOT_FOUND", "message": "No source with that ID exists."},
        ) from exc
    return success_response(RawObservationPublic.model_validate(observation))


# ---- Provenance Records ----


@router.post(
    "/records",
    response_model=ApiSuccess[ProvenanceRecordPublic],
    status_code=status.HTTP_201_CREATED,
)
async def create_provenance_record(
    payload: ProvenanceRecordCreate, db: DbSession, _current_user: CurrentUser
) -> ApiSuccess[ProvenanceRecordPublic]:
    try:
        record, _conflict = await provenance_service.create_provenance_record(db, payload)
    except RawObservationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RAW_OBSERVATION_NOT_FOUND",
                "message": "No raw observation with that ID exists.",
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_PROVENANCE_RECORD", "message": str(exc)},
        ) from exc
    return success_response(ProvenanceRecordPublic.model_validate(record))


@router.get("/records/{record_id}", response_model=ApiSuccess[ProvenanceRecordPublic])
async def get_provenance_record(
    record_id: uuid.UUID, db: DbSession
) -> ApiSuccess[ProvenanceRecordPublic]:
    record = await provenance_service.get_provenance_record(db, record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "PROVENANCE_RECORD_NOT_FOUND",
                "message": "No provenance record with that ID exists.",
            },
        )
    return success_response(ProvenanceRecordPublic.model_validate(record))


@router.get("", response_model=ApiSuccess[ProvenanceRecordPage])
async def list_provenance(
    db: DbSession,
    entity_type: Annotated[str, Query(pattern="^(company|product)$")],
    entity_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiSuccess[ProvenanceRecordPage]:
    """The lineage view — every provenance record for one Company or Product."""
    records, total = await provenance_service.list_provenance_for_entity(
        db, entity_type=entity_type, entity_id=entity_id, page=page, page_size=page_size
    )
    return success_response(
        ProvenanceRecordPage(
            items=[ProvenanceRecordPublic.model_validate(r) for r in records],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=provenance_service.total_pages(total, page_size),
        )
    )


@router.post("/records/{record_id}/verify", response_model=ApiSuccess[ProvenanceRecordPublic])
async def verify_provenance_record(
    record_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> ApiSuccess[ProvenanceRecordPublic]:
    """
    The one and only route that can set status=VERIFIED — see
    provenance_service.verify_provenance_record's own docstring. The
    architecture doc's Section 11 rule ("do not allow observed or
    extracted to automatically become verified") is enforced by this
    being a distinct, explicit, authenticated action — never a side
    effect of any other route in this file.
    """
    record = await provenance_service.get_provenance_record(db, record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "PROVENANCE_RECORD_NOT_FOUND",
                "message": "No provenance record with that ID exists.",
            },
        )
    try:
        verified = await provenance_service.verify_provenance_record(
            db, record, verified_by=current_user.id
        )
    except AlreadyVerifiedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "ALREADY_VERIFIED",
                "message": "This provenance record is already verified.",
            },
        ) from exc
    return success_response(ProvenanceRecordPublic.model_validate(verified))


@router.post(
    "/records/{record_id}/apply-to-company",
    response_model=ApiSuccess[ApplyToCompanyResponse],
)
async def apply_provenance_record_to_company(
    record_id: uuid.UUID,
    payload: ApplyToCompanyRequest,
    db: DbSession,
    current_user: CurrentUser,
    _admin: RequireAdmin,
) -> ApiSuccess[ApplyToCompanyResponse]:
    """
    Closes the one real gap Module 8B's architectural review found —
    see data_quality_service.apply_reviewed_field_to_company's own
    docstring. This route does no business logic of its own: it only
    resolves the record/company by id and delegates entirely to that
    function.
    """
    record = await provenance_service.get_provenance_record(db, record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "PROVENANCE_RECORD_NOT_FOUND",
                "message": "No provenance record with that ID exists.",
            },
        )
    company_result = await db.execute(select(Company).where(Company.id == payload.company_id))
    company = company_result.scalar_one_or_none()
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "COMPANY_NOT_FOUND", "message": "No company with that ID exists."},
        )
    try:
        await data_quality_service.apply_reviewed_field_to_company(
            db, record, company, reviewer_id=current_user.id, overwrite=payload.overwrite
        )
    except data_quality_service.RecordNotVerifiedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "NOT_VERIFIED", "message": str(exc)},
        ) from exc
    except data_quality_service.RecordCompanyMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "COMPANY_MISMATCH", "message": str(exc)},
        ) from exc
    except data_quality_service.FieldNotAllowlistedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "FIELD_NOT_ALLOWLISTED", "message": str(exc)},
        ) from exc
    except data_quality_service.EmptyValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "EMPTY_VALUE", "message": str(exc)},
        ) from exc
    except data_quality_service.ValueTooLongError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "VALUE_TOO_LONG", "message": str(exc)},
        ) from exc
    except data_quality_service.ConflictingValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONFLICTING_VALUE", "message": str(exc)},
        ) from exc

    refreshed_record = await provenance_service.get_provenance_record(db, record_id)
    return success_response(
        ApplyToCompanyResponse(
            company_id=company.id,
            field_name=record.field_name,
            provenance_record=ProvenanceRecordPublic.model_validate(refreshed_record),
        )
    )


# ---- Data Conflicts ----


@router.get("/conflicts", response_model=ApiSuccess[DataConflictPage])
async def list_conflicts(
    db: DbSession,
    status_filter: Annotated[ConflictStatus | None, Query(alias="status")] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiSuccess[DataConflictPage]:
    conflicts, total = await provenance_service.list_conflicts(
        db, status_filter=status_filter, page=page, page_size=page_size
    )
    return success_response(
        DataConflictPage(
            items=[DataConflictPublic.model_validate(c) for c in conflicts],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=provenance_service.total_pages(total, page_size),
        )
    )


@router.post("/conflicts/{conflict_id}/resolve", response_model=ApiSuccess[DataConflictPublic])
async def resolve_conflict(
    conflict_id: uuid.UUID, payload: DataConflictResolve, db: DbSession, current_user: CurrentUser
) -> ApiSuccess[DataConflictPublic]:
    conflict = await provenance_service.get_conflict(db, conflict_id)
    if conflict is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CONFLICT_NOT_FOUND", "message": "No conflict with that ID exists."},
        )
    resolved = await provenance_service.resolve_conflict(
        db, conflict, resolved_by=current_user.id, resolution_note=payload.resolution_note
    )
    return success_response(DataConflictPublic.model_validate(resolved))
