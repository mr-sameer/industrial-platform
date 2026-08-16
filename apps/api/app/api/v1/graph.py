"""
Industrial Knowledge Graph routes — Module 5F. A new file, mounted
under /api/v1, separate from every existing router. Role.ADMIN-gated
for all mutations and relationship-verification actions, matching
Module 5B/5C/5D/5E's own established pattern — per this module's own
explicit instruction, no public endpoint allows arbitrary graph
mutation. Read/query routes are also admin-gated in this first pass —
an internal, backend-first surface (per 5F.12's own instruction to
prefer this over any public UI), not yet the public-facing retrieval
layer architecture Section 21 describes as a future possibility.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.dependencies import CurrentUser, require_role
from app.core.responses import ApiSuccess, success_response
from app.db.session import DbSession
from app.models.user import Role
from app.schemas.graph import (
    CapabilityCreate,
    CapabilityPublic,
    CompanyGraphView,
    FactoryCreate,
    FactoryPublic,
    GraphRelationshipCreate,
    GraphRelationshipPublic,
    RelationshipRejectRequest,
)
from app.services import graph_service
from app.services.graph_service import (
    CompanyNotFoundError,
    InvalidRelationshipError,
    RelationshipNotUnderReviewableStateError,
)

router = APIRouter(prefix="/graph", tags=["graph"])

RequireAdmin = Annotated[object, Depends(require_role(Role.ADMIN))]


# --------------------------------------------------------------------
# Factory
# --------------------------------------------------------------------


@router.post(
    "/factories", response_model=ApiSuccess[FactoryPublic], status_code=status.HTTP_201_CREATED
)
async def create_factory(
    payload: FactoryCreate, db: DbSession, _admin: RequireAdmin
) -> ApiSuccess[FactoryPublic]:
    try:
        factory = await graph_service.create_factory(db, payload)
    except CompanyNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "COMPANY_NOT_FOUND", "message": "No company with that ID exists."},
        ) from exc
    return success_response(FactoryPublic.model_validate(factory))


@router.get("/factories/{factory_id}", response_model=ApiSuccess[FactoryPublic])
async def get_factory(
    factory_id: uuid.UUID, db: DbSession, _admin: RequireAdmin
) -> ApiSuccess[FactoryPublic]:
    factory = await graph_service.get_factory(db, factory_id)
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "FACTORY_NOT_FOUND", "message": "No factory with that ID exists."},
        )
    return success_response(FactoryPublic.model_validate(factory))


@router.get("/companies/{company_id}/factories", response_model=ApiSuccess[list[FactoryPublic]])
async def list_factories(
    company_id: uuid.UUID, db: DbSession, _admin: RequireAdmin
) -> ApiSuccess[list[FactoryPublic]]:
    factories = await graph_service.list_factories_for_company(db, company_id)
    return success_response([FactoryPublic.model_validate(f) for f in factories])


# --------------------------------------------------------------------
# Capability
# --------------------------------------------------------------------


@router.post(
    "/capabilities",
    response_model=ApiSuccess[CapabilityPublic],
    status_code=status.HTTP_201_CREATED,
)
async def create_capability(
    payload: CapabilityCreate, db: DbSession, _admin: RequireAdmin
) -> ApiSuccess[CapabilityPublic]:
    capability = await graph_service.create_capability(db, payload)
    return success_response(CapabilityPublic.model_validate(capability))


@router.get("/capabilities", response_model=ApiSuccess[list[CapabilityPublic]])
async def list_capabilities(
    db: DbSession, _admin: RequireAdmin
) -> ApiSuccess[list[CapabilityPublic]]:
    capabilities = await graph_service.list_capabilities(db)
    return success_response([CapabilityPublic.model_validate(c) for c in capabilities])


# --------------------------------------------------------------------
# Relationships
# --------------------------------------------------------------------


@router.post(
    "/relationships",
    response_model=ApiSuccess[GraphRelationshipPublic],
    status_code=status.HTTP_201_CREATED,
)
async def create_relationship(
    payload: GraphRelationshipCreate, db: DbSession, _admin: RequireAdmin
) -> ApiSuccess[GraphRelationshipPublic]:
    try:
        relationship = await graph_service.create_relationship(db, payload)
    except CompanyNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "COMPANY_NOT_FOUND", "message": "No company with that ID exists."},
        ) from exc
    except InvalidRelationshipError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_RELATIONSHIP", "message": str(exc)},
        ) from exc
    return success_response(GraphRelationshipPublic.model_validate(relationship))


@router.get("/relationships/{relationship_id}", response_model=ApiSuccess[GraphRelationshipPublic])
async def get_relationship(
    relationship_id: uuid.UUID, db: DbSession, _admin: RequireAdmin
) -> ApiSuccess[GraphRelationshipPublic]:
    relationship = await graph_service.get_relationship(db, relationship_id)
    if relationship is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RELATIONSHIP_NOT_FOUND",
                "message": "No relationship with that ID exists.",
            },
        )
    return success_response(GraphRelationshipPublic.model_validate(relationship))


@router.post(
    "/relationships/{relationship_id}/verify", response_model=ApiSuccess[GraphRelationshipPublic]
)
async def verify_relationship(
    relationship_id: uuid.UUID, db: DbSession, current_user: CurrentUser, _admin: RequireAdmin
) -> ApiSuccess[GraphRelationshipPublic]:
    relationship = await graph_service.get_relationship(db, relationship_id)
    if relationship is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RELATIONSHIP_NOT_FOUND",
                "message": "No relationship with that ID exists.",
            },
        )
    try:
        updated = await graph_service.verify_relationship(
            db, relationship, verified_by=current_user.id
        )
    except RelationshipNotUnderReviewableStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "ALREADY_VERIFIED", "message": str(exc)},
        ) from exc
    return success_response(GraphRelationshipPublic.model_validate(updated))


@router.post(
    "/relationships/{relationship_id}/reject", response_model=ApiSuccess[GraphRelationshipPublic]
)
async def reject_relationship(
    relationship_id: uuid.UUID,
    payload: RelationshipRejectRequest,
    db: DbSession,
    current_user: CurrentUser,
    _admin: RequireAdmin,
) -> ApiSuccess[GraphRelationshipPublic]:
    relationship = await graph_service.get_relationship(db, relationship_id)
    if relationship is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RELATIONSHIP_NOT_FOUND",
                "message": "No relationship with that ID exists.",
            },
        )
    try:
        updated = await graph_service.reject_relationship(
            db, relationship, reviewer_id=current_user.id, note=payload.note
        )
    except RelationshipNotUnderReviewableStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "INVALID_TRANSITION", "message": str(exc)},
        ) from exc
    return success_response(GraphRelationshipPublic.model_validate(updated))


@router.post("/relationships/flag-conflict", response_model=ApiSuccess[dict[str, str]])
async def flag_conflict(
    relationship_a_id: uuid.UUID,
    relationship_b_id: uuid.UUID,
    db: DbSession,
    _admin: RequireAdmin,
) -> ApiSuccess[dict[str, str]]:
    """Manual conflict flagging — see graph_service's own docstring for
    why this is deliberate, not automatic, for relationship-level
    conflicts."""
    relationship_a = await graph_service.get_relationship(db, relationship_a_id)
    relationship_b = await graph_service.get_relationship(db, relationship_b_id)
    if relationship_a is None or relationship_b is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RELATIONSHIP_NOT_FOUND",
                "message": "One or both relationships do not exist.",
            },
        )
    conflict = await graph_service.flag_relationship_conflict(db, relationship_a, relationship_b)
    return success_response({"conflict_id": str(conflict.id), "status": conflict.status.value})


# --------------------------------------------------------------------
# Query layer (architecture Section 19 / 5F.10)
# --------------------------------------------------------------------


@router.get("/companies/{company_id}/view", response_model=ApiSuccess[CompanyGraphView])
async def get_company_graph_view(
    company_id: uuid.UUID, db: DbSession, _admin: RequireAdmin
) -> ApiSuccess[CompanyGraphView]:
    """The unified traversal view — Offering-derived edges plus
    graph_relationships edges, presented consistently."""
    offering_edges = await graph_service.get_offering_edges_for_company(db, company_id)
    relationship_edges = await graph_service.list_relationships_for_company(db, company_id)
    return success_response(
        CompanyGraphView(
            company_id=company_id,
            offering_edges=offering_edges,
            relationship_edges=[
                GraphRelationshipPublic.model_validate(r) for r in relationship_edges
            ],
        )
    )


@router.get("/query/manufacturers-of-product/{product_id}", response_model=ApiSuccess[list[str]])
async def query_manufacturers_of_product(
    product_id: uuid.UUID, db: DbSession, _admin: RequireAdmin
) -> ApiSuccess[list[str]]:
    company_ids = await graph_service.find_manufacturers_of_product(db, product_id)
    return success_response([str(cid) for cid in company_ids])


@router.get("/query/distributors-of-product/{product_id}", response_model=ApiSuccess[list[str]])
async def query_distributors_of_product(
    product_id: uuid.UUID, db: DbSession, _admin: RequireAdmin, country: str = Query(...)
) -> ApiSuccess[list[str]]:
    company_ids = await graph_service.find_distributors_of_product_in_country(
        db, product_id, country
    )
    return success_response([str(cid) for cid in company_ids])


@router.get("/query/companies-by-capability/{capability_id}", response_model=ApiSuccess[list[str]])
async def query_companies_by_capability(
    capability_id: uuid.UUID,
    db: DbSession,
    _admin: RequireAdmin,
    city: str | None = Query(default=None),
    verified_only: bool = Query(default=False),
) -> ApiSuccess[list[str]]:
    company_ids = await graph_service.find_companies_by_capability(
        db, capability_id, city=city, verified_only=verified_only
    )
    return success_response([str(cid) for cid in company_ids])


@router.get(
    "/query/companies/{company_id}/offerings-by-category",
    response_model=ApiSuccess[list[dict[str, object]]],
)
async def query_traverse_offering_category(
    company_id: uuid.UUID, db: DbSession, _admin: RequireAdmin
) -> ApiSuccess[list[dict[str, object]]]:
    rows = await graph_service.traverse_company_offering_product_category(db, company_id)
    return success_response(
        [{k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in row.items()} for row in rows]
    )
