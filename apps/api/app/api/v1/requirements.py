"""
Requirement routes — Module 7A-1 (Requirement Intelligence foundation).
A new router file, mounted under /api/v1, separate from every existing
router — matching this phase's own instruction not to modify Consult,
Discover, or any previous module's routes.

Authenticated-only, ownership-scoped (CurrentUser required for both
routes; GET is scoped to the requirement's own creator). This is a
narrower policy than app.api.v1.products' public-read model — a
Requirement carries a user's own procurement intent, not shared/public
taxonomy data, so the closer precedent is session ownership
(app.api.v1.auth's revoke_session, 404-not-403-if-not-yours), not
Product's public GET. See this module's own completion report for why
anonymous submission was considered and deliberately not built here.

Deliberately does NOT expose a /matches route — matching belongs to
Phase 7A-2, a distinct future module (see app.services.requirement_service's
own docstring on the boundary this maintains).
"""

import uuid

from fastapi import APIRouter, HTTPException, status

from app.core.dependencies import CurrentUser
from app.core.responses import ApiSuccess, success_response
from app.db.session import DbSession
from app.models.requirement import Requirement
from app.schemas.requirement import (
    RequirementCreate,
    RequirementDetail,
    RequirementSpecificationCriterionPublic,
)
from app.services import requirement_service
from app.services.requirement_service import (
    CategoryNotFoundError,
    CategoryRequiredForCriteriaError,
    InvalidCriterionValueError,
    InvalidSpecificationError,
)

router = APIRouter(prefix="/requirements", tags=["requirements"])


def _to_detail(requirement: Requirement) -> RequirementDetail:
    """
    Builds RequirementDetail explicitly rather than a blind
    RequirementDetail.model_validate(requirement) — mirrors
    app.api.v1.products._to_detail's own reasoning exactly:
    RequirementSpecificationCriterionPublic's `specification_name`
    isn't a direct attribute on the ORM row, only reachable via its
    `.specification` relationship, so Pydantic's from_attributes
    auto-mapping can't resolve it alone.
    """
    return RequirementDetail(
        id=requirement.id,
        created_by=requirement.created_by,
        raw_query=requirement.raw_query,
        product_category_id=requirement.product_category_id,
        industry=requirement.industry,
        country=requirement.country,
        state=requirement.state,
        city=requirement.city,
        certifications=requirement.certifications,
        quantity=requirement.quantity,
        budget=requirement.budget,
        timeline=requirement.timeline,
        status=requirement.status,
        extraction_confidence=requirement.extraction_confidence,
        criteria=[
            RequirementSpecificationCriterionPublic(
                id=criterion.id,
                specification_id=criterion.specification_id,
                specification_name=criterion.specification.name,
                operator=criterion.operator,
                value=criterion.value,
            )
            for criterion in requirement.criteria
        ],
        created_at=requirement.created_at,
        updated_at=requirement.updated_at,
    )


@router.post("", response_model=ApiSuccess[RequirementDetail], status_code=status.HTTP_201_CREATED)
async def create_requirement(
    payload: RequirementCreate, db: DbSession, current_user: CurrentUser
) -> ApiSuccess[RequirementDetail]:
    """
    Any authenticated user may submit a Requirement — mirrors
    app.api.v1.products.create_product's own precedent (any
    authenticated user may create a Product; no finer-grained RBAC
    exists for this kind of shared-vocabulary-referencing action yet).
    Always created as SUBMITTED — there is no draft-editing flow in
    this phase (see app.models.requirement.RequirementStatus's own
    docstring).
    """
    try:
        requirement = await requirement_service.create_requirement(
            db, payload, created_by=current_user.id
        )
    except CategoryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "CATEGORY_NOT_FOUND",
                "message": "No product category with that ID exists.",
            },
        ) from exc
    except CategoryRequiredForCriteriaError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "CATEGORY_REQUIRED_FOR_CRITERIA",
                "message": "product_category_id is required when criteria are given.",
            },
        ) from exc
    except InvalidSpecificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INVALID_SPECIFICATION",
                "message": "One or more criteria reference a specification that doesn't exist or "
                "doesn't belong to the given product category.",
            },
        ) from exc
    except InvalidCriterionValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_CRITERION_VALUE", "message": str(exc)},
        ) from exc
    return success_response(_to_detail(requirement))


@router.get("/{requirement_id}", response_model=ApiSuccess[RequirementDetail])
async def get_requirement(
    requirement_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> ApiSuccess[RequirementDetail]:
    requirement = await requirement_service.get_requirement_for_user(
        db, requirement_id, current_user.id
    )
    if requirement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "REQUIREMENT_NOT_FOUND",
                "message": "No requirement with that ID exists.",
            },
        )
    return success_response(_to_detail(requirement))
