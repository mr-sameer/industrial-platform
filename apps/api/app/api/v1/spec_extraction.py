"""
Spec extraction trigger route — the one new API surface for the
approved deterministic specification-extraction milestone. A new
router file, mounted under /api/v1 like every other new subsystem in
this codebase, separate from app.api.v1.products and
app.api.v1.product_attribute_evidence — neither existing file is
modified.

Role.ADMIN-gated: this parses untrusted document content and writes
database rows, the same trust tier this codebase already uses for
POST /documents (app.api.v1.documents) and POST /acquisition/jobs
(app.api.v1.acquisition). `product_id` is supplied explicitly by the
admin operator — this route performs no product matching, discovery,
or creation of any kind (see app.services.spec_extraction_service's
own docstring).

Deliberately does NOT expose SpecificationAlias creation. The existing
specification-authoring endpoints
(app.api.v1.products.create_category_specification and
create_category) require only an authenticated user, not Role.ADMIN —
wiring alias configuration through that surface would let any
authenticated user influence which labels this deterministic extractor
treats as equivalent. Per this milestone's own design review, that gap
is reported rather than silently worked around (see this
implementation's completion report); alias rows are seeded directly
(service/script/fixture) until that authorization question is resolved
as its own, separate decision. Nothing in this file changes.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import require_role
from app.core.responses import ApiSuccess, success_response
from app.db.session import DbSession
from app.models.user import Role
from app.schemas.spec_extraction import (
    AmbiguousConfigurationPublic,
    ExtractionRunPublic,
    ExtractionRunRequest,
    RejectedCandidatePublic,
)
from app.services import spec_extraction_service
from app.services.spec_extraction_service import (
    InvalidDocumentStructureError,
    ProductNotFoundForExtractionError,
    RawObservationNotFoundForExtractionError,
)

router = APIRouter(prefix="/products", tags=["spec-extraction"])

RequireAdmin = Annotated[object, Depends(require_role(Role.ADMIN))]


@router.post(
    "/{product_id}/extract-specifications",
    response_model=ApiSuccess[ExtractionRunPublic],
)
async def extract_specifications(
    product_id: uuid.UUID,
    payload: ExtractionRunRequest,
    db: DbSession,
    _admin: RequireAdmin,
) -> ApiSuccess[ExtractionRunPublic]:
    try:
        result = await spec_extraction_service.run_extraction(
            db, product_id=product_id, raw_observation_id=payload.raw_observation_id
        )
    except ProductNotFoundForExtractionError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PRODUCT_NOT_FOUND", "message": "No product with that ID exists."},
        ) from exc
    except RawObservationNotFoundForExtractionError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RAW_OBSERVATION_NOT_FOUND",
                "message": "No raw observation with that ID exists.",
            },
        ) from exc
    except InvalidDocumentStructureError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_DOCUMENT_STRUCTURE", "message": str(exc)},
        ) from exc

    return success_response(
        ExtractionRunPublic(
            created=result.created,
            existing=result.existing,
            rejected=[
                RejectedCandidatePublic(page=r.page, label=r.label, reason=r.reason)
                for r in result.rejected
            ],
            ambiguous_configuration=[
                AmbiguousConfigurationPublic(
                    label=entry.label, specification_ids=entry.specification_ids
                )
                for entry in result.ambiguous_configuration
            ],
        )
    )
