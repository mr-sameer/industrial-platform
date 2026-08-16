"""
Acquisition routes — Module 5B. Deliberately restricted to
Role.ADMIN for anything that creates or runs a job — per this module's
own security instruction ("do not allow arbitrary users to execute
arbitrary collectors"), this is a stricter bar than the "any
authenticated user" pattern Modules 4B/5A used for Product/Provenance
creation, chosen because job creation is the one action in this whole
subsystem that actually *executes code* (an adapter's collect()) on
the server, not just writes a row.

Read routes (job status, job events) use the same Role.ADMIN
restriction — this is an internal operations surface, not a public
dataset, matching "do not expose dangerous public ingestion
endpoints."
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.dependencies import CurrentUser, require_role
from app.core.responses import ApiSuccess, success_response
from app.db.session import DbSession
from app.models.acquisition_job import AcquisitionJobStatus
from app.models.user import Role
from app.schemas.acquisition import (
    AcquisitionJobCreate,
    AcquisitionJobEventPage,
    AcquisitionJobEventPublic,
    AcquisitionJobPage,
    AcquisitionJobPublic,
)
from app.services import acquisition_service
from app.services.acquisition_service import InvalidJobConfigurationError
from app.services.provenance_service import SourceNotFoundError

router = APIRouter(prefix="/acquisition", tags=["acquisition"])

RequireAdmin = Annotated[object, Depends(require_role(Role.ADMIN))]


@router.post(
    "/jobs", response_model=ApiSuccess[AcquisitionJobPublic], status_code=status.HTTP_201_CREATED
)
async def create_job(
    payload: AcquisitionJobCreate, db: DbSession, current_user: CurrentUser, _admin: RequireAdmin
) -> ApiSuccess[AcquisitionJobPublic]:
    """
    Creates AND runs a job synchronously within this request — no
    background task queue exists yet in this phase (a documented
    limitation, not an oversight). The response reflects the job's
    real terminal state (SUCCEEDED/FAILED), never a fabricated
    "in progress" placeholder.
    """
    try:
        job = await acquisition_service.create_and_run_job(db, payload, created_by=current_user.id)
    except SourceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SOURCE_NOT_FOUND", "message": "No source with that ID exists."},
        ) from exc
    except InvalidJobConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_COLLECTOR_TYPE", "message": str(exc)},
        ) from exc
    return success_response(AcquisitionJobPublic.model_validate(job))


@router.get("/jobs/{job_id}", response_model=ApiSuccess[AcquisitionJobPublic])
async def get_job(
    job_id: uuid.UUID, db: DbSession, _admin: RequireAdmin
) -> ApiSuccess[AcquisitionJobPublic]:
    job = await acquisition_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": "No acquisition job with that ID exists."},
        )
    return success_response(AcquisitionJobPublic.model_validate(job))


@router.get("/jobs", response_model=ApiSuccess[AcquisitionJobPage])
async def list_jobs(
    db: DbSession,
    _admin: RequireAdmin,
    source_id: Annotated[uuid.UUID | None, Query()] = None,
    status_filter: Annotated[AcquisitionJobStatus | None, Query(alias="status")] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiSuccess[AcquisitionJobPage]:
    jobs, total = await acquisition_service.list_jobs(
        db, source_id=source_id, status_filter=status_filter, page=page, page_size=page_size
    )
    return success_response(
        AcquisitionJobPage(
            items=[AcquisitionJobPublic.model_validate(j) for j in jobs],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=acquisition_service.total_pages(total, page_size),
        )
    )


@router.get("/jobs/{job_id}/events", response_model=ApiSuccess[AcquisitionJobEventPage])
async def list_job_events(
    job_id: uuid.UUID,
    db: DbSession,
    _admin: RequireAdmin,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> ApiSuccess[AcquisitionJobEventPage]:
    job = await acquisition_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": "No acquisition job with that ID exists."},
        )
    events, total = await acquisition_service.list_job_events(
        db, job_id, page=page, page_size=page_size
    )
    return success_response(
        AcquisitionJobEventPage(
            items=[AcquisitionJobEventPublic.model_validate(e) for e in events],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=acquisition_service.total_pages(total, page_size),
        )
    )
