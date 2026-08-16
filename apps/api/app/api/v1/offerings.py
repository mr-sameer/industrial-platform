"""
Offering mutation routes — Phase 4B. A separate router file mounted
under the same `/companies` prefix as app.api.v1.companies and
app.api.v1.company_verification (matching that second file's own
"separate file, shared prefix" pattern) — specifically so this module
can reuse app.core.company_authorization's `require_company_role`
completely unchanged. That dependency resolves `company_id` from the
URL path only, by design (its own module docstring: "never trusts a
role/company claimed by the client anywhere else, e.g. a request
body") — which is exactly why OfferingCreate/Update
(app.schemas.product) do not carry a company_id field at all.

Reading a product's offerings (which companies offer it) is public and
lives in app.api.v1.products instead — only *mutating* your own
company's offerings needs authorization.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.company_authorization import CompanyOr404, require_company_role
from app.core.responses import ApiSuccess, success_response
from app.db.session import DbSession
from app.models.company_member import CompanyMember, CompanyRole
from app.models.offering import Offering
from app.schemas.product import (
    OfferingCompanySummary,
    OfferingCreate,
    OfferingProductSummary,
    OfferingPublic,
    OfferingUpdate,
)
from app.services import offering_service, product_service
from app.services.offering_service import DuplicateOfferingError

router = APIRouter(prefix="/companies", tags=["offerings"])


def _to_public(offering: Offering) -> OfferingPublic:
    return OfferingPublic(
        id=offering.id,
        company=OfferingCompanySummary.model_validate(offering.company),
        product=OfferingProductSummary.model_validate(offering.product),
        role=offering.role,
        moq=offering.moq,
        lead_time=offering.lead_time,
        capacity=offering.capacity,
        country=offering.country,
        verification_status=offering.verification_status,
        status=offering.status,
        created_at=offering.created_at,
        updated_at=offering.updated_at,
    )


@router.post(
    "/{company_id}/offerings",
    response_model=ApiSuccess[OfferingPublic],
    status_code=status.HTTP_201_CREATED,
)
async def create_offering(
    company_id: uuid.UUID,
    payload: OfferingCreate,
    db: DbSession,
    _company: CompanyOr404,
    membership: Annotated[CompanyMember, Depends(require_company_role(CompanyRole.EDITOR))],
) -> ApiSuccess[OfferingPublic]:
    """Editor+ — matching Module 3A's company-profile-edit permission
    level (docs/domain/09-permission-matrix.md), the same level
    company_verification.py uses for business-info/branding edits."""
    product = await product_service.get_product(db, payload.product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PRODUCT_NOT_FOUND", "message": "No product with that ID exists."},
        )
    try:
        offering = await offering_service.create_offering(db, company_id, payload)
    except DuplicateOfferingError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "DUPLICATE_OFFERING",
                "message": "This company already has an offering for this product with this role.",
            },
        ) from exc
    return success_response(_to_public(offering))


@router.patch("/{company_id}/offerings/{offering_id}", response_model=ApiSuccess[OfferingPublic])
async def update_offering(
    company_id: uuid.UUID,
    offering_id: uuid.UUID,
    payload: OfferingUpdate,
    db: DbSession,
    _company: CompanyOr404,
    membership: Annotated[CompanyMember, Depends(require_company_role(CompanyRole.EDITOR))],
) -> ApiSuccess[OfferingPublic]:
    offering = await offering_service.get_offering(db, offering_id)
    if offering is None or offering.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "OFFERING_NOT_FOUND",
                "message": "No offering with that ID exists for this company.",
            },
        )
    try:
        updated = await offering_service.update_offering(db, offering, payload)
    except DuplicateOfferingError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "DUPLICATE_OFFERING",
                "message": "This change would duplicate an existing offering (same company, product, and role).",
            },
        ) from exc
    return success_response(_to_public(updated))


@router.delete("/{company_id}/offerings/{offering_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_offering(
    company_id: uuid.UUID,
    offering_id: uuid.UUID,
    db: DbSession,
    _company: CompanyOr404,
    membership: Annotated[CompanyMember, Depends(require_company_role(CompanyRole.EDITOR))],
) -> None:
    offering = await offering_service.get_offering(db, offering_id)
    if offering is None or offering.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "OFFERING_NOT_FOUND",
                "message": "No offering with that ID exists for this company.",
            },
        )
    await offering_service.delete_offering(db, offering)
