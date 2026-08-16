"""
Entity resolution routes — Module 5D. A new file, mounted under
/api/v1, separate from every existing router. Role.ADMIN-gated for
every route (including reads) — matching Module 5B/5C's own
established pattern for this subsystem: an internal review-queue
surface, never a public entity-resolution endpoint (per this module's
own explicit instruction).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.api.v1.companies import _to_detail
from app.core.dependencies import CurrentUser, require_role
from app.core.responses import ApiSuccess, success_response
from app.db.session import DbSession
from app.models.company import Company
from app.models.company_member import CompanyRole
from app.models.entity_resolution_candidate import ResolutionState
from app.models.user import Role
from app.schemas.company import CompanyDetail
from app.schemas.entity_resolution import (
    CandidateGenerateRequest,
    DecisionRequest,
    EntityResolutionCandidatePage,
    EntityResolutionCandidatePublic,
)
from app.services import entity_resolution_service
from app.services.company_promotion_service import DuplicateCinError, MissingRequiredFieldError
from app.services.entity_resolution_service import (
    AlreadyDecidedError,
    InvalidDecisionError,
    RawObservationNotFoundError,
)

router = APIRouter(prefix="/entity-resolution", tags=["entity-resolution"])

RequireAdmin = Annotated[object, Depends(require_role(Role.ADMIN))]


@router.post(
    "/candidates",
    response_model=ApiSuccess[EntityResolutionCandidatePublic],
    status_code=status.HTTP_201_CREATED,
)
async def generate_candidate(
    payload: CandidateGenerateRequest, db: DbSession, _admin: RequireAdmin
) -> ApiSuccess[EntityResolutionCandidatePublic]:
    """
    Computes and persists a candidate for the given raw observation —
    a pure read-and-analyze operation against existing Companies, never
    a write to canonical data (see entity_resolution_service's own
    docstring: only decide() can touch canonical data, and only after
    an explicit decision).
    """
    try:
        candidate = await entity_resolution_service.generate_candidate_for_observation(
            db, payload.raw_observation_id
        )
    except RawObservationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "OBSERVATION_NOT_FOUND",
                "message": "No raw observation with that ID exists.",
            },
        ) from exc
    return success_response(EntityResolutionCandidatePublic.model_validate(candidate))


@router.get(
    "/candidates/{candidate_id}", response_model=ApiSuccess[EntityResolutionCandidatePublic]
)
async def get_candidate(
    candidate_id: uuid.UUID, db: DbSession, _admin: RequireAdmin
) -> ApiSuccess[EntityResolutionCandidatePublic]:
    candidate = await entity_resolution_service.get_candidate(db, candidate_id)
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "CANDIDATE_NOT_FOUND",
                "message": "No entity resolution candidate with that ID exists.",
            },
        )
    return success_response(EntityResolutionCandidatePublic.model_validate(candidate))


@router.get("/candidates", response_model=ApiSuccess[EntityResolutionCandidatePage])
async def list_candidates(
    db: DbSession,
    _admin: RequireAdmin,
    resolution_state: Annotated[ResolutionState | None, Query()] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiSuccess[EntityResolutionCandidatePage]:
    candidates, total = await entity_resolution_service.list_candidates(
        db, resolution_state=resolution_state, page=page, page_size=page_size
    )
    return success_response(
        EntityResolutionCandidatePage(
            items=[EntityResolutionCandidatePublic.model_validate(c) for c in candidates],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=entity_resolution_service.total_pages(total, page_size),
        )
    )


@router.post(
    "/candidates/{candidate_id}/decide", response_model=ApiSuccess[EntityResolutionCandidatePublic]
)
async def decide_candidate(
    candidate_id: uuid.UUID,
    payload: DecisionRequest,
    db: DbSession,
    current_user: CurrentUser,
    _admin: RequireAdmin,
) -> ApiSuccess[EntityResolutionCandidatePublic]:
    """
    The one and only route that can cause canonical data to change as
    a result of entity resolution — always an explicit, authenticated,
    attributed human action (Phase 9's safety principle, enforced by
    construction: the service layer literally has no other path to
    canonical data from a candidate).
    """
    candidate = await entity_resolution_service.get_candidate(db, candidate_id)
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "CANDIDATE_NOT_FOUND",
                "message": "No entity resolution candidate with that ID exists.",
            },
        )
    try:
        updated, _company = await entity_resolution_service.decide(
            db, candidate, decision=payload.decision, decided_by=current_user.id
        )
    except AlreadyDecidedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "ALREADY_DECIDED",
                "message": "This candidate has already been decided.",
            },
        ) from exc
    except InvalidDecisionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_DECISION", "message": str(exc)},
        ) from exc
    except DuplicateCinError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "DUPLICATE_CIN", "message": str(exc)},
        ) from exc
    except MissingRequiredFieldError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "MISSING_REQUIRED_FIELD", "message": str(exc)},
        ) from exc
    return success_response(EntityResolutionCandidatePublic.model_validate(updated))


@router.get("/candidates/{candidate_id}/company", response_model=ApiSuccess[CompanyDetail])
async def get_candidate_company(
    candidate_id: uuid.UUID, db: DbSession, _admin: RequireAdmin
) -> ApiSuccess[CompanyDetail]:
    """Convenience read — the candidate company a reviewer would be
    looking at while deciding, shown with the same detail a normal
    company page would use."""
    candidate = await entity_resolution_service.get_candidate(db, candidate_id)
    if candidate is None or candidate.candidate_company_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "CANDIDATE_COMPANY_NOT_FOUND",
                "message": "This candidate has no candidate company.",
            },
        )
    company_result = await db.execute(
        select(Company).where(Company.id == candidate.candidate_company_id)
    )
    company = company_result.scalar_one_or_none()
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "COMPANY_NOT_FOUND",
                "message": "The candidate company no longer exists.",
            },
        )
    return success_response(await _to_detail(db, company, CompanyRole.VIEWER))
