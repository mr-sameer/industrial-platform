"""
SpecificationAlias management routes — the dedicated ADMIN-only alias
API the deterministic specification-extraction milestone's own
completion report identified as missing. A new router, mounted under
/api/v1 like every other new subsystem in this codebase, entirely
separate from app.api.v1.products — that file
(create_category_specification, create_category) is NOT modified by
this change, and its authorization (authenticated user, not
Role.ADMIN) stays exactly as it is. This route is the resolution to
that gap: a new, narrower, ADMIN-gated surface instead of loosening or
routing through the existing one.

Create is Role.ADMIN-gated: an alias directly shapes which label text
app.extraction.label_matching treats as equivalent to a specification,
which in turn drives what becomes deterministic
ProductAttributeEvidence — the same trust tier this codebase already
reserves for consequential, code-executing admin actions (document
upload in app.api.v1.documents, acquisition jobs in
app.api.v1.acquisition, evidence verify/reject/apply in
app.api.v1.product_attribute_evidence).

List is deliberately left public, unauthenticated — not an oversight.
Every other piece of a ProductSpecification's own configuration (name,
unit, datatype, enum_options) is already public via
GET /product-categories/{id}/specifications
(app.api.v1.products's own module docstring: "(list, search, detail,
offerings, specifications) are public"). An alias is just more of that
same public specification metadata, not a secret — gating reads here
while enum_options stays public would be an inconsistency in this API,
not a real security boundary, since neither carries anything sensitive.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import require_role
from app.core.responses import ApiSuccess, success_response
from app.db.session import DbSession
from app.models.user import Role
from app.schemas.specification_alias import SpecificationAliasCreate, SpecificationAliasPublic
from app.services import specification_alias_service
from app.services.specification_alias_service import (
    DuplicateAliasError,
    EmptyAliasError,
    SpecificationNotFoundForAliasError,
)

router = APIRouter(prefix="/product-specifications", tags=["specification-aliases"])

RequireAdmin = Annotated[object, Depends(require_role(Role.ADMIN))]


@router.post(
    "/{specification_id}/aliases",
    response_model=ApiSuccess[SpecificationAliasPublic],
    status_code=status.HTTP_201_CREATED,
)
async def create_specification_alias(
    specification_id: uuid.UUID,
    payload: SpecificationAliasCreate,
    db: DbSession,
    _admin: RequireAdmin,
) -> ApiSuccess[SpecificationAliasPublic]:
    try:
        alias = await specification_alias_service.create_alias(db, specification_id, payload.alias)
    except SpecificationNotFoundForAliasError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "SPECIFICATION_NOT_FOUND",
                "message": "No specification with that ID exists.",
            },
        ) from exc
    except EmptyAliasError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "EMPTY_ALIAS", "message": str(exc)},
        ) from exc
    except DuplicateAliasError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "DUPLICATE_ALIAS", "message": str(exc)},
        ) from exc
    return success_response(SpecificationAliasPublic.model_validate(alias))


@router.get(
    "/{specification_id}/aliases",
    response_model=ApiSuccess[list[SpecificationAliasPublic]],
)
async def list_specification_aliases(
    specification_id: uuid.UUID, db: DbSession
) -> ApiSuccess[list[SpecificationAliasPublic]]:
    aliases = await specification_alias_service.list_aliases(db, specification_id)
    return success_response([SpecificationAliasPublic.model_validate(a) for a in aliases])
