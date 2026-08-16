"""
Company promotion routes — Module 5C. A new file, mounted under
/api/v1, separate from every existing router — matching this phase's
own instruction not to modify Module 5A (app/api/v1/provenance.py) or
Module 5B (app/api/v1/acquisition.py). Both existing routers are
reused via their real service layers (provenance_service,
acquisition_service) and via the new, generic
company_promotion_service — nothing in this file duplicates their
logic.

Role.ADMIN-gated, matching Module 5B's own established pattern for
this subsystem — reviewing and promoting acquired data is exactly the
kind of consequential, code-executing action that pattern exists for.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.companies import _to_detail
from app.core.dependencies import CurrentUser, require_role
from app.core.responses import ApiSuccess, success_response
from app.db.session import DbSession
from app.models.company_member import CompanyRole
from app.models.user import Role
from app.schemas.company import CompanyDetail
from app.schemas.provenance import RawObservationPublic
from app.services import company_promotion_service, provenance_service
from app.services.company_promotion_service import (
    DuplicateCinError,
    MissingRequiredFieldError,
    RawObservationNotFoundForPromotionError,
)

router = APIRouter(prefix="/acquisition/observations", tags=["acquisition-review"])

RequireAdmin = Annotated[object, Depends(require_role(Role.ADMIN))]


@router.get("/{observation_id}", response_model=ApiSuccess[RawObservationPublic])
async def get_observation_for_review(
    observation_id: uuid.UUID, db: DbSession, _admin: RequireAdmin
) -> ApiSuccess[RawObservationPublic]:
    """
    Read-only — lets a reviewer inspect a raw observation's actual
    content before deciding whether to promote it. Reuses Module 5A's
    own provenance_service.get_raw_observation unchanged; this route
    is new (Module 5A never exposed one), added here rather than in
    app/api/v1/provenance.py specifically to avoid modifying that
    frozen file.
    """
    observation = await provenance_service.get_raw_observation(db, observation_id)
    if observation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "OBSERVATION_NOT_FOUND",
                "message": "No raw observation with that ID exists.",
            },
        )
    return success_response(RawObservationPublic.model_validate(observation))


@router.post(
    "/{observation_id}/promote",
    response_model=ApiSuccess[CompanyDetail],
    status_code=status.HTTP_201_CREATED,
)
async def promote_observation(
    observation_id: uuid.UUID, db: DbSession, current_user: CurrentUser, _admin: RequireAdmin
) -> ApiSuccess[CompanyDetail]:
    """
    The explicit, human-gated review action — this call itself IS
    "review" for this pilot (per the approved architecture's own
    framing: a human confirms before any Company row is created). Never
    triggered automatically by acquisition. Never marks the resulting
    Company as ForgeX-verified — see company_promotion_service's own
    docstring for why that distinction is preserved deliberately.
    """
    try:
        company = await company_promotion_service.promote_raw_observation_to_company(
            db, observation_id, reviewer_id=current_user.id
        )
    except RawObservationNotFoundForPromotionError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "OBSERVATION_NOT_FOUND",
                "message": "No raw observation with that ID exists.",
            },
        ) from exc
    except DuplicateCinError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "DUPLICATE_CIN",
                "message": "A Company with this CIN already exists — not auto-merged, review manually.",
            },
        ) from exc
    except MissingRequiredFieldError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "MISSING_REQUIRED_FIELD", "message": str(exc)},
        ) from exc
    return success_response(await _to_detail(db, company, CompanyRole.OWNER))
