"""
Product Attribute Evidence routes — extends the Product Graph (Phase
4B) with the evidence/provenance mechanism ProductAttribute previously
lacked entirely. A new router file, mounted under /api/v1 like every
other new subsystem in this codebase (app.api.v1.provenance,
app.api.v1.graph), separate from app.api.v1.products.

Creating evidence requires authentication only, matching
provenance_service.create_provenance_record's equivalent route — this
records a claim, it doesn't assert truth. Reading evidence (list/get)
is public, matching the same "provenance is meant to be inspectable"
principle app.api.v1.provenance already documents. Verifying,
rejecting, and applying evidence to a Product's canonical attribute
value are Role.ADMIN-gated — per this mechanism's own explicit
requirement that evidence review must not be available to arbitrary
authenticated users, matching app.api.v1.graph's relationship
verify/reject precedent rather than Module 5A's original (looser)
provenance-record verify route.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.dependencies import CurrentUser, require_role
from app.core.responses import ApiSuccess, success_response
from app.db.session import DbSession
from app.models.user import Role
from app.schemas.product_attribute_evidence import (
    ApplyAttributeEvidenceResponse,
    ProductAttributeEvidenceCreate,
    ProductAttributeEvidencePage,
    ProductAttributeEvidencePublic,
    ProductAttributeEvidenceRejectRequest,
)
from app.services import product_attribute_evidence_service
from app.services.product_attribute_evidence_service import (
    AlreadyVerifiedError,
    EmptyValueError,
    EvidenceNotReviewableStateError,
    EvidenceNotVerifiedError,
    ProductNotFoundForEvidenceError,
    RawObservationNotFoundForEvidenceError,
    SpecificationNotFoundForEvidenceError,
    SpecificationNotInProductCategoryError,
)

router = APIRouter(prefix="/products", tags=["product-attribute-evidence"])

RequireAdmin = Annotated[object, Depends(require_role(Role.ADMIN))]


def _evidence_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "EVIDENCE_NOT_FOUND",
            "message": "No attribute evidence with that ID exists.",
        },
    )


@router.post(
    "/{product_id}/attributes/{specification_id}/evidence",
    response_model=ApiSuccess[ProductAttributeEvidencePublic],
    status_code=status.HTTP_201_CREATED,
)
async def create_attribute_evidence(
    product_id: uuid.UUID,
    specification_id: uuid.UUID,
    payload: ProductAttributeEvidenceCreate,
    db: DbSession,
    _current_user: CurrentUser,
) -> ApiSuccess[ProductAttributeEvidencePublic]:
    if payload.product_id != product_id or payload.specification_id != specification_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "ATTRIBUTE_MISMATCH",
                "message": "product_id/specification_id in the body must match the URL path.",
            },
        )
    try:
        evidence, _conflict = await product_attribute_evidence_service.create_attribute_evidence(
            db, payload
        )
    except ProductNotFoundForEvidenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PRODUCT_NOT_FOUND", "message": "No product with that ID exists."},
        ) from exc
    except SpecificationNotFoundForEvidenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "SPECIFICATION_NOT_FOUND",
                "message": "No specification with that ID exists.",
            },
        ) from exc
    except SpecificationNotInProductCategoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_SPECIFICATION", "message": str(exc)},
        ) from exc
    except RawObservationNotFoundForEvidenceError as exc:
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
            detail={"code": "INVALID_EVIDENCE", "message": str(exc)},
        ) from exc
    return success_response(ProductAttributeEvidencePublic.model_validate(evidence))


@router.get(
    "/{product_id}/attributes/{specification_id}/evidence",
    response_model=ApiSuccess[ProductAttributeEvidencePage],
)
async def list_attribute_evidence(
    product_id: uuid.UUID,
    specification_id: uuid.UUID,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiSuccess[ProductAttributeEvidencePage]:
    """The full evidence ledger for one (product, specification) pair —
    every source's claim, agreeing or conflicting, verified or not."""
    items, total = await product_attribute_evidence_service.list_attribute_evidence(
        db,
        product_id=product_id,
        specification_id=specification_id,
        page=page,
        page_size=page_size,
    )
    return success_response(
        ProductAttributeEvidencePage(
            items=[ProductAttributeEvidencePublic.model_validate(e) for e in items],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=product_attribute_evidence_service.total_pages(total, page_size),
        )
    )


@router.get(
    "/attribute-evidence/{evidence_id}", response_model=ApiSuccess[ProductAttributeEvidencePublic]
)
async def get_attribute_evidence(
    evidence_id: uuid.UUID, db: DbSession
) -> ApiSuccess[ProductAttributeEvidencePublic]:
    evidence = await product_attribute_evidence_service.get_attribute_evidence(db, evidence_id)
    if evidence is None:
        raise _evidence_not_found()
    return success_response(ProductAttributeEvidencePublic.model_validate(evidence))


@router.post(
    "/attribute-evidence/{evidence_id}/verify",
    response_model=ApiSuccess[ProductAttributeEvidencePublic],
)
async def verify_attribute_evidence(
    evidence_id: uuid.UUID, db: DbSession, current_user: CurrentUser, _admin: RequireAdmin
) -> ApiSuccess[ProductAttributeEvidencePublic]:
    """
    The one and only route that can set status=VERIFIED — see
    product_attribute_evidence_service.verify_product_attribute_evidence's
    own docstring. Role.ADMIN-gated: this is a review decision, not a
    claim submission.
    """
    evidence = await product_attribute_evidence_service.get_attribute_evidence(db, evidence_id)
    if evidence is None:
        raise _evidence_not_found()
    try:
        verified = await product_attribute_evidence_service.verify_product_attribute_evidence(
            db, evidence, verified_by=current_user.id
        )
    except AlreadyVerifiedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "ALREADY_VERIFIED",
                "message": "This attribute evidence is already verified.",
            },
        ) from exc
    return success_response(ProductAttributeEvidencePublic.model_validate(verified))


@router.post(
    "/attribute-evidence/{evidence_id}/reject",
    response_model=ApiSuccess[ProductAttributeEvidencePublic],
)
async def reject_attribute_evidence(
    evidence_id: uuid.UUID,
    payload: ProductAttributeEvidenceRejectRequest,
    db: DbSession,
    current_user: CurrentUser,
    _admin: RequireAdmin,
) -> ApiSuccess[ProductAttributeEvidencePublic]:
    evidence = await product_attribute_evidence_service.get_attribute_evidence(db, evidence_id)
    if evidence is None:
        raise _evidence_not_found()
    try:
        rejected = await product_attribute_evidence_service.reject_product_attribute_evidence(
            db, evidence, reviewer_id=current_user.id, note=payload.note
        )
    except EvidenceNotReviewableStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "INVALID_TRANSITION", "message": str(exc)},
        ) from exc
    return success_response(ProductAttributeEvidencePublic.model_validate(rejected))


@router.post(
    "/attribute-evidence/{evidence_id}/apply",
    response_model=ApiSuccess[ApplyAttributeEvidenceResponse],
)
async def apply_attribute_evidence(
    evidence_id: uuid.UUID, db: DbSession, current_user: CurrentUser, _admin: RequireAdmin
) -> ApiSuccess[ApplyAttributeEvidenceResponse]:
    """
    Closes the same gap apply_provenance_record_to_company closes for
    Company fields — writes a VERIFIED evidence claim onto the
    canonical ProductAttribute value. This route does no business logic
    of its own: it resolves the evidence row by id and delegates
    entirely to
    product_attribute_evidence_service.apply_reviewed_attribute_to_product.
    """
    evidence = await product_attribute_evidence_service.get_attribute_evidence(db, evidence_id)
    if evidence is None:
        raise _evidence_not_found()
    try:
        attribute = await product_attribute_evidence_service.apply_reviewed_attribute_to_product(
            db, evidence, reviewer_id=current_user.id
        )
    except EvidenceNotVerifiedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "NOT_VERIFIED", "message": str(exc)},
        ) from exc
    except EmptyValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "EMPTY_VALUE", "message": str(exc)},
        ) from exc

    refreshed_evidence = await product_attribute_evidence_service.get_attribute_evidence(
        db, evidence_id
    )
    assert refreshed_evidence is not None  # just applied against it — always exists
    return success_response(
        ApplyAttributeEvidenceResponse(
            product_id=attribute.product_id,
            specification_id=attribute.specification_id,
            value=attribute.value,
            evidence=ProductAttributeEvidencePublic.model_validate(refreshed_evidence),
        )
    )
