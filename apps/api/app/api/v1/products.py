"""
Product Graph routes — Phase 4B. A new router file, mounted under
/api/v1, separate from app.api.v1.companies and
app.api.v1.company_verification — this module's brief explicitly frames
the Product Graph as "the second core domain of ForgeX alongside the
existing Company domain," not an extension bolted onto Company's own
router. Offering *mutation* routes live in app.api.v1.offerings instead
(mounted under /companies, reusing app.core.company_authorization
exactly) — see that file's own docstring for why.

Public/authenticated split mirrors Module 3A/3B exactly: read routes
(list, search, detail, offerings, specifications) are public — Product
knowledge is meant to be discoverable without an account, the same
principle app.api.v1.companies.search_companies documents. Mutations
(create/update Product, create/update category or specification)
require authentication only — see this module's completion report for
why no finer-grained product-level RBAC exists yet (an explicitly
flagged, honest limitation, not an oversight).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.core.dependencies import CurrentUser
from app.core.responses import ApiSuccess, success_response
from app.db.session import DbSession
from app.models.offering import Offering
from app.models.product import Product
from app.schemas.product import (
    OfferingCompanySummary,
    OfferingPage,
    OfferingProductSummary,
    OfferingPublic,
    ProductAttributePublic,
    ProductCategoryCreate,
    ProductCategoryPublic,
    ProductCreate,
    ProductDetail,
    ProductSearchPage,
    ProductSearchResult,
    ProductSpecificationCreate,
    ProductSpecificationPublic,
    ProductUpdate,
)
from app.services import offering_service, product_service
from app.services.product_service import CategoryNotFoundError, InvalidSpecificationError


def _to_detail(product: Product) -> ProductDetail:
    """
    Builds ProductDetail explicitly rather than a blind
    `ProductDetail.model_validate(product)` — ProductAttributePublic's
    `specification_name`/`unit` fields aren't direct attributes on the
    ProductAttribute ORM row (only reachable via its `.specification`
    relationship), so Pydantic's from_attributes auto-mapping can't
    resolve them on its own. Found via a real API smoke test (a 500,
    not a theoretical concern) — see this module's completion report.
    """
    return ProductDetail(
        id=product.id,
        name=product.name,
        slug=product.slug,
        description=product.description,
        product_family=product.product_family,
        category=ProductCategoryPublic.model_validate(product.category),
        industry=product.industry,
        status=product.status,
        attributes=[
            ProductAttributePublic(
                specification_id=attr.specification_id,
                specification_name=attr.specification.name,
                unit=attr.specification.unit,
                value=attr.value,
                latest_evidence_id=attr.latest_evidence_id,
            )
            for attr in product.attributes
        ],
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


router = APIRouter(prefix="/products", tags=["products"])
categories_router = APIRouter(prefix="/product-categories", tags=["product-categories"])


# ---- Categories (minimal — needed for Product creation/browsing to function at all) ----


@categories_router.get("", response_model=ApiSuccess[list[ProductCategoryPublic]])
async def list_categories(db: DbSession) -> ApiSuccess[list[ProductCategoryPublic]]:
    categories = await product_service.list_categories(db)
    return success_response([ProductCategoryPublic.model_validate(c) for c in categories])


@categories_router.post(
    "", response_model=ApiSuccess[ProductCategoryPublic], status_code=status.HTTP_201_CREATED
)
async def create_category(
    payload: ProductCategoryCreate, db: DbSession, _current_user: CurrentUser
) -> ApiSuccess[ProductCategoryPublic]:
    try:
        category = await product_service.create_category(db, payload.name, payload.parent_id)
    except CategoryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CATEGORY_NOT_FOUND", "message": "Parent category does not exist."},
        ) from exc
    return success_response(ProductCategoryPublic.model_validate(category))


@categories_router.get(
    "/{category_id}/specifications", response_model=ApiSuccess[list[ProductSpecificationPublic]]
)
async def list_category_specifications(
    category_id: uuid.UUID, db: DbSession
) -> ApiSuccess[list[ProductSpecificationPublic]]:
    specs = await product_service.list_specifications_for_category(db, category_id)
    return success_response([ProductSpecificationPublic.model_validate(s) for s in specs])


@categories_router.post(
    "/{category_id}/specifications",
    response_model=ApiSuccess[ProductSpecificationPublic],
    status_code=status.HTTP_201_CREATED,
)
async def create_category_specification(
    category_id: uuid.UUID,
    payload: ProductSpecificationCreate,
    db: DbSession,
    _current_user: CurrentUser,
) -> ApiSuccess[ProductSpecificationPublic]:
    category = await product_service.get_category(db, category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CATEGORY_NOT_FOUND", "message": "No category with that ID exists."},
        )
    spec = await product_service.create_specification(
        db,
        category_id,
        name=payload.name,
        unit=payload.unit,
        datatype=payload.datatype,
        enum_options=payload.enum_options,
        required=payload.required,
    )
    return success_response(ProductSpecificationPublic.model_validate(spec))


def _to_search_result(product: Product, offering_count: int) -> ProductSearchResult:
    return ProductSearchResult(
        id=product.id,
        name=product.name,
        slug=product.slug,
        product_family=product.product_family,
        category_id=product.category_id,
        industry=product.industry,
        status=product.status,
        offering_count=offering_count,
    )


# ---- Products ----


@router.post("", response_model=ApiSuccess[ProductDetail], status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate, db: DbSession, _current_user: CurrentUser
) -> ApiSuccess[ProductDetail]:
    """
    Any authenticated user may create a Product — per Phase 4A Section
    1, a Product is canonical/shared, not owned by the creator's
    company. Starts in DRAFT status (app.models.product.Product's own
    docstring) — there is no admin-review workflow to move it to
    PUBLISHED yet (a real, explicitly-flagged limitation, not an
    oversight — see this module's completion report).
    """
    try:
        product = await product_service.create_product(db, payload)
    except CategoryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CATEGORY_NOT_FOUND", "message": "No category with that ID exists."},
        ) from exc
    except InvalidSpecificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INVALID_SPECIFICATION",
                "message": "One or more specifications do not belong to this product's category.",
            },
        ) from exc
    return success_response(_to_detail(product))


@router.get("", response_model=ApiSuccess[ProductSearchPage])
async def list_products(
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiSuccess[ProductSearchPage]:
    """Plain paginated browse of published products — no filters. See
    /products/search for filtered discovery."""
    pairs, total = await product_service.search_products(
        db, name=None, category_id=None, industry=None, page=page, page_size=page_size
    )
    items = [_to_search_result(p, count) for p, count in pairs]
    return success_response(
        ProductSearchPage(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=product_service.total_pages(total, page_size),
        )
    )


@router.get("/search", response_model=ApiSuccess[ProductSearchPage])
async def search_products(
    db: DbSession,
    name: str | None = Query(default=None, max_length=255),
    category_id: Annotated[uuid.UUID | None, Query()] = None,
    industry: str | None = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiSuccess[ProductSearchPage]:
    """
    Public, unauthenticated search over PUBLISHED products only —
    mirrors app.api.v1.companies.search_companies exactly. Registered
    before /{product_id} so FastAPI doesn't try to parse "search" as a
    UUID (same ordering reason as companies.py).
    """
    pairs, total = await product_service.search_products(
        db, name=name, category_id=category_id, industry=industry, page=page, page_size=page_size
    )
    items = [_to_search_result(p, count) for p, count in pairs]
    return success_response(
        ProductSearchPage(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=product_service.total_pages(total, page_size),
        )
    )


@router.get("/slug/{slug}", response_model=ApiSuccess[ProductDetail])
async def get_product_by_slug(slug: str, db: DbSession) -> ApiSuccess[ProductDetail]:
    product = await product_service.get_by_slug(db, slug)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PRODUCT_NOT_FOUND", "message": "No product with that slug exists."},
        )
    return success_response(_to_detail(product))


@router.get("/{product_id}", response_model=ApiSuccess[ProductDetail])
async def get_product(product_id: uuid.UUID, db: DbSession) -> ApiSuccess[ProductDetail]:
    product = await product_service.get_product(db, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PRODUCT_NOT_FOUND", "message": "No product with that ID exists."},
        )
    return success_response(_to_detail(product))


@router.patch("/{product_id}", response_model=ApiSuccess[ProductDetail])
async def update_product(
    product_id: uuid.UUID, payload: ProductUpdate, db: DbSession, _current_user: CurrentUser
) -> ApiSuccess[ProductDetail]:
    product = await product_service.get_product(db, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PRODUCT_NOT_FOUND", "message": "No product with that ID exists."},
        )
    try:
        updated = await product_service.update_product(db, product, payload)
    except InvalidSpecificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INVALID_SPECIFICATION",
                "message": "One or more specifications do not belong to this product's category.",
            },
        ) from exc
    return success_response(_to_detail(updated))


@router.get(
    "/{product_id}/specifications", response_model=ApiSuccess[list[ProductSpecificationPublic]]
)
async def get_product_specifications(
    product_id: uuid.UUID, db: DbSession
) -> ApiSuccess[list[ProductSpecificationPublic]]:
    product = await product_service.get_product(db, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PRODUCT_NOT_FOUND", "message": "No product with that ID exists."},
        )
    specs = await product_service.list_specifications_for_category(db, product.category_id)
    return success_response([ProductSpecificationPublic.model_validate(s) for s in specs])


@router.get("/{product_id}/offerings", response_model=ApiSuccess[OfferingPage])
async def get_product_offerings(
    product_id: uuid.UUID,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiSuccess[OfferingPage]:
    """Public — which companies offer this product, and in what role.
    This IS the answer to the module's ABSOLUTE RULE: many companies,
    one Product, zero duplication."""
    product = await product_service.get_product(db, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PRODUCT_NOT_FOUND", "message": "No product with that ID exists."},
        )
    offerings, total = await offering_service.list_offerings_for_product(
        db, product_id, page, page_size
    )
    return success_response(
        OfferingPage(
            items=[_offering_to_public(o) for o in offerings],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=offering_service.total_pages(total, page_size),
        )
    )


def _offering_to_public(offering: Offering) -> OfferingPublic:
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
