"""
Product / ProductCategory / ProductSpecification / ProductAttribute
service layer — Phase 4B. Mirrors app/services/company_service.py's
conventions (slug generation, search pagination) exactly, reusing
app.core.slug directly rather than duplicating it — that module was
already written generically, not Company-specific.
"""

import math
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.slug import candidate_slugs, slugify
from app.models.offering import Offering
from app.models.product import Product, ProductStatus
from app.models.product_attribute import ProductAttribute
from app.models.product_category import ProductCategory
from app.models.product_specification import ProductSpecification, SpecificationDataType
from app.schemas.product import ProductAttributeInput, ProductCreate, ProductUpdate


class ProductNotFoundError(Exception):
    pass


class CategoryNotFoundError(Exception):
    pass


class InvalidSpecificationError(Exception):
    """Raised when a submitted attribute references a specification that
    doesn't belong to the product's own category — see set_attributes."""


async def _generate_unique_product_slug(db: AsyncSession, name: str) -> str:
    base = slugify(name)
    for candidate in candidate_slugs(base):
        result = await db.execute(select(Product.id).where(Product.slug == candidate))
        if result.scalar_one_or_none() is None:
            return candidate
    raise RuntimeError("Exhausted slug candidates")  # pragma: no cover — practically unreachable


async def _generate_unique_category_slug(db: AsyncSession, name: str) -> str:
    base = slugify(name)
    for candidate in candidate_slugs(base):
        result = await db.execute(
            select(ProductCategory.id).where(ProductCategory.slug == candidate)
        )
        if result.scalar_one_or_none() is None:
            return candidate
    raise RuntimeError("Exhausted slug candidates")  # pragma: no cover


async def get_category(db: AsyncSession, category_id: uuid.UUID) -> ProductCategory | None:
    result = await db.execute(select(ProductCategory).where(ProductCategory.id == category_id))
    return result.scalar_one_or_none()


async def list_categories(db: AsyncSession) -> list[ProductCategory]:
    result = await db.execute(select(ProductCategory).order_by(ProductCategory.name))
    return list(result.scalars().all())


async def create_category(
    db: AsyncSession, name: str, parent_id: uuid.UUID | None
) -> ProductCategory:
    if parent_id is not None:
        parent = await get_category(db, parent_id)
        if parent is None:
            raise CategoryNotFoundError(str(parent_id))
    slug = await _generate_unique_category_slug(db, name)
    category = ProductCategory(name=name, slug=slug, parent_id=parent_id)
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


async def list_specifications_for_category(
    db: AsyncSession, category_id: uuid.UUID
) -> list[ProductSpecification]:
    result = await db.execute(
        select(ProductSpecification).where(ProductSpecification.category_id == category_id)
    )
    return list(result.scalars().all())


async def create_specification(
    db: AsyncSession,
    category_id: uuid.UUID,
    *,
    name: str,
    unit: str | None,
    datatype: SpecificationDataType,
    enum_options: list[str] | None,
    required: bool,
) -> ProductSpecification:
    spec = ProductSpecification(
        category_id=category_id,
        name=name,
        unit=unit,
        datatype=datatype,
        enum_options=enum_options,
        required=required,
    )
    db.add(spec)
    await db.commit()
    await db.refresh(spec)
    return spec


async def get_product(db: AsyncSession, product_id: uuid.UUID) -> Product | None:
    result = await db.execute(
        select(Product)
        .where(Product.id == product_id)
        .options(
            selectinload(Product.category),
            selectinload(Product.attributes).selectinload(ProductAttribute.specification),
        )
    )
    return result.scalar_one_or_none()


async def get_by_slug(db: AsyncSession, slug: str) -> Product | None:
    result = await db.execute(
        select(Product)
        .where(Product.slug == slug)
        .options(
            selectinload(Product.category),
            selectinload(Product.attributes).selectinload(ProductAttribute.specification),
        )
    )
    return result.scalar_one_or_none()


async def _set_attributes(
    db: AsyncSession, product: Product, attributes: list[ProductAttributeInput]
) -> None:
    """
    Replaces the product's full attribute set. Validates every
    specification_id actually belongs to the product's own category —
    per Phase 4A Section 5, specifications are category-scoped; letting
    a Motor product accept a Pump-only specification would silently
    corrupt the whole point of scoping them.

    Mutates `product.attributes` (the ORM relationship collection)
    directly rather than issuing a raw Core-level DELETE — a raw DELETE
    bypasses the session's unit-of-work tracking for this relationship,
    leaving stale in-memory state that produced silently-wrong results
    at commit (found via a real, failing test). `cascade="all,
    delete-orphan"` on Product.attributes (app.models.product) means
    clearing this collection correctly issues real DELETEs for the
    orphaned rows.

    Explicitly `db.refresh()`s the relationship first — `create_product`
    calls this right after `db.flush()`, at which point `product` is
    persistent but `.attributes` has never been loaded; touching it
    synchronously (`.clear()`) would otherwise trigger an implicit lazy
    load, which raises `MissingGreenlet` in an async session (also
    found via a real failing test, a second real bug in this same
    function). `refresh()` is the async-safe way to force that load.
    """
    valid_spec_ids = {
        spec.id for spec in await list_specifications_for_category(db, product.category_id)
    }
    for attr in attributes:
        if attr.specification_id not in valid_spec_ids:
            raise InvalidSpecificationError(str(attr.specification_id))

    await db.refresh(product, attribute_names=["attributes"])
    product.attributes.clear()
    # Forces the delete-orphan cascade's DELETE to actually execute now,
    # before any new row for the same (product_id, specification_id) is
    # inserted below — without this, both operations can land in the
    # same flush batch in the wrong order and violate
    # uq_product_attribute (found via a real, failing test — a third
    # real bug in this one function; see this module's completion
    # report for the full account).
    await db.flush()
    for attr in attributes:
        product.attributes.append(
            ProductAttribute(
                product_id=product.id, specification_id=attr.specification_id, value=attr.value
            )
        )


async def create_product(db: AsyncSession, payload: ProductCreate) -> Product:
    category = await get_category(db, payload.category_id)
    if category is None:
        raise CategoryNotFoundError(str(payload.category_id))

    slug = await _generate_unique_product_slug(db, payload.name)
    product = Product(
        name=payload.name,
        slug=slug,
        description=payload.description,
        product_family=payload.product_family,
        category_id=payload.category_id,
        industry=payload.industry,
        status=ProductStatus.DRAFT,
    )
    db.add(product)
    await db.flush()  # product.id is needed before attribute rows can reference it

    await _set_attributes(db, product, payload.attributes)
    await db.commit()

    refreshed = await get_product(db, product.id)
    assert refreshed is not None  # just committed — always exists
    return refreshed


async def update_product(db: AsyncSession, product: Product, payload: ProductUpdate) -> Product:
    if payload.name is not None:
        product.name = payload.name
    if payload.description is not None:
        product.description = payload.description
    if payload.product_family is not None:
        product.product_family = payload.product_family
    if payload.industry is not None:
        product.industry = payload.industry
    if payload.status is not None:
        product.status = payload.status
    if payload.attributes is not None:
        await _set_attributes(db, product, payload.attributes)

    await db.commit()
    refreshed = await get_product(db, product.id)
    assert refreshed is not None
    return refreshed


async def search_products(
    db: AsyncSession,
    *,
    name: str | None,
    category_id: uuid.UUID | None,
    industry: str | None,
    page: int,
    page_size: int,
) -> tuple[list[tuple[Product, int]], int]:
    """
    Returns (product, offering_count) pairs — the offering count is a
    real, cheap aggregate (not a placeholder), useful to the frontend
    without a second round-trip per product. Only PUBLISHED products
    are searchable — a DRAFT product (Phase 4A Section 6) isn't ready
    for cross-company discovery yet, mirroring how Company search
    (Module 3A) only returns ACTIVE companies.
    """
    query = select(Product).where(Product.status == ProductStatus.PUBLISHED)

    if name:
        like = f"%{name}%"
        query = query.where(Product.name.ilike(like))
    if category_id:
        query = query.where(Product.category_id == category_id)
    if industry:
        query = query.where(Product.industry.ilike(f"%{industry}%"))

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = int(count_result.scalar_one())

    query = (
        query.order_by(Product.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    result = await db.execute(query)
    products = list(result.scalars().all())

    if not products:
        return [], total

    offering_counts_result = await db.execute(
        select(Offering.product_id, func.count(Offering.id))
        .where(Offering.product_id.in_([p.id for p in products]))
        .group_by(Offering.product_id)
    )
    counts: dict[uuid.UUID, int] = {row[0]: row[1] for row in offering_counts_result.all()}

    return [(p, counts.get(p.id, 0)) for p in products], total


def total_pages(total: int, page_size: int) -> int:
    return max(1, math.ceil(total / page_size))
